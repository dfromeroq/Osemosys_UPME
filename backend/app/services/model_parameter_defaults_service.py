"""Servicio de defaults versionados del modelo OSeMOSYS."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    ModelParameterCatalog,
    ModelParameterDefaultItem,
    ModelParameterDefaultVersion,
)
from app.services.system_settings_service import SystemSettingsService

ACTIVE_VERSION_KEY = "model_defaults.active_version_id"


@contextmanager
def model_defaults_runtime(db: Session) -> Iterator[dict[str, float]]:
    """Activa el mapa de defaults de la versión global durante el bloque (p. ej. import)."""
    from app.simulation.core.osemosys_defaults import reset_defaults_context, set_defaults_context

    _vid, defaults_map = ModelParameterDefaultsService.resolve_for_job(db, job_version_id=None)
    token = set_defaults_context(defaults_map)
    try:
        yield defaults_map
    finally:
        reset_defaults_context(token)


@dataclass(frozen=True)
class CatalogRowPublic:
    param_key: str
    pyomo_name: str
    index_dims: str
    category: str
    description: str | None
    value_type: str
    min_value: float | None
    max_value: float | None
    requires_storage: bool
    requires_udc: bool
    value: float


@dataclass(frozen=True)
class VersionSummary:
    id: int
    created_at: object
    created_by_username: str | None
    comment: str | None
    is_active: bool


class ModelParameterDefaultsService:
    @staticmethod
    def get_active_version_id(db: Session) -> int:
        version_id = SystemSettingsService.get_int(db, ACTIVE_VERSION_KEY, default=0)
        if version_id <= 0:
            latest = db.execute(
                select(ModelParameterDefaultVersion.id)
                .order_by(ModelParameterDefaultVersion.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest is None:
                raise RuntimeError(
                    "No hay versión de defaults OSeMOSYS; ejecute migraciones/seed.",
                )
            version_id = int(latest)
            SystemSettingsService.set_value(
                db,
                key=ACTIVE_VERSION_KEY,
                value=version_id,
                updated_by=None,
            )
        return version_id

    @staticmethod
    def get_defaults_map(db: Session, version_id: int | None = None) -> dict[str, float]:
        vid = version_id if version_id is not None else ModelParameterDefaultsService.get_active_version_id(db)
        rows = db.execute(
            select(ModelParameterDefaultItem.param_key, ModelParameterDefaultItem.value).where(
                ModelParameterDefaultItem.version_id == vid,
            ),
        ).all()
        return {str(k): float(v) for k, v in rows}

    @staticmethod
    def list_catalog_with_values(
        db: Session,
        *,
        version_id: int | None = None,
    ) -> list[CatalogRowPublic]:
        vid = version_id if version_id is not None else ModelParameterDefaultsService.get_active_version_id(db)
        values = ModelParameterDefaultsService.get_defaults_map(db, vid)
        catalog = db.execute(
            select(ModelParameterCatalog).order_by(
                ModelParameterCatalog.category,
                ModelParameterCatalog.pyomo_name,
            ),
        ).scalars().all()
        return [
            CatalogRowPublic(
                param_key=row.param_key,
                pyomo_name=row.pyomo_name,
                index_dims=row.index_dims,
                category=row.category,
                description=row.description,
                value_type=row.value_type,
                min_value=row.min_value,
                max_value=row.max_value,
                requires_storage=row.requires_storage,
                requires_udc=row.requires_udc,
                value=values.get(row.param_key, 0.0),
            )
            for row in catalog
        ]

    @staticmethod
    def list_versions(db: Session, *, limit: int = 50) -> list[VersionSummary]:
        active_id = ModelParameterDefaultsService.get_active_version_id(db)
        rows = db.execute(
            select(ModelParameterDefaultVersion)
            .order_by(ModelParameterDefaultVersion.id.desc())
            .limit(limit),
        ).scalars().all()
        from app.repositories.user_repository import UserRepository

        out: list[VersionSummary] = []
        for row in rows:
            username: str | None = None
            if row.created_by is not None:
                user = UserRepository.get_by_id(db, row.created_by)
                if user is not None:
                    username = user.username
            out.append(
                VersionSummary(
                    id=row.id,
                    created_at=row.created_at,
                    created_by_username=username,
                    comment=row.comment,
                    is_active=row.id == active_id,
                ),
            )
        return out

    @staticmethod
    def get_version_detail(
        db: Session,
        version_id: int,
    ) -> tuple[ModelParameterDefaultVersion, dict[str, float]]:
        version = db.execute(
            select(ModelParameterDefaultVersion)
            .options(joinedload(ModelParameterDefaultVersion.items))
            .where(ModelParameterDefaultVersion.id == version_id),
        ).unique().scalar_one_or_none()
        if version is None:
            raise ValueError(f"Versión {version_id} no encontrada")
        values = {item.param_key: float(item.value) for item in version.items}
        return version, values

    @staticmethod
    def _validate_items(
        db: Session,
        items: list[dict[str, Any]],
    ) -> dict[str, float]:
        catalog_rows = {
            row.param_key: row
            for row in db.execute(select(ModelParameterCatalog)).scalars().all()
        }
        if not catalog_rows:
            raise ValueError("Catálogo de parámetros vacío")

        normalized: dict[str, float] = {}
        seen: set[str] = set()
        for raw in items:
            key = str(raw.get("param_key", "")).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            if key not in catalog_rows:
                raise ValueError(f"Parámetro desconocido: {key}")
            try:
                value = float(raw["value"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Valor inválido para {key}") from exc
            meta = catalog_rows[key]
            if meta.min_value is not None and value < meta.min_value:
                raise ValueError(
                    f"{meta.pyomo_name}: valor {value} < mínimo {meta.min_value}",
                )
            if meta.max_value is not None and value > meta.max_value:
                raise ValueError(
                    f"{meta.pyomo_name}: valor {value} > máximo {meta.max_value}",
                )
            normalized[key] = value

        missing = set(catalog_rows) - set(normalized)
        if missing:
            active = ModelParameterDefaultsService.get_defaults_map(db)
            for key in missing:
                if key not in active:
                    raise ValueError(f"Falta valor para parámetro {key}")
                normalized[key] = active[key]
        return normalized

    @staticmethod
    def create_version_from_items(
        db: Session,
        *,
        items: list[dict[str, Any]],
        user_id: uuid.UUID | None,
        comment: str | None = None,
    ) -> int:
        values = ModelParameterDefaultsService._validate_items(db, items)
        version = ModelParameterDefaultVersion(
            created_by=user_id,
            comment=(comment or "").strip() or None,
        )
        db.add(version)
        db.flush()
        for param_key, value in values.items():
            db.add(
                ModelParameterDefaultItem(
                    version_id=version.id,
                    param_key=param_key,
                    value=value,
                ),
            )
        SystemSettingsService.set_value(
            db,
            key=ACTIVE_VERSION_KEY,
            value=version.id,
            updated_by=user_id,
        )
        db.commit()
        db.refresh(version)
        return int(version.id)

    @staticmethod
    def resolve_for_job(
        db: Session,
        *,
        job_version_id: int | None,
    ) -> tuple[int, dict[str, float]]:
        """Mapa de defaults para una corrida: versión del job o activa."""
        if job_version_id is not None:
            return job_version_id, ModelParameterDefaultsService.get_defaults_map(
                db, job_version_id,
            )
        active = ModelParameterDefaultsService.get_active_version_id(db)
        return active, ModelParameterDefaultsService.get_defaults_map(db, active)
