"""Operational endpoints for simulation queues across environments."""

from __future__ import annotations

from hmac import compare_digest

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_system_settings_manager
from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.models import User
from app.services.simulation_ops_service import SimulationOpsService

router = APIRouter(prefix="/simulation-ops")
ops_bearer = HTTPBearer(auto_error=False)


def require_simulation_ops_access(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(ops_bearer),
) -> User | None:
    """Allow either a system-settings admin JWT or a configured ops shared token."""
    token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    shared_token = get_settings().simulation_ops_shared_token.strip()
    if shared_token and token and compare_digest(token, shared_token):
        return None
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se pudieron validar las credenciales",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_system_settings_manager(get_current_user(db, token))


@router.get("/dashboard")
def get_simulation_ops_dashboard(
    include_remotes: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: User | None = Depends(require_simulation_ops_access),
) -> dict:
    """Aggregated queue/resource dashboard for local and configured remotes."""
    return SimulationOpsService.dashboard(db, include_remotes=include_remotes)


@router.post("/jobs/{job_id}/cancel")
def cancel_local_simulation_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_simulation_ops_access),
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
    _: User | None = Depends(require_simulation_ops_access),
) -> dict:
    """Cancel a job in the selected local or configured remote environment."""
    try:
        return SimulationOpsService.cancel_job(db, environment=environment, job_id=job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
