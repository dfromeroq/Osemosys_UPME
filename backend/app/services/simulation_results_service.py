"""Servicio para exponer resultados de simulación en formato wide.

Pivotea filas de ``osemosys_output_param_value`` por dimensiones (variable,
region, tecnología, fuel, emission, timeslice, mode, storage, season, daytype,
bracket) con años como columnas. Espejo de
``ScenarioService.list_osemosys_values_wide`` adaptado a la tabla de resultados.

Solo lectura: el modelo de datos de resultados es inmutable.
"""

from __future__ import annotations

import io
import logging
from typing import Iterable

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models import (
    Dailytimebracket,
    Daytype,
    Emission,
    Fuel,
    ModeOfOperation,
    OsemosysOutputParamValue,
    Region,
    Season,
    StorageSet,
    Technology,
    Timeslice,
    User,
)
from app.repositories.simulation_repository import SimulationRepository

logger = logging.getLogger(__name__)


def _eq_or_is_null(column, value):
    """`column = value` o `column IS NULL` según el valor dado."""
    if value is None:
        return column.is_(None)
    return column == value


def _value_rule_clause(value_col, op: str, val: float | None):
    """Construye comparación sobre `value` según la regla (gt/lt/eq/nonzero/...)."""
    op = (op or "").lower()
    if op == "nonzero":
        return value_col != 0
    if op == "zero":
        return value_col == 0
    if val is None:
        return None
    if op == "gt":
        return value_col > val
    if op == "lt":
        return value_col < val
    if op == "gte":
        return value_col >= val
    if op == "lte":
        return value_col <= val
    if op == "eq":
        return value_col == val
    if op == "ne":
        return value_col != val
    return None


# Agrupación: tupla de columnas que definen una fila wide.
_GROUP_COLS = (
    OsemosysOutputParamValue.variable_name,
    OsemosysOutputParamValue.id_region,
    OsemosysOutputParamValue.id_technology,
    OsemosysOutputParamValue.id_fuel,
    OsemosysOutputParamValue.id_emission,
    OsemosysOutputParamValue.id_timeslice,
    OsemosysOutputParamValue.id_mode_of_operation,
    OsemosysOutputParamValue.id_storage,
    OsemosysOutputParamValue.id_season,
    OsemosysOutputParamValue.id_daytype,
    OsemosysOutputParamValue.id_dailytimebracket,
)

# Valor especial en filtros CSV para indicar "esta columna IS NULL".
_NULL_SENTINEL = "__NULL__"


def _in_or_isnull(column, names: list[int | None]):
    """Construye clausula IN que acepta NULL con el sentinel __NULL__ ya convertido."""
    non_null = [v for v in names if v is not None]
    has_null = any(v is None for v in names)
    clauses = []
    if non_null:
        clauses.append(column.in_(non_null))
    if has_null:
        clauses.append(column.is_(None))
    if not clauses:
        from sqlalchemy import literal
        return literal(False)
    return or_(*clauses) if len(clauses) > 1 else clauses[0]


def _resolve_catalog_ids(
    db: Session,
    *,
    model_cls,
    attr: str,
    names: list[str] | None,
) -> list[int | None] | None:
    """Convierte nombres en ids usando el catálogo dado. Respeta sentinel NULL."""
    if not names:
        return None
    resolved: list[int | None] = []
    non_null = [n for n in names if n != _NULL_SENTINEL]
    if non_null:
        col = getattr(model_cls, attr)
        rows = db.query(model_cls.id, col).filter(col.in_(non_null)).all()
        resolved.extend(int(r.id) for r in rows)
    if any(n == _NULL_SENTINEL for n in names):
        resolved.append(None)
    return resolved


