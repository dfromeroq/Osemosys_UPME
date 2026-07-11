"""Operational dashboard and controls for simulation queues."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models import SimulationJob, SimulationJobEvent
from app.repositories.simulation_repository import SimulationRepository
from app.services.docker_metrics_service import DockerMetricsService
from app.simulation.celery_app import celery_app

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("QUEUED", "RUNNING")
_LAST_CPU_SAMPLE: tuple[float, int, int] | None = None


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


def _read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _read_meminfo() -> dict[str, int]:
    raw = _read_text("/proc/meminfo")
    if not raw:
        return {}
    values: dict[str, int] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parts = value.strip().split()
        if not parts:
            continue
        try:
            values[key] = int(parts[0]) * 1024
        except ValueError:
            continue
    return values


def _read_cpu_totals() -> tuple[int, int] | None:
    raw = _read_text("/proc/stat")
    if not raw:
        return None
    first = raw.splitlines()[0].split()
    if not first or first[0] != "cpu":
        return None
    try:
        values = [int(part) for part in first[1:]]
    except ValueError:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return total, idle


def _system_resources() -> dict[str, Any]:
    """Current host/container-visible CPU and memory snapshot for ops UI."""
    global _LAST_CPU_SAMPLE

    meminfo = _read_meminfo()
    total_bytes = meminfo.get("MemTotal")
    available_bytes = meminfo.get("MemAvailable")
    used_bytes = (
        total_bytes - available_bytes
        if total_bytes is not None and available_bytes is not None
        else None
    )

    cpu_percent: float | None = None
    now = time.monotonic()
    totals = _read_cpu_totals()
    if totals is not None:
        total, idle = totals
        if _LAST_CPU_SAMPLE is not None:
            _last_wall, last_total, last_idle = _LAST_CPU_SAMPLE
            total_delta = max(0, total - last_total)
            idle_delta = max(0, idle - last_idle)
            wall_delta = max(0.0, now - _last_wall)
            if total_delta > 0 and wall_delta > 0:
                cpu_percent = round((1 - idle_delta / total_delta) * 100, 2)
        _LAST_CPU_SAMPLE = (now, total, idle)

    cpu_count = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    if cpu_percent is None and cpu_count:
        try:
            cpu_percent = round(min(100.0, (os.getloadavg()[0] / cpu_count) * 100), 2)
        except (AttributeError, OSError):
            pass
    return {
        "cpu_logical_count": cpu_count,
        "cpu_percent": cpu_percent,
        "cpu_used_cores": round((cpu_percent or 0) * (cpu_count or 0) / 100, 3)
        if cpu_percent is not None and cpu_count
        else None,
        "memory_total_bytes": total_bytes,
        "memory_available_bytes": available_bytes,
        "memory_used_bytes": used_bytes,
        "memory_used_percent": round((used_bytes / total_bytes) * 100, 2)
        if used_bytes is not None and total_bytes
        else None,
    }


def _event_summary(event: SimulationJobEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "stage": event.stage,
        "message": event.message,
        "progress": _safe_float(event.progress),
        "created_at": _dt(event.created_at),
    }


def _runtime_summary(job: SimulationJob) -> dict[str, Any]:
    timings = job.model_timings_json if isinstance(job.model_timings_json, dict) else {}
    context = timings.get("runtime_context")
    samples = timings.get("runtime_resource_samples")
    if not isinstance(context, dict):
        context = {}
    if not isinstance(samples, list):
        samples = []
    last_sample = samples[-1] if samples and isinstance(samples[-1], dict) else None
    clean_samples = [sample for sample in samples if isinstance(sample, dict)]
    env = context.get("env") if isinstance(context.get("env"), dict) else {}
    cpu = context.get("cpu") if isinstance(context.get("cpu"), dict) else {}
    memory = context.get("memory") if isinstance(context.get("memory"), dict) else {}
    return {
        "commit": env.get("APP_GIT_SHA"),
        "branch": env.get("APP_GIT_BRANCH"),
        "deploy_env": env.get("APP_DEPLOY_ENV"),
        "hostname": context.get("hostname"),
        "pid": context.get("pid"),
        "cpu_visible": cpu.get("affinity_count") or cpu.get("os_cpu_count"),
        "cpu_context": cpu,
        "memory_context": memory,
        "last_resource_sample": last_sample,
        "resource_samples": clean_samples[-60:],
    }


def _job_summary(
    job: SimulationJob,
    *,
    events: list[SimulationJobEvent] | None = None,
) -> dict[str, Any]:
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
        "events": [_event_summary(event) for event in (events or [])],
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
            select(SimulationJob).order_by(SimulationJob.id.desc()).limit(30)
        ).scalars().all()

        job_ids = list(dict.fromkeys(int(job.id) for job in [*active_jobs, *recent_jobs]))
        events_by_job: dict[int, list[SimulationJobEvent]] = {job_id: [] for job_id in job_ids}
        if job_ids:
            event_rows = db.execute(
                select(SimulationJobEvent)
                .where(SimulationJobEvent.job_id.in_(job_ids))
                .order_by(SimulationJobEvent.id.desc())
                .limit(max(20, len(job_ids) * 20))
            ).scalars().all()
            for event in event_rows:
                bucket = events_by_job.setdefault(int(event.job_id), [])
                if len(bucket) < 20:
                    bucket.append(event)
            for bucket in events_by_job.values():
                bucket.reverse()

        service_memory = DockerMetricsService.list_service_memory()
        service_metrics = DockerMetricsService.list_service_metrics()
        detailed_by_name = {
            str(item.get("service_name")): item for item in service_metrics
        }
        services = [
            {**detailed_by_name.get(str(item.get("service_name")), {}), **item}
            for item in service_memory
        ]
        known = {str(item.get("service_name")) for item in services}
        services.extend(
            item for item in service_metrics if str(item.get("service_name")) not in known
        )
        runtime_env = {
            key: os.environ.get(key)
            for key in (
                "APP_DEPLOY_ENV",
                "APP_GIT_BRANCH",
                "APP_GIT_SHA",
                "COMPOSE_PROJECT_NAME",
                "SIM_SOLVER_THREADS",
                "SIM_SOLVER_PROFILE",
                "SIM_SOLVER_GLPK_PROFILE",
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
            "system_resources": _system_resources(),
            "services_memory": services,
            "services_memory_total_bytes": sum(
                int(item.get("memory_usage_bytes") or 0) for item in services
            ),
            "active_jobs": [
                _job_summary(job, events=events_by_job.get(int(job.id))) for job in active_jobs
            ],
            "recent_jobs": [
                _job_summary(job, events=events_by_job.get(int(job.id))) for job in recent_jobs
            ],
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
