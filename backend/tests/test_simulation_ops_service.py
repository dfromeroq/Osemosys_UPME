from __future__ import annotations

from datetime import datetime, timezone

import app.services.simulation_ops_service as ops_module
from app.models import SimulationJob
from app.services.simulation_service import SimulationService
from app.services.simulation_ops_service import SimulationOpsService

from factories import create_scenario, create_user


def test_simulation_ops_dashboard_counts_and_resources(db_session, monkeypatch) -> None:
    user = create_user(db_session, username="ops-user")
    scenario = create_scenario(db_session, name="Ops Scenario", owner=user.username)
    job = SimulationJob(
        user_id=user.id,
        scenario_id=scenario.id,
        solver_name="highs",
        status="RUNNING",
        progress=55.0,
        queued_at=datetime.now(timezone.utc),
        simulation_type="REGIONAL",
        model_timings_json={
            "runtime_context": {
                "env": {"APP_GIT_SHA": "abcdef123456"},
                "cpu": {"affinity_count": 4},
            },
            "runtime_resource_samples": [
                {"stage": "solver_run", "rss_mb": 1024.0, "threads": 9}
            ],
        },
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(
        ops_module.DockerMetricsService,
        "list_service_memory",
        staticmethod(
            lambda: [
                {"service_name": "api", "memory_usage_bytes": 100},
                {"service_name": "simulation-worker", "memory_usage_bytes": 200},
            ]
        ),
    )

    payload = SimulationOpsService.dashboard(db_session, include_remotes=False)

    env = payload["environments"][0]
    assert env["queue"]["running_count"] == 1
    assert env["queue"]["counts_by_status_type"]["RUNNING"]["REGIONAL"] == 1
    assert env["services_memory_total_bytes"] == 300
    assert env["active_jobs"][0]["runtime"]["commit"] == "abcdef123456"
    assert env["active_jobs"][0]["runtime"]["last_resource_sample"]["stage"] == "solver_run"


def test_simulation_ops_cancel_local_running_job(db_session, monkeypatch) -> None:
    user = create_user(db_session, username="ops-cancel")
    scenario = create_scenario(db_session, name="Ops Cancel", owner=user.username)
    job = SimulationJob(
        user_id=user.id,
        scenario_id=scenario.id,
        solver_name="highs",
        status="RUNNING",
        progress=45.0,
        queued_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        simulation_type="REGIONAL",
        celery_task_id="task-123",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    revoked: list[tuple[str, bool, str]] = []

    def fake_revoke(task_id: str, *, terminate: bool, signal: str) -> None:
        revoked.append((task_id, terminate, signal))

    monkeypatch.setattr(ops_module.celery_app.control, "revoke", fake_revoke)
    monkeypatch.setattr(SimulationService, "_dispatch_queued_jobs", staticmethod(lambda _db: None))

    payload = SimulationOpsService.cancel_local_job(db_session, job_id=job.id)

    db_session.refresh(job)
    assert payload["status"] == "CANCELLED"
    assert job.status == "CANCELLED"
    assert job.cancel_requested is True
    assert revoked == [("task-123", True, "SIGTERM")]
