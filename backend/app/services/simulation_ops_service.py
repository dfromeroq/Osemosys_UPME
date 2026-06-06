"""Operational dashboard and controls for simulation queues."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models import SimulationJob
from app.repositories.simulation_repository import SimulationRepository
from app.services.docker_metrics_service import DockerMetricsService
from app.simulation.celery_app import celery_app

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("QUEUED", "RUNNING")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _runtime_summary(job: SimulationJob) -> dict[str, Any]:
    timings = job.model_timings_json if isinstance(job.model_timings_json, dict) else {}
    context = timings.get("runtime_context")
    samples = timings.get("runtime_resource_samples")
    if not isinstance(context, dict):
        context = {}
    if not isinstance(samples, list):
        samples = []
    last_sample = samples[-1] if samples and isinstance(samples[-1], dict) else None
    env = context.get("env") if isinstance(context.get("env"), dict) else {}
    cpu = context.get("cpu") if isinstance(context.get("cpu"), dict) else {}
    return {
        "commit": env.get("APP_GIT_SHA"),
        "branch": env.get("APP_GIT_BRANCH"),
        "deploy_env": env.get("APP_DEPLOY_ENV"),
        "cpu_visible": cpu.get("affinity_count") or cpu.get("os_cpu_count"),
        "last_resource_sample": last_sample,
    }


def _job_summary(job: SimulationJob) -> dict[str, Any]:
    timings = job.model_timings_json if isinstance(job.model_timings_json, dict) else {}
    stage_times = job.stage_times_json if isinstance(job.stage_times_json, dict) else {}
    return {
        "id": job.id,
        "status": job.status,
        "simulation_type": job.simulation_type,
        "scenario_id": job.scenario_id,
        "solver_name": job.solver_name,
        "solver_threads_configured": job.solver_threads_configured,
        "solver_threads_used": job.solver_threads_used,
        "queued_at": _dt(job.queued_at),
        "started_at": _dt(job.started_at),
        "finished_at": _dt(job.finished_at),
        "progress": _safe_float(job.progress),
        "objective_value": _safe_float(job.objective_value),
        "total_dispatch": _safe_float(job.total_dispatch),
        "stage_times": stage_times,
        "model_timing_keys": sorted(timings.keys()),
        "solver_status": timings.get("solver_status"),
        "runtime": _runtime_summary(job),
    }


def _remote_configs() -> list[dict[str, str]]:
    settings = get_settings()
    configs: list[dict[str, str]] = []
    for item in settings.simulation_ops_remote_environments_list():
        name = str(item.get("name") or "").strip()
        base_url = str(item.get("base_url") or "").strip().rstrip("/")
        token = str(item.get("token") or "").strip()
        if not name or not base_url:
            continue
        configs.append({"name": name, "base_url": base_url, "token": token})
    return configs


class SimulationOpsService:
    """Aggregates local and configured remote simulation queue state."""

    @staticmethod
    def environment_name() -> str:
        settings = get_settings()
        return (
            settings.simulation_ops_environment_name
            or os.environ.get("APP_DEPLOY_ENV")
            or settings.environment
            or "local"
        )

    @staticmethod
    def local_dashboard(db: Session) -> dict[str, Any]:
        settings = get_settings()
        status_rows = db.execute(
            select(
                SimulationJob.status,
                SimulationJob.simulation_type,
                func.count(SimulationJob.id),
            ).group_by(SimulationJob.status, SimulationJob.simulation_type)
        ).all()
        counts_by_status_type: dict[str, dict[str, int]] = {}
        for status, simulation_type, count in status_rows:
            counts_by_status_type.setdefault(str(status), {})[str(simulation_type)] = int(count)

        active_jobs = db.execute(
            select(SimulationJob)
            .where(SimulationJob.status.in_(ACTIVE_STATUSES))
            .order_by(SimulationJob.queued_at.asc())
            .limit(30)
        ).scalars().all()
        recent_jobs = db.execute(
            select(SimulationJob).order_by(SimulationJob.id.desc()).limit(12)
        ).scalars().all()

        services = DockerMetricsService.list_service_memory()
        runtime_env = {
            key: os.environ.get(key)
            for key in (
                "APP_DEPLOY_ENV",
                "APP_GIT_BRANCH",
                "APP_GIT_SHA",
                "COMPOSE_PROJECT_NAME",
                "SIM_SOLVER_THREADS",
                "SIM_MAX_CONCURRENCY",
                "SIM_TOTAL_WEIGHT_LIMIT",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
            )
            if os.environ.get(key) is not None
        }
        return {
            "name": SimulationOpsService.environment_name(),
            "generated_at": _utc_now(),
            "reachable": True,
            "error": None,
            "queue": {
                **SimulationRepository.count_overview(db),
                "counts_by_status_type": counts_by_status_type,
                "limits": {
                    "sim_max_concurrency": settings.sim_max_concurrency,
                    "sim_user_active_limit": settings.sim_user_active_limit,
                    "sim_total_weight_limit": settings.sim_total_weight_limit,
                    "sim_weight_national": settings.sim_weight_national,
                    "sim_weight_regional": settings.sim_weight_regional,
                },
            },
            "runtime_env": runtime_env,
            "services_memory": services,
            "services_memory_total_bytes": sum(
                int(item.get("memory_usage_bytes") or 0) for item in services
            ),
            "active_jobs": [_job_summary(job) for job in active_jobs],
            "recent_jobs": [_job_summary(job) for job in recent_jobs],
        }

    @staticmethod
    def _request_remote(config: dict[str, str], *, method: str, path: str) -> dict[str, Any]:
        url = f"{config['base_url']}{path}"
        headers = {"Accept": "application/json"}
        if config.get("token"):
            headers["Authorization"] = f"Bearer {config['token']}"
        request = Request(url, headers=headers, method=method)
        try:
            with urlopen(request, timeout=8) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code}: {body[:300]}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(str(exc)) from exc

    @staticmethod
    def remote_dashboards() -> list[dict[str, Any]]:
        dashboards: list[dict[str, Any]] = []
        qs = urlencode({"include_remotes": "false"})
        for config in _remote_configs():
            try:
                payload = SimulationOpsService._request_remote(
                    config,
                    method="GET",
                    path=f"/simulation-ops/dashboard?{qs}",
                )
                envs = payload.get("environments") if isinstance(payload, dict) else None
                if isinstance(envs, list) and envs:
                    dashboards.append(envs[0])
                elif isinstance(payload, dict):
                    dashboards.append(payload)
            except RuntimeError as exc:
                logger.warning("No fue posible consultar ambiente remoto %s", config["name"])
                dashboards.append(
                    {
                        "name": config["name"],
                        "generated_at": _utc_now(),
                        "reachable": False,
                        "error": str(exc),
                        "queue": {},
                        "runtime_env": {},
                        "services_memory": [],
                        "services_memory_total_bytes": 0,
                        "active_jobs": [],
                        "recent_jobs": [],
                    }
                )
        return dashboards

    @staticmethod
    def dashboard(db: Session, *, include_remotes: bool) -> dict[str, Any]:
        environments = [SimulationOpsService.local_dashboard(db)]
        if include_remotes:
            environments.extend(SimulationOpsService.remote_dashboards())
        return {"generated_at": _utc_now(), "environments": environments}

    @staticmethod
    def cancel_local_job(db: Session, *, job_id: int) -> dict[str, Any]:
        job = db.get(SimulationJob, job_id)
        if not job:
            raise NotFoundError("Simulación no encontrada.")
        if job.status not in ACTIVE_STATUSES:
            raise ConflictError("Solo se pueden cancelar simulaciones en cola o ejecución.")

        previous_status = str(job.status)
        task_id = str(job.celery_task_id) if job.celery_task_id else None
        job.cancel_requested = True
        job.status = "CANCELLED"
        job.finished_at = func.now()
        SimulationRepository.add_event(
            db,
            job_id=job.id,
            event_type="INFO",
            stage="cancel",
            message="Simulación cancelada desde el tablero operacional.",
            progress=job.progress,
        )
        db.commit()
        if task_id:
            try:
                celery_app.control.revoke(
                    task_id,
                    terminate=(previous_status == "RUNNING"),
                    signal="SIGTERM",
                )
            except Exception:  # pragma: no cover
                logger.warning("No se pudo revocar task Celery %s", task_id, exc_info=True)
        from app.services.simulation_service import SimulationService

        SimulationService._dispatch_queued_jobs(db)
        db.refresh(job)
        return _job_summary(job)

    @staticmethod
    def cancel_job(db: Session, *, environment: str, job_id: int) -> dict[str, Any]:
        local_name = SimulationOpsService.environment_name()
        if environment == local_name or environment in ("local", "current"):
            return SimulationOpsService.cancel_local_job(db, job_id=job_id)
        for config in _remote_configs():
            if config["name"] == environment:
                return SimulationOpsService._request_remote(
                    config,
                    method="POST",
                    path=f"/simulation-ops/jobs/{job_id}/cancel",
                )
        raise NotFoundError("Ambiente operacional no configurado.")
