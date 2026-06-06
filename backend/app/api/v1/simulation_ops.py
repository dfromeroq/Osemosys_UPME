"""Operational endpoints for simulation queues across environments."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_system_settings_manager
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.models import User
from app.services.simulation_ops_service import SimulationOpsService

router = APIRouter(prefix="/simulation-ops")


@router.get("/dashboard")
def get_simulation_ops_dashboard(
    include_remotes: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: User = Depends(get_system_settings_manager),
) -> dict:
    """Aggregated queue/resource dashboard for local and configured remotes."""
    return SimulationOpsService.dashboard(db, include_remotes=include_remotes)


@router.post("/jobs/{job_id}/cancel")
def cancel_local_simulation_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_system_settings_manager),
) -> dict:
    """Cancel a job in the current environment, bypassing owner restrictions."""
    try:
        return SimulationOpsService.cancel_local_job(db, job_id=job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/environments/{environment}/jobs/{job_id}/cancel")
def cancel_environment_simulation_job(
    environment: str,
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_system_settings_manager),
) -> dict:
    """Cancel a job in the selected local or configured remote environment."""
    try:
        return SimulationOpsService.cancel_job(db, environment=environment, job_id=job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