class SimulationResultsService:
    """Reglas de negocio para el Data Explorer de resultados."""

    # ------------------------------------------------------------------
    #  Permisos
    # ------------------------------------------------------------------

    @staticmethod
    def _require_job(db: Session, *, job_id: int, current_user: User):
        """Valida que `current_user` puede leer `job_id` y que ya terminó bien.

        Usa la misma lógica de visibilidad que ``GET /simulations/{id}``.
        """
        visible = SimulationRepository.get_job_visible(
            db, job_id=job_id, current_user_id=current_user.id
        )
        if not visible:
            raise NotFoundError("Simulacion no encontrada.")
        job, *_ = visible
        if str(job.status).upper() != "SUCCEEDED":
            raise ForbiddenError(
                "El Data Explorer solo está disponible para simulaciones completadas.",
            )
        return job

    # ------------------------------------------------------------------
    #  Construcción de filtros
    # ------------------------------------------------------------------

    @staticmethod
    def _wide_filter_clauses(
        db: Session | None,
        *,
        job_id: int,
        variable_name: str | None,
        variable_names: list[str] | None,
        region_names: list[str] | None,
        technology_names: list[str] | None,
        fuel_names: list[str] | None,
        emission_names: list[str] | None,
        timeslice_names: list[str] | None,
        mode_names: list[str] | None,
        storage_names: list[str] | None,
        year_rules: list[tuple[int, str, float | None]] | None,
        skip_column: str | None = None,
    ) -> tuple[list, bool]:
        """Construye la lista de cláusulas WHERE.

        `skip_column` omite la cláusula de esa columna — se usa en los
        facets para evitar auto-filtrado (exclude-self).
        """
        clauses = [OsemosysOutputParamValue.id_simulation_job == job_id]
        needs_search = False

        if skip_column != "variable_name":
            if variable_name:
                clauses.append(
                    OsemosysOutputParamValue.variable_name == variable_name
                )
            if variable_names:
                clauses.append(OsemosysOutputParamValue.variable_name.in_(variable_names))

        if db is not None:
            _catalog_filters = [
                ("region_names", region_names, Region, "name", OsemosysOutputParamValue.id_region),
                ("technology_names", technology_names, Technology, "name", OsemosysOutputParamValue.id_technology),
                ("fuel_names", fuel_names, Fuel, "name", OsemosysOutputParamValue.id_fuel),
                ("emission_names", emission_names, Emission, "name", OsemosysOutputParamValue.id_emission),
                ("timeslice_names", timeslice_names, Timeslice, "code", OsemosysOutputParamValue.id_timeslice),
                ("mode_names", mode_names, ModeOfOperation, "code", OsemosysOutputParamValue.id_mode_of_operation),
                ("storage_names", storage_names, StorageSet, "code", OsemosysOutputParamValue.id_storage),
            ]
            for col_key, names, model_cls, attr, col in _catalog_filters:
                if skip_column == col_key:
                    continue
                ids = _resolve_catalog_ids(
                    db, model_cls=model_cls, attr=attr, names=names
                )
                if ids is not None:
                    clauses.append(_in_or_isnull(col, ids))

        if year_rules and db is not None:
            clauses.extend(
                SimulationResultsService._year_rules_clauses(db, job_id, year_rules)
            )

        return clauses, needs_search

    @staticmethod
    def _year_rules_clauses(
        db: Session,
        job_id: int,
        year_rules: list[tuple[int, str, float | None]] | None,
    ) -> list:
        """Filtra por reglas de año usando intersección de tuplas de dimensión.

        Una sola regla → subquery `id IN (...)`. Múltiples reglas → intersecta
        en Python las tuplas de dimensión que matchean cada regla y luego
        OR-ands reconstruidos.
        """
        from sqlalchemy import literal, select
        if not year_rules:
            return []

        valid: list[tuple[int, str, float | None]] = []
        for year, op, val in year_rules:
            if _value_rule_clause(OsemosysOutputParamValue.value, op, val) is not None:
                valid.append((year, op, val))
        if not valid:
            return []

        if len(valid) == 1:
            year, op, val = valid[0]
            rule = _value_rule_clause(OsemosysOutputParamValue.value, op, val)
            return [
                OsemosysOutputParamValue.id.in_(
                    select(OsemosysOutputParamValue.id).where(
                        OsemosysOutputParamValue.id_simulation_job == job_id,
                        OsemosysOutputParamValue.year == int(year),
                        rule,
                    )
                )
            ]

        surviving: set[tuple] | None = None
        for year, op, val in valid:
            rule = _value_rule_clause(OsemosysOutputParamValue.value, op, val)
            q = (
                db.query(*_GROUP_COLS)
                .distinct()
                .filter(
                    OsemosysOutputParamValue.id_simulation_job == job_id,
                    OsemosysOutputParamValue.year == int(year),
                    rule,
                )
            )
            tuples = {tuple(row) for row in q.all()}
            surviving = tuples if surviving is None else (surviving & tuples)
            if not surviving:
                break

        if not surviving:
            return [literal(False)]

        conds = []
        for t in surviving:
            conds.append(
                and_(
                    OsemosysOutputParamValue.variable_name == t[0],
                    _eq_or_is_null(OsemosysOutputParamValue.id_region, t[1]),
                    _eq_or_is_null(OsemosysOutputParamValue.id_technology, t[2]),
                    _eq_or_is_null(OsemosysOutputParamValue.id_fuel, t[3]),
                    _eq_or_is_null(OsemosysOutputParamValue.id_emission, t[4]),
                    _eq_or_is_null(OsemosysOutputParamValue.id_timeslice, t[5]),
                    _eq_or_is_null(OsemosysOutputParamValue.id_mode_of_operation, t[6]),
                    _eq_or_is_null(OsemosysOutputParamValue.id_storage, t[7]),
                    _eq_or_is_null(OsemosysOutputParamValue.id_season, t[8]),
                    _eq_or_is_null(OsemosysOutputParamValue.id_daytype, t[9]),
                    _eq_or_is_null(OsemosysOutputParamValue.id_dailytimebracket, t[10]),
                )
            )
        return [or_(*conds)]

    # ------------------------------------------------------------------
    #  Wide list
    # ------------------------------------------------------------------

    @staticmethod
    def list_output_values_wide(
        db: Session,
        *,
        job_id: int,
        current_user: User,
        variable_name: str | None = None,
        variable_names: list[str] | None = None,
        region_names: list[str] | None = None,
        technology_names: list[str] | None = None,
        fuel_names: list[str] | None = None,
        emission_names: list[str] | None = None,
        timeslice_names: list[str] | None = None,
        mode_names: list[str] | None = None,
        storage_names: list[str] | None = None,
        year_rules: list[tuple[int, str, float | None]] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        """Paginación + pivot en formato wide.

        Años como columnas, combinación completa de dimensiones como fila.
        """
        SimulationResultsService._require_job(
            db, job_id=job_id, current_user=current_user
        )

        safe_limit = max(1, min(limit, 500))
        safe_offset = max(0, offset)

        clauses, _ = SimulationResultsService._wide_filter_clauses(
            db,
            job_id=job_id,
            variable_name=variable_name,
            variable_names=variable_names,
            region_names=region_names,
            technology_names=technology_names,
            fuel_names=fuel_names,
            emission_names=emission_names,
            timeslice_names=timeslice_names,
            mode_names=mode_names,
            storage_names=storage_names,
            year_rules=year_rules,
        )

        # 1. Page de grupos distintos (ordenados).
        groups_query = db.query(*_GROUP_COLS).distinct().filter(*clauses).order_by(
            OsemosysOutputParamValue.variable_name.asc(),
            OsemosysOutputParamValue.id_region.asc().nulls_last(),
            OsemosysOutputParamValue.id_technology.asc().nulls_last(),
            OsemosysOutputParamValue.id_fuel.asc().nulls_last(),
            OsemosysOutputParamValue.id_emission.asc().nulls_last(),
            OsemosysOutputParamValue.id_timeslice.asc().nulls_last(),
            OsemosysOutputParamValue.id_mode_of_operation.asc().nulls_last(),
            OsemosysOutputParamValue.id_storage.asc().nulls_last(),
            OsemosysOutputParamValue.id_season.asc().nulls_last(),
            OsemosysOutputParamValue.id_daytype.asc().nulls_last(),
            OsemosysOutputParamValue.id_dailytimebracket.asc().nulls_last(),
        )
        group_rows = groups_query.offset(safe_offset).limit(safe_limit).all()

        # 2. Count total.
        count_subq = (
            db.query(*_GROUP_COLS).distinct().filter(*clauses).subquery()
        )
        total = db.query(func.count()).select_from(count_subq).scalar() or 0

        # 3. Años visibles (independiente de year_rules para header consistente).
        clauses_sin_year_rules, _ = SimulationResultsService._wide_filter_clauses(
            db,
            job_id=job_id,
            variable_name=variable_name,
            variable_names=variable_names,
            region_names=region_names,
            technology_names=technology_names,
            fuel_names=fuel_names,
            emission_names=emission_names,
            timeslice_names=timeslice_names,
            mode_names=mode_names,
            storage_names=storage_names,
            year_rules=None,
        )
        years_rows = (
            db.query(OsemosysOutputParamValue.year)
            .filter(*clauses_sin_year_rules)
            .distinct()
            .all()
        )
        raw_years = [r[0] for r in years_rows]
        has_scalar = any(y is None for y in raw_years)
        years = sorted(y for y in raw_years if y is not None)

        if not group_rows:
            return {
                "items": [],
                "total": int(total),
                "offset": safe_offset,
                "limit": safe_limit,
                "years": years,
                "has_scalar": has_scalar,
            }

        # 4. Celdas para los grupos paginados.
        group_conditions = []
        for g in group_rows:
            group_conditions.append(
                and_(
                    OsemosysOutputParamValue.variable_name == g.variable_name,
                    _eq_or_is_null(OsemosysOutputParamValue.id_region, g.id_region),
                    _eq_or_is_null(OsemosysOutputParamValue.id_technology, g.id_technology),
                    _eq_or_is_null(OsemosysOutputParamValue.id_fuel, g.id_fuel),
                    _eq_or_is_null(OsemosysOutputParamValue.id_emission, g.id_emission),
                    _eq_or_is_null(OsemosysOutputParamValue.id_timeslice, g.id_timeslice),
                    _eq_or_is_null(OsemosysOutputParamValue.id_mode_of_operation, g.id_mode_of_operation),
                    _eq_or_is_null(OsemosysOutputParamValue.id_storage, g.id_storage),
                    _eq_or_is_null(OsemosysOutputParamValue.id_season, g.id_season),
                    _eq_or_is_null(OsemosysOutputParamValue.id_daytype, g.id_daytype),
                    _eq_or_is_null(OsemosysOutputParamValue.id_dailytimebracket, g.id_dailytimebracket),
                )
            )

        cells_rows = (
            db.query(
                OsemosysOutputParamValue,
                Region.name.label("region_name"),
                Technology.name.label("technology_name"),
                Fuel.name.label("fuel_name"),
                Emission.name.label("emission_name"),
                Timeslice.code.label("timeslice_name"),
                ModeOfOperation.code.label("mode_name"),
                StorageSet.code.label("storage_name"),
                Season.code.label("season_name"),
                Daytype.code.label("daytype_name"),
                Dailytimebracket.code.label("bracket_name"),
            )
            .outerjoin(Region, OsemosysOutputParamValue.id_region == Region.id)
            .outerjoin(Technology, OsemosysOutputParamValue.id_technology == Technology.id)
            .outerjoin(Fuel, OsemosysOutputParamValue.id_fuel == Fuel.id)
            .outerjoin(Emission, OsemosysOutputParamValue.id_emission == Emission.id)
            .outerjoin(Timeslice, OsemosysOutputParamValue.id_timeslice == Timeslice.id)
            .outerjoin(ModeOfOperation, OsemosysOutputParamValue.id_mode_of_operation == ModeOfOperation.id)
            .outerjoin(StorageSet, OsemosysOutputParamValue.id_storage == StorageSet.id)
            .outerjoin(Season, OsemosysOutputParamValue.id_season == Season.id)
            .outerjoin(Daytype, OsemosysOutputParamValue.id_daytype == Daytype.id)
            .outerjoin(Dailytimebracket, OsemosysOutputParamValue.id_dailytimebracket == Dailytimebracket.id)
            .filter(OsemosysOutputParamValue.id_simulation_job == job_id)
            .filter(or_(*group_conditions))
            .all()
        )

        def _group_key(row) -> tuple:
            return (
                row.variable_name,
                row.id_region,
                row.id_technology,
                row.id_fuel,
                row.id_emission,
                row.id_timeslice,
                row.id_mode_of_operation,
                row.id_storage,
                row.id_season,
                row.id_daytype,
                row.id_dailytimebracket,
            )

        groups_map: dict[tuple, dict] = {}
        for r in cells_rows:
            v = r.OsemosysOutputParamValue
            key = _group_key(v)
            g = groups_map.get(key)
            if g is None:
                g = {
                    "variable_name": v.variable_name,
                    "region_name": r.region_name,
                    "technology_name": r.technology_name or v.technology_name,
                    "fuel_name": r.fuel_name or v.fuel_name,
                    "emission_name": r.emission_name or v.emission_name,
                    "timeslice_name": r.timeslice_name,
                    "mode_name": r.mode_name,
                    "storage_name": r.storage_name,
                    "season_name": r.season_name,
                    "daytype_name": r.daytype_name,
                    "bracket_name": r.bracket_name,
                    "cells": {},
                }
                groups_map[key] = g
            year_key = "scalar" if v.year is None else str(int(v.year))
            g["cells"][year_key] = {"id": int(v.id), "value": float(v.value)}

        items: list[dict] = []
        for g in group_rows:
            key = _group_key(g)
            entry = groups_map.get(key)
            if entry is None:
                continue
            entry["group_key"] = "|".join(
                "" if part is None else str(part) for part in key
            )
            items.append(entry)

        return {
            "items": items,
            "total": int(total),
            "offset": safe_offset,
            "limit": safe_limit,
            "years": years,
            "has_scalar": has_scalar,
        }

    # ------------------------------------------------------------------
    #  Facets (valores únicos por columna para popovers)
    # ------------------------------------------------------------------

    @staticmethod
    def list_output_wide_facets(
        db: Session,
        *,
        job_id: int,
        current_user: User,
        variable_name: str | None = None,
        variable_names: list[str] | None = None,
        region_names: list[str] | None = None,
        technology_names: list[str] | None = None,
        fuel_names: list[str] | None = None,
        emission_names: list[str] | None = None,
        timeslice_names: list[str] | None = None,
        mode_names: list[str] | None = None,
        storage_names: list[str] | None = None,
        year_rules: list[tuple[int, str, float | None]] | None = None,
        limit_per_column: int = 500,
    ) -> dict:
        """Valores únicos por columna aplicando el resto de filtros (exclude-self).

        El facet para la columna ``X`` se calcula ignorando el filtro activo
        sobre ``X`` (exclude-self) pero respetando los filtros sobre otras
        columnas — esto permite que los popovers muestren opciones que
        estrecha en función de lo ya seleccionado en otras columnas.
        """
        SimulationResultsService._require_job(
            db, job_id=job_id, current_user=current_user
        )

        lpc = max(1, min(int(limit_per_column or 500), 2000))

        shared_filter_kwargs = dict(
            job_id=job_id,
            variable_name=variable_name,
            variable_names=variable_names,
            region_names=region_names,
            technology_names=technology_names,
            fuel_names=fuel_names,
            emission_names=emission_names,
            timeslice_names=timeslice_names,
            mode_names=mode_names,
            storage_names=storage_names,
            year_rules=year_rules,
        )

        def _distinct(col, skip_column: str, *extra_joins) -> list[str]:
            clauses, _ = SimulationResultsService._wide_filter_clauses(
                db, **shared_filter_kwargs, skip_column=skip_column
            )
            q = db.query(col).select_from(OsemosysOutputParamValue)
            for join_tgt, on_clause in extra_joins:
                q = q.outerjoin(join_tgt, on_clause)
            q = q.filter(*clauses, col.is_not(None)).distinct().order_by(col.asc()).limit(lpc)
            return [str(r[0]) for r in q.all() if r[0] is not None]

        return {
            "variable_names": _distinct(
                OsemosysOutputParamValue.variable_name, "variable_name"
            ),
            "region_names": _distinct(
                Region.name,
                "region_names",
                (Region, OsemosysOutputParamValue.id_region == Region.id),
            ),
            "technology_names": _distinct(
                Technology.name,
                "technology_names",
                (Technology, OsemosysOutputParamValue.id_technology == Technology.id),
            ),
            "fuel_names": _distinct(
                Fuel.name,
                "fuel_names",
                (Fuel, OsemosysOutputParamValue.id_fuel == Fuel.id),
            ),
            "emission_names": _distinct(
                Emission.name,
                "emission_names",
                (Emission, OsemosysOutputParamValue.id_emission == Emission.id),
            ),
            "timeslice_names": _distinct(
                Timeslice.code,
                "timeslice_names",
                (Timeslice, OsemosysOutputParamValue.id_timeslice == Timeslice.id),
            ),
            "mode_names": _distinct(
                ModeOfOperation.code,
                "mode_names",
                (ModeOfOperation, OsemosysOutputParamValue.id_mode_of_operation == ModeOfOperation.id),
            ),
            "storage_names": _distinct(
                StorageSet.code,
                "storage_names",
                (StorageSet, OsemosysOutputParamValue.id_storage == StorageSet.id),
            ),
        }

    # ------------------------------------------------------------------
    #  Totales por año (mismos filtros que wide)
    # ------------------------------------------------------------------

    @staticmethod
    def get_output_totals(
        db: Session,
        *,
        job_id: int,
        current_user: User,
        variable_name: str | None = None,
        variable_names: list[str] | None = None,
        region_names: list[str] | None = None,
        technology_names: list[str] | None = None,
        fuel_names: list[str] | None = None,
        emission_names: list[str] | None = None,
        timeslice_names: list[str] | None = None,
        mode_names: list[str] | None = None,
        storage_names: list[str] | None = None,
        year_rules: list[tuple[int, str, float | None]] | None = None,
    ) -> dict:
        """Suma de ``value`` agrupada por año (y escalar) tras aplicar filtros.

        Nota: la suma agrega filas heterogéneas — útil cuando el usuario
        restringe a una variable única. El frontend decide cuándo mostrar
        el total en función del contexto de filtros.
        """
        SimulationResultsService._require_job(
            db, job_id=job_id, current_user=current_user
        )

        clauses, _ = SimulationResultsService._wide_filter_clauses(
            db,
            job_id=job_id,
            variable_name=variable_name,
            variable_names=variable_names,
            region_names=region_names,
            technology_names=technology_names,
            fuel_names=fuel_names,
            emission_names=emission_names,
            timeslice_names=timeslice_names,
            mode_names=mode_names,
            storage_names=storage_names,
            year_rules=year_rules,
        )

        rows = (
            db.query(
                OsemosysOutputParamValue.year,
                func.sum(OsemosysOutputParamValue.value).label("total"),
                func.count().label("n"),
            )
            .filter(*clauses)
            .group_by(OsemosysOutputParamValue.year)
            .all()
        )

        years_map: dict[str, float] = {}
        scalar: float | None = None
        row_count = 0
        for r in rows:
            n = int(r.n or 0)
            row_count += n
            total = float(r.total or 0.0)
            if r.year is None:
                scalar = total
            else:
                years_map[str(int(r.year))] = total

        return {"years": years_map, "scalar": scalar, "row_count": row_count}

    # ------------------------------------------------------------------
    #  Export Excel
    # ------------------------------------------------------------------

    @staticmethod
    def export_output_values_xlsx(
        db: Session,
        *,
        job_id: int,
        current_user: User,
        variable_name: str | None = None,
        variable_names: list[str] | None = None,
        region_names: list[str] | None = None,
        technology_names: list[str] | None = None,
        fuel_names: list[str] | None = None,
        emission_names: list[str] | None = None,
        timeslice_names: list[str] | None = None,
        mode_names: list[str] | None = None,
        storage_names: list[str] | None = None,
        year_rules: list[tuple[int, str, float | None]] | None = None,
    ) -> bytes:
        """Exporta TODOS los resultados filtrados a un Excel wide (un solo sheet)."""
        import pandas as pd  # local — evita coste al arrancar FastAPI

        SimulationResultsService._require_job(
            db, job_id=job_id, current_user=current_user
        )

        clauses, _ = SimulationResultsService._wide_filter_clauses(
            db,
            job_id=job_id,
            variable_name=variable_name,
            variable_names=variable_names,
            region_names=region_names,
            technology_names=technology_names,
            fuel_names=fuel_names,
            emission_names=emission_names,
            timeslice_names=timeslice_names,
            mode_names=mode_names,
            storage_names=storage_names,
            year_rules=year_rules,
        )

        rows = (
            db.query(
                OsemosysOutputParamValue.variable_name,
                Region.name.label("region"),
                Technology.name.label("technology"),
                Fuel.name.label("fuel"),
                Emission.name.label("emission"),
                Timeslice.code.label("timeslice"),
                ModeOfOperation.code.label("mode"),
                StorageSet.code.label("storage"),
                Season.code.label("season"),
                Daytype.code.label("daytype"),
                Dailytimebracket.code.label("bracket"),
                OsemosysOutputParamValue.year,
                OsemosysOutputParamValue.value,
            )
            .outerjoin(Region, OsemosysOutputParamValue.id_region == Region.id)
            .outerjoin(Technology, OsemosysOutputParamValue.id_technology == Technology.id)
            .outerjoin(Fuel, OsemosysOutputParamValue.id_fuel == Fuel.id)
            .outerjoin(Emission, OsemosysOutputParamValue.id_emission == Emission.id)
            .outerjoin(Timeslice, OsemosysOutputParamValue.id_timeslice == Timeslice.id)
            .outerjoin(ModeOfOperation, OsemosysOutputParamValue.id_mode_of_operation == ModeOfOperation.id)
            .outerjoin(StorageSet, OsemosysOutputParamValue.id_storage == StorageSet.id)
            .outerjoin(Season, OsemosysOutputParamValue.id_season == Season.id)
            .outerjoin(Daytype, OsemosysOutputParamValue.id_daytype == Daytype.id)
            .outerjoin(Dailytimebracket, OsemosysOutputParamValue.id_dailytimebracket == Dailytimebracket.id)
            .filter(*clauses)
            .all()
        )

        if not rows:
            df_long = pd.DataFrame(
                columns=[
                    "variable_name", "region", "technology", "fuel", "emission",
                    "timeslice", "mode", "storage", "season", "daytype", "bracket",
                    "year", "value",
                ],
            )
        else:
            df_long = pd.DataFrame(
                [
                    {
                        "variable_name": r.variable_name,
                        "region": r.region,
                        "technology": r.technology,
                        "fuel": r.fuel,
                        "emission": r.emission,
                        "timeslice": r.timeslice,
                        "mode": r.mode,
                        "storage": r.storage,
                        "season": r.season,
                        "daytype": r.daytype,
                        "bracket": r.bracket,
                        "year": r.year,
                        "value": float(r.value),
                    }
                    for r in rows
                ]
            )

        dim_cols = [
            "variable_name", "region", "technology", "fuel", "emission",
            "timeslice", "mode", "storage", "season", "daytype", "bracket",
        ]

        if df_long.empty:
            df_wide = df_long
        else:
            # Pivotea a wide por año; "scalar" para año nulo.
            df_long["year_key"] = df_long["year"].apply(
                lambda v: "scalar" if v is None else str(int(v))
            )
            df_wide = (
                df_long.pivot_table(
                    index=dim_cols,
                    columns="year_key",
                    values="value",
                    aggfunc="first",
                    dropna=False,
                )
                .reset_index()
            )
            # Orden de columnas: dimensiones + scalar primero + años asc.
            year_cols = [c for c in df_wide.columns if c not in dim_cols]
            ordered_years = []
            if "scalar" in year_cols:
                ordered_years.append("scalar")
            ordered_years.extend(
                sorted(
                    [c for c in year_cols if c != "scalar"],
                    key=lambda x: int(x),
                )
            )
            df_wide = df_wide[dim_cols + ordered_years]

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            df_wide.to_excel(xw, sheet_name="Resultados", index=False)
        buf.seek(0)
        return buf.read()
