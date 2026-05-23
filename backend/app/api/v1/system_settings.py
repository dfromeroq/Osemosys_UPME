"""Endpoints administrativos de configuración runtime del sistema."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_system_settings_manager
from app.db.session import get_db
from app.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.system_setting import SolverSettingsPublic, SolverSettingsUpdate
from app.services.system_settings_service import (
    SOLVER_THREADS_KEY,
    SystemSettingsService,
)

router = APIRouter(prefix="/admin/system-settings")


def _to_public(
    db: Session, *, value: int, updated_at, updated_by_id
) -> SolverSettingsPublic:
    username: str | None = None
    if updated_by_id is not None:
        user = UserRepository.get_by_id(db, updated_by_id)
        if user is not None:
            username = user.username
    return SolverSettingsPublic(
        solver_threads=value,
        updated_at=updated_at,
        updated_by_username=username,
    )


@router.get("/solver", response_model=SolverSettingsPublic)
def get_solver_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_system_settings_manager),
) -> SolverSettingsPublic:
    """Devuelve la configuración runtime del solver."""
    row = SystemSettingsService.get_raw(db, SOLVER_THREADS_KEY)
    if row is None:
        return SolverSettingsPublic(solver_threads=0)
    try:
        threads = int((row.value or "0").strip())
    except ValueError:
        threads = 0
    return _to_public(
        db,
        value=threads,
        updated_at=row.updated_at,
        updated_by_id=row.updated_by,
    )


@router.patch("/solver", response_model=SolverSettingsPublic)
def update_solver_settings(
    payload: SolverSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_system_settings_manager),
) -> SolverSettingsPublic:
    """Actualiza el número de hilos a entregar al solver multihilo."""
    row = SystemSettingsService.set_value(
        db,
        key=SOLVER_THREADS_KEY,
        value=payload.solver_threads,
        updated_by=current_user.id,
    )
    return _to_public(
        db,
        value=payload.solver_threads,
        updated_at=row.updated_at,
        updated_by_id=row.updated_by,
    )
