"""Endpoints administrativos de configuración runtime del sistema."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_system_settings_manager
from app.core.config import get_settings
from app.db.session import get_db
from app.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.system_setting import SolverSettingsPublic, SolverSettingsUpdate
from app.services.system_settings_service import SystemSettingsService
from app.simulation.core.solver_config import (
    SOLVER_HIGHS_CROSSOVER_KEY,
    SOLVER_HIGHS_IPM_TOL_KEY,
    SOLVER_HIGHS_METHOD_KEY,
    SOLVER_HIGHS_PARALLEL_KEY,
    SOLVER_HIGHS_PRESOLVE_KEY,
    SOLVER_HIGHS_PRIMAL_TOL_KEY,
    SOLVER_HIGHS_TIME_LIMIT_KEY,
    SOLVER_HIGHS_USE_DIRECT_KEY,
    SOLVER_THREADS_KEY,
    resolve_highs_config,
)

router = APIRouter(prefix="/admin/system-settings")


def _hardware_thread_limit() -> int:
    """Devuelve CPUs visibles para este proceso."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except Exception:
        return max(1, os.cpu_count() or 1)


def _effective_solver_threads(requested_threads: int) -> int:
    """Aplica el mismo cap visible por hardware usado en la vista admin."""
    hardware = _hardware_thread_limit()
    if requested_threads <= 0:
        return hardware
    return min(requested_threads, hardware)


def _latest_updated(db: Session) -> tuple[object | None, object | None]:
    keys = [
        SOLVER_THREADS_KEY,
        SOLVER_HIGHS_METHOD_KEY,
        SOLVER_HIGHS_PRESOLVE_KEY,
        SOLVER_HIGHS_PARALLEL_KEY,
        SOLVER_HIGHS_CROSSOVER_KEY,
        SOLVER_HIGHS_USE_DIRECT_KEY,
        SOLVER_HIGHS_TIME_LIMIT_KEY,
        SOLVER_HIGHS_IPM_TOL_KEY,
        SOLVER_HIGHS_PRIMAL_TOL_KEY,
    ]
    latest_at = None
    latest_by = None
    for key in keys:
        row = SystemSettingsService.get_raw(db, key)
        if row is None or row.updated_at is None:
            continue
        if latest_at is None or row.updated_at >= latest_at:
            latest_at = row.updated_at
            latest_by = row.updated_by
    return latest_at, latest_by


def _to_public(
    db: Session,
    *,
    value: int | None = None,
    updated_at=None,
    updated_by_id=None,
) -> SolverSettingsPublic:
    cfg = resolve_highs_config(get_settings())
    if value is None:
        solver_threads = cfg.threads
        latest_at, latest_by = _latest_updated(db)
    else:
        solver_threads = value
        latest_at, latest_by = updated_at, updated_by_id
    username: str | None = None
    if latest_by is not None:
        user = UserRepository.get_by_id(db, latest_by)
        if user is not None:
            username = user.username
    return SolverSettingsPublic(
        solver_threads=solver_threads,
        hardware_thread_limit=_hardware_thread_limit(),
        effective_threads_preview=_effective_solver_threads(solver_threads),
        highs_method=cfg.method,  # type: ignore[arg-type]
        highs_presolve=cfg.presolve,  # type: ignore[arg-type]
        highs_parallel=cfg.parallel,  # type: ignore[arg-type]
        highs_run_crossover=cfg.run_crossover,  # type: ignore[arg-type]
        highs_use_direct=cfg.use_direct,
        highs_time_limit=cfg.time_limit,
        highs_ipm_optimality_tolerance=cfg.ipm_optimality_tolerance,
        highs_primal_feasibility_tolerance=cfg.primal_feasibility_tolerance,
        updated_at=latest_at,  # type: ignore[arg-type]
        updated_by_username=username,
    )


@router.get("/solver", response_model=SolverSettingsPublic)
def get_solver_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_system_settings_manager),
) -> SolverSettingsPublic:
    """Devuelve la configuración runtime del solver."""
    return _to_public(db)


@router.patch("/solver", response_model=SolverSettingsPublic)
def update_solver_settings(
    payload: SolverSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_system_settings_manager),
) -> SolverSettingsPublic:
    """Actualiza opciones runtime del solver multihilo."""
    updates = {
        SOLVER_THREADS_KEY: payload.solver_threads,
        SOLVER_HIGHS_METHOD_KEY: payload.highs_method,
        SOLVER_HIGHS_PRESOLVE_KEY: payload.highs_presolve,
        SOLVER_HIGHS_PARALLEL_KEY: payload.highs_parallel,
        SOLVER_HIGHS_CROSSOVER_KEY: payload.highs_run_crossover,
        SOLVER_HIGHS_USE_DIRECT_KEY: payload.highs_use_direct,
        SOLVER_HIGHS_TIME_LIMIT_KEY: payload.highs_time_limit,
        SOLVER_HIGHS_IPM_TOL_KEY: payload.highs_ipm_optimality_tolerance,
        SOLVER_HIGHS_PRIMAL_TOL_KEY: payload.highs_primal_feasibility_tolerance,
    }
    for key, value in updates.items():
        if value is None:
            continue
        SystemSettingsService.set_value(
            db,
            key=key,
            value=value,
            updated_by=current_user.id,
        )
    return _to_public(db)
