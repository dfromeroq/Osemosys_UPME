"""Registro y consulta de auditoría sobre `osemosys_param_value`."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Sequence

from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.types import String as SAString

from app.db.dialect import is_sqlite_mode
from app.models import OsemosysParamValueAudit


def user_actor(current_user) -> str:
    """Nombre de usuario para `changed_by`."""
    return str(current_user.username)


@dataclass
class AuditBatch:
    """Identificador de una operación que agrupa N entradas de auditoría."""

    id: str
    label: str | None = None


# ---------------------------------------------------------------------------
# Filtrado por dimensiones contra `dimensions_json`
# ---------------------------------------------------------------------------
#
# El campo `dimensions_json` guarda un dict con claves:
#   region_name, technology_name, fuel_name, emission_name, udc_name, year.
# Postgres usa JSONB → se filtra con operadores nativos. SQLite no tiene
# operadores JSON estables disponibles vía SQLAlchemy core, así que se hace
# un fallback con LIKE sobre el texto serializado (suficiente para modo local).

_DIMENSION_KEYS = {
    "region_name",
    "technology_name",
    "fuel_name",
    "emission_name",
    "udc_name",
}


def _dimension_filter_clause(key: str, values: Sequence[str]):
    """Construye una cláusula SQL para filtrar dimensions_json[key] IN values."""
    if not values:
        return None
    col = OsemosysParamValueAudit.dimensions_json
    if is_sqlite_mode():
        # SQLite: comparar contra texto serializado (heurístico pero útil para dev).
        like_clauses = [
            cast(col, SAString).like(f'%"{key}": "{v}"%') for v in values if v
        ]
        return or_(*like_clauses) if like_clauses else None
    # Postgres: usar operador ->> que extrae como texto.
    text_value = col.op("->>")(key)
    return text_value.in_(list(values))


class OsemosysParamAuditService:
    @staticmethod
    @contextmanager
    def batch(label: str | None = None) -> Iterator[AuditBatch]:
        """Genera un batch_id compartible para agrupar entradas de auditoría.

        Uso::

            with OsemosysParamAuditService.batch(label="Aplicación Excel: ...") as b:
                for row in changes:
                    OsemosysParamAuditService.append(
                        ..., batch_id=b.id, batch_label=b.label,
                    )
        """
        yield AuditBatch(id=str(uuid.uuid4()), label=label)

    @staticmethod
    def append(
        db: Session,
        *,
        scenario_id: int,
        param_name: str,
        id_osemosys_param_value: int | None,
        action: str,
        old_value: float | None,
        new_value: float | None,
        dimensions_json: dict | None,
        source: str,
        changed_by: str,
        batch_id: str | None = None,
        batch_label: str | None = None,
    ) -> None:
        db.add(
            OsemosysParamValueAudit(
                id_scenario=scenario_id,
                param_name=param_name,
                id_osemosys_param_value=id_osemosys_param_value,
                action=action,
                old_value=old_value,
                new_value=new_value,
                dimensions_json=dimensions_json,
                source=source,
                changed_by=changed_by,
                batch_id=batch_id,
                batch_label=batch_label,
            )
        )

    @staticmethod
    def list_for_param(
        db: Session,
        *,
        scenario_id: int,
        param_name: str,
        offset: int,
        limit: int,
    ) -> tuple[list[OsemosysParamValueAudit], int]:
        where = (
            (OsemosysParamValueAudit.id_scenario == scenario_id)
            & (OsemosysParamValueAudit.param_name == param_name)
        )
        total = int(
            db.scalar(select(func.count()).select_from(OsemosysParamValueAudit).where(where)) or 0
        )
        stmt = (
            select(OsemosysParamValueAudit)
            .where(where)
            .order_by(OsemosysParamValueAudit.created_at.desc(), OsemosysParamValueAudit.id.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = list(db.execute(stmt).scalars().all())
        return rows, total

    # ------------------------------------------------------------------
    # Listado scenario-wide con filtros
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filter_clauses(
        *,
        scenario_id: int,
        param_names: Sequence[str] | None = None,
        actions: Sequence[str] | None = None,
        sources: Sequence[str] | None = None,
        changed_by: Sequence[str] | None = None,
        batch_ids: Sequence[str] | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        dimension_filters: dict[str, Sequence[str]] | None = None,
        value_id: int | None = None,
        q: str | None = None,
    ):
        clauses = [OsemosysParamValueAudit.id_scenario == scenario_id]
        if param_names:
            clauses.append(OsemosysParamValueAudit.param_name.in_(list(param_names)))
        if actions:
            clauses.append(OsemosysParamValueAudit.action.in_(list(actions)))
        if sources:
            clauses.append(OsemosysParamValueAudit.source.in_(list(sources)))
        if changed_by:
            clauses.append(OsemosysParamValueAudit.changed_by.in_(list(changed_by)))
        if batch_ids:
            clauses.append(OsemosysParamValueAudit.batch_id.in_(list(batch_ids)))
        if from_date is not None:
            clauses.append(OsemosysParamValueAudit.created_at >= from_date)
        if to_date is not None:
            clauses.append(OsemosysParamValueAudit.created_at <= to_date)
        if value_id is not None:
            clauses.append(OsemosysParamValueAudit.id_osemosys_param_value == value_id)

        if year_from is not None or year_to is not None:
            col = OsemosysParamValueAudit.dimensions_json
            if is_sqlite_mode():
                # En SQLite no podemos hacer rango sobre JSON; aproximamos comparando texto.
                # Generamos predicados LIKE para cada año en rango (acotado a 200 años).
                lo = year_from if year_from is not None else 1900
                hi = year_to if year_to is not None else 2100
                if hi - lo <= 200:
                    like_clauses = [cast(col, SAString).like(f'%"year": {y}%') for y in range(lo, hi + 1)]
                    if like_clauses:
                        clauses.append(or_(*like_clauses))
            else:
                year_text = col.op("->>")("year")
                year_int = func.cast(year_text, sa_int_type())
                if year_from is not None:
                    clauses.append(year_int >= year_from)
                if year_to is not None:
                    clauses.append(year_int <= year_to)

        if dimension_filters:
            for key, values in dimension_filters.items():
                if key not in _DIMENSION_KEYS or not values:
                    continue
                clause = _dimension_filter_clause(key, values)
                if clause is not None:
                    clauses.append(clause)

        if q:
            like = f"%{q}%"
            text_search = or_(
                OsemosysParamValueAudit.param_name.ilike(like),
                OsemosysParamValueAudit.changed_by.ilike(like),
                OsemosysParamValueAudit.batch_label.ilike(like),
                cast(OsemosysParamValueAudit.dimensions_json, SAString).ilike(like),
            )
            clauses.append(text_search)

        return and_(*clauses)

    @staticmethod
    def list_entries(
        db: Session,
        *,
        scenario_id: int,
        offset: int = 0,
        limit: int = 50,
        **filters,
    ) -> tuple[list[OsemosysParamValueAudit], int]:
        where = OsemosysParamAuditService._build_filter_clauses(
            scenario_id=scenario_id, **filters
        )
        total = int(
            db.scalar(select(func.count()).select_from(OsemosysParamValueAudit).where(where)) or 0
        )
        stmt = (
            select(OsemosysParamValueAudit)
            .where(where)
            .order_by(OsemosysParamValueAudit.created_at.desc(), OsemosysParamValueAudit.id.desc())
            .offset(max(0, offset))
            .limit(max(1, min(limit, 1000)))
        )
        rows = list(db.execute(stmt).scalars().all())
        return rows, total

    @staticmethod
    def list_grouped_batches(
        db: Session,
        *,
        scenario_id: int,
        offset: int = 0,
        limit: int = 50,
        preview_size: int = 5,
        **filters,
    ) -> tuple[list[dict], int, int]:
        """Lista batches agrupados (batch_id) ordenados por última actividad.

        Entradas con `batch_id IS NULL` se agrupan como pseudo-batches por
        `(changed_by, source, created_at minute)` para que las ediciones
        individuales históricas se vean como batches de tamaño 1+.
        """
        where = OsemosysParamAuditService._build_filter_clauses(
            scenario_id=scenario_id, **filters
        )

        total_entries = int(
            db.scalar(select(func.count()).select_from(OsemosysParamValueAudit).where(where)) or 0
        )

        stmt = (
            select(OsemosysParamValueAudit)
            .where(where)
            .order_by(OsemosysParamValueAudit.created_at.desc(), OsemosysParamValueAudit.id.desc())
        )
        rows = list(db.execute(stmt).scalars().all())

        # Agrupar manualmente para soportar fallback heurístico para legacy (batch_id NULL).
        groups: dict[str, dict] = {}
        order: list[str] = []

        def _legacy_group_key(r: OsemosysParamValueAudit) -> str:
            ts: datetime = r.created_at  # type: ignore[assignment]
            bucket = ts.replace(second=0, microsecond=0).isoformat() if ts else "no-ts"
            return f"legacy::{r.changed_by}::{r.source}::{bucket}"

        for r in rows:
            key = str(r.batch_id) if r.batch_id else _legacy_group_key(r)
            grp = groups.get(key)
            if grp is None:
                grp = {
                    "key": key,
                    "batch_id": str(r.batch_id) if r.batch_id else None,
                    "batch_label": r.batch_label,
                    "changed_by": str(r.changed_by),
                    "source": str(r.source),
                    "started_at": r.created_at,
                    "ended_at": r.created_at,
                    "stats": {"INSERT": 0, "UPDATE": 0, "DELETE": 0},
                    "params_touched": set(),
                    "entries_count": 0,
                    "preview_rows": [],
                    "reverted_count": 0,
                    "is_revert_count": 0,
                }
                groups[key] = grp
                order.append(key)

            grp["stats"][str(r.action)] = grp["stats"].get(str(r.action), 0) + 1
            grp["entries_count"] += 1
            grp["params_touched"].add(str(r.param_name))
            if r.reverted_at is not None:
                grp["reverted_count"] += 1
            if bool(r.is_revert):
                grp["is_revert_count"] += 1
            if r.created_at < grp["started_at"]:
                grp["started_at"] = r.created_at
            if r.created_at > grp["ended_at"]:
                grp["ended_at"] = r.created_at
            if len(grp["preview_rows"]) < preview_size:
                grp["preview_rows"].append(r)

        total_batches = len(order)
        page_keys = order[offset : offset + max(1, min(limit, 200))]

        result: list[dict] = []
        for key in page_keys:
            grp = groups[key]
            result.append(
                {
                    "batch_id": grp["batch_id"],
                    "batch_label": grp["batch_label"],
                    "changed_by": grp["changed_by"],
                    "source": grp["source"],
                    "started_at": grp["started_at"],
                    "ended_at": grp["ended_at"],
                    "stats": grp["stats"],
                    "params_touched": sorted(grp["params_touched"]),
                    "entries_count": grp["entries_count"],
                    "preview": grp["preview_rows"],
                    "is_revert": grp["is_revert_count"] == grp["entries_count"]
                    and grp["entries_count"] > 0,
                    "fully_reverted": grp["reverted_count"] == grp["entries_count"]
                    and grp["entries_count"] > 0,
                    "reverted_count": grp["reverted_count"],
                }
            )
        return result, total_batches, total_entries

    # ------------------------------------------------------------------
    # Facets
    # ------------------------------------------------------------------

    @staticmethod
    def list_facets(db: Session, *, scenario_id: int) -> dict:
        """Valores únicos disponibles en la auditoría del escenario."""
        base_where = OsemosysParamValueAudit.id_scenario == scenario_id

        def _distinct(column) -> list:
            stmt = (
                select(column)
                .where(base_where)
                .where(column.is_not(None))
                .distinct()
                .order_by(column.asc())
            )
            return [v for v in db.execute(stmt).scalars().all() if v is not None]

        param_names = _distinct(OsemosysParamValueAudit.param_name)
        changed_by = _distinct(OsemosysParamValueAudit.changed_by)
        sources = _distinct(OsemosysParamValueAudit.source)
        actions = _distinct(OsemosysParamValueAudit.action)

        # Facets de dimensiones desde dimensions_json (colectado en Python para
        # ser dialect-agnóstico; volumen acotado por escenario).
        dim_stmt = (
            select(OsemosysParamValueAudit.dimensions_json)
            .where(base_where)
            .where(OsemosysParamValueAudit.dimensions_json.is_not(None))
        )
        regions: set[str] = set()
        techs: set[str] = set()
        fuels: set[str] = set()
        emissions: set[str] = set()
        udcs: set[str] = set()
        years: set[int] = set()
        for (raw,) in db.execute(dim_stmt).all():
            d = raw if isinstance(raw, dict) else None
            if not d:
                continue
            if d.get("region_name"):
                regions.add(str(d["region_name"]))
            if d.get("technology_name"):
                techs.add(str(d["technology_name"]))
            if d.get("fuel_name"):
                fuels.add(str(d["fuel_name"]))
            if d.get("emission_name"):
                emissions.add(str(d["emission_name"]))
            if d.get("udc_name"):
                udcs.add(str(d["udc_name"]))
            if d.get("year") is not None:
                try:
                    years.add(int(d["year"]))
                except (TypeError, ValueError):
                    pass

        date_range = db.execute(
            select(
                func.min(OsemosysParamValueAudit.created_at),
                func.max(OsemosysParamValueAudit.created_at),
            ).where(base_where)
        ).one()

        return {
            "param_names": param_names,
            "changed_by": changed_by,
            "sources": sources,
            "actions": actions,
            "region_names": sorted(regions),
            "technology_names": sorted(techs),
            "fuel_names": sorted(fuels),
            "emission_names": sorted(emissions),
            "udc_names": sorted(udcs),
            "years": sorted(years),
            "date_min": date_range[0],
            "date_max": date_range[1],
        }


def sa_int_type():
    """Tipo INTEGER reutilizable para casts en queries (importación tardía)."""
    from sqlalchemy import Integer

    return Integer
