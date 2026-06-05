from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest

import app.services.simulation_service as simulation_service_module
from app.services.simulation_service import SimulationService


class DummyDbSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.refresh_calls = 0
        self.flush_calls = 0

    def execute(self, _stmt):
        class _Result:
            def all(self):
                return []

            def scalars(self):
                class _Scalars:
                    def all(self_inner):
                        return []

                    def __iter__(self_inner):
                        return iter([])

                return _Scalars()

        return _Result()

    def commit(self) -> None:
        self.commit_calls += 1

    def flush(self) -> None:
        self.flush_calls += 1

    def refresh(self, _obj: object) -> None:
        self.refresh_calls += 1


def _build_job(user_id: uuid.UUID, *, scenario_id: int | None = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=123,
        scenario_id=scenario_id,
        user_id=user_id,
        solver_name="highs",
        input_mode="SCENARIO" if scenario_id is not None else "CSV_UPLOAD",
        input_name=None,
        simulation_type="NATIONAL",
        parallel_weight=1,
        status="QUEUED",
        progress=0.0,
        cancel_requested=False,
        result_ref=None,
        error_message=None,
        queued_at=datetime.now(timezone.utc),
        started_at=None,
        finished_at=None,
        celery_task_id=None,
        celery_dispatched_at=None,
        stage_times_json={},
        model_timings_json={},
    )


def test_submit_derives_simulation_type_and_weight_from_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    current_user = SimpleNamespace(id=uuid.uuid4(), username="seed")
    scenario = SimpleNamespace(id=1, owner="seed", name="Escenario nacional", simulation_type="REGIONAL")
    job = _build_job(current_user.id)
    db = DummyDbSession()
    events: list[dict] = []
    create_kwargs: dict[str, object] = {}
    dispatch_calls: list[int | None] = []

    monkeypatch.setattr(
        simulation_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            sim_user_active_limit=3,
            sim_total_weight_limit=8,
            sim_weight_national=1,
            sim_weight_regional=3,
            simulation_mode="async",
        ),
    )
    from app.services.scenario_service import ScenarioService

    def _create_job(_db, **kwargs):
        create_kwargs.update(kwargs)
        for key, value in kwargs.items():
            setattr(job, key, value)
        return job

    monkeypatch.setattr(
        ScenarioService,
        "_require_access",
        staticmethod(lambda _db, *, scenario_id, current_user: scenario),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "count_user_active_jobs",
        lambda _db, *, user_id: 0,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "create_job",
        _create_job,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "add_event",
        lambda _db, *, job_id, event_type, stage, message, progress: events.append(
            {
                "job_id": job_id,
                "event_type": event_type,
                "stage": stage,
                "message": message,
                "progress": progress,
            }
        ),
    )
    monkeypatch.setattr(
        simulation_service_module,
        "_MAIN_VARIABLES",
        simulation_service_module._MAIN_VARIABLES,
    )
    monkeypatch.setattr(
        SimulationService,
        "_dispatch_queued_jobs",
        staticmethod(lambda _db, *, fail_fast_job_id=None: dispatch_calls.append(fail_fast_job_id)),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "queue_position",
        lambda _db, *, job_id: 1,
    )

    payload = SimulationService.submit(
        db,
        current_user=current_user,
        scenario_id=1,
        solver_name="highs",
    )

    assert create_kwargs["simulation_type"] == "REGIONAL"
    assert create_kwargs["parallel_weight"] == 3
    assert dispatch_calls == [job.id]
    assert payload["simulation_type"] == "REGIONAL"
    assert events[0]["message"] == "Job creado y listo para encolar."


def test_submit_from_csv_uses_visible_name_type_and_weight(monkeypatch: pytest.MonkeyPatch) -> None:
    current_user = SimpleNamespace(id=uuid.uuid4(), username="seed")
    job = _build_job(current_user.id, scenario_id=None)
    job.input_mode = "CSV_UPLOAD"
    job.input_name = "Modelo regional abril"
    job.simulation_type = "REGIONAL"
    job.parallel_weight = 3
    db = DummyDbSession()
    create_kwargs: dict[str, object] = {}

    def _create_job(_db, **kwargs):
        create_kwargs.update(kwargs)
        for key, value in kwargs.items():
            setattr(job, key, value)
        return job

    monkeypatch.setattr(
        simulation_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            sim_user_active_limit=3,
            sim_total_weight_limit=8,
            sim_weight_national=1,
            sim_weight_regional=3,
            simulation_mode="async",
        ),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "count_user_active_jobs",
        lambda _db, *, user_id: 0,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "create_job",
        _create_job,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "add_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        SimulationService,
        "_dispatch_queued_jobs",
        staticmethod(lambda _db, *, fail_fast_job_id=None: None),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "queue_position",
        lambda _db, *, job_id: 2,
    )

    payload = SimulationService.submit_from_csv(
        db,
        current_user=current_user,
        solver_name="highs",
        input_name="Modelo regional abril",
        input_ref="/tmp/job/input",
        simulation_type="REGIONAL",
    )

    assert create_kwargs["input_name"] == "Modelo regional abril"
    assert create_kwargs["simulation_type"] == "REGIONAL"
    assert create_kwargs["parallel_weight"] == 3
    assert payload["scenario_name"] == "Modelo regional abril"
    assert payload["simulation_type"] == "REGIONAL"


def test_dispatch_queued_jobs_respects_reserved_weight(monkeypatch: pytest.MonkeyPatch) -> None:
    db = DummyDbSession()
    first = _build_job(uuid.uuid4())
    first.id = 1
    first.parallel_weight = 4
    second = _build_job(uuid.uuid4())
    second.id = 2
    second.parallel_weight = 2
    third = _build_job(uuid.uuid4())
    third.id = 3
    third.parallel_weight = 1
    pending = [first, second, third]
    dispatched: list[int] = []

    monkeypatch.setattr(
        simulation_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            sim_user_active_limit=3,
            sim_total_weight_limit=5,
            sim_weight_national=1,
            sim_weight_regional=3,
            simulation_mode="async",
        ),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "get_reserved_parallel_weight",
        lambda _db: 2,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "get_reserved_user_job_counts",
        lambda _db: {},
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "list_queued_undispatched_jobs",
        lambda _db, *, limit=500: pending,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "get_job_by_id",
        lambda _db, *, job_id: next((job for job in pending if job.id == job_id), None),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "add_event",
        lambda *args, **kwargs: None,
    )
    task_ids = iter(["task-2", "task-3"])
    monkeypatch.setattr(
        simulation_service_module.uuid,
        "uuid4",
        lambda: next(task_ids),
    )

    class _TaskStub:
        @staticmethod
        def apply_async(*, args, task_id: str):
            job_id = args[0]
            dispatched.append(job_id)
            return SimpleNamespace(id=task_id)

    monkeypatch.setattr(simulation_service_module, "run_simulation_job", _TaskStub())

    SimulationService.dispatch_pending_jobs(db)

    assert dispatched == [2, 3]
    assert second.celery_task_id == "task-2"
    assert third.celery_task_id == "task-3"
    assert first.celery_task_id is None

def test_submit_creates_queued_job_even_when_user_has_many_active(monkeypatch: pytest.MonkeyPatch) -> None:
    current_user = SimpleNamespace(id=uuid.uuid4(), username="seed")
    scenario = SimpleNamespace(id=1, owner="seed", name="Escenario seed", simulation_type="NATIONAL")
    job = _build_job(current_user.id)
    db = DummyDbSession()
    create_kwargs: dict[str, object] = {}

    monkeypatch.setattr(
        simulation_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            sim_user_active_limit=3,
            sim_total_weight_limit=8,
            sim_weight_national=1,
            sim_weight_regional=3,
            simulation_mode="async",
        ),
    )
    from app.services.scenario_service import ScenarioService

    monkeypatch.setattr(
        ScenarioService,
        "_require_access",
        staticmethod(lambda _db, *, scenario_id, current_user: scenario),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "create_job",
        lambda _db, **kwargs: create_kwargs.update(kwargs) or job,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "add_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "queue_position",
        lambda _db, *, job_id: 4,
    )
    monkeypatch.setattr(
        SimulationService,
        "_dispatch_queued_jobs",
        staticmethod(lambda _db, *, fail_fast_job_id=None: None),
    )

    payload = SimulationService.submit(
        db,
        current_user=current_user,
        scenario_id=1,
        solver_name="highs",
    )

    assert create_kwargs["scenario_id"] == 1
    assert payload["status"] == "QUEUED"


def test_cancel_running_job_revokes_and_terminates_celery_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = SimpleNamespace(id=uuid.uuid4(), username="seed")
    job = _build_job(current_user.id)
    job.status = "RUNNING"
    job.progress = 45.0
    job.celery_task_id = "running-task"
    db = DummyDbSession()
    events: list[dict[str, object]] = []
    revoke_calls: list[dict[str, object]] = []
    dispatch_calls = 0

    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "get_job_for_user",
        lambda _db, *, job_id, user_id: job,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "add_event",
        lambda _db, **kwargs: events.append(kwargs),
    )

    class _Control:
        @staticmethod
        def revoke(task_id: str, *, terminate: bool, signal: str) -> None:
            revoke_calls.append(
                {"task_id": task_id, "terminate": terminate, "signal": signal}
            )

    monkeypatch.setattr(
        simulation_service_module.celery_app,
        "control",
        _Control(),
    )

    def _dispatch(_db):
        nonlocal dispatch_calls
        dispatch_calls += 1

    monkeypatch.setattr(
        SimulationService,
        "_dispatch_queued_jobs",
        staticmethod(_dispatch),
    )
    monkeypatch.setattr(
        SimulationService,
        "_batch_scenario_tags_by_scenario_ids",
        staticmethod(lambda _db, _ids: {}),
    )
    monkeypatch.setattr(
        SimulationService,
        "_to_public",
        staticmethod(lambda job_, *, scenario_tag=None: {"id": job_.id, "status": job_.status}),
    )

    payload = SimulationService.cancel(db, current_user=current_user, job_id=job.id)

    assert payload["status"] == "CANCELLED"
    assert job.status == "CANCELLED"
    assert job.cancel_requested is True
    assert job.finished_at is not None
    assert revoke_calls == [
        {"task_id": "running-task", "terminate": True, "signal": "SIGTERM"}
    ]
    assert dispatch_calls == 1
    assert events[0]["stage"] == "cancel"


def test_dispatch_queued_jobs_respects_user_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    db = DummyDbSession()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    first = _build_job(user_a)
    first.id = 11
    second = _build_job(user_a)
    second.id = 12
    third = _build_job(user_b)
    third.id = 13
    pending = [first, second, third]
    dispatched: list[int] = []

    monkeypatch.setattr(
        simulation_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            sim_user_active_limit=3,
            sim_total_weight_limit=8,
            sim_weight_national=1,
            sim_weight_regional=3,
            simulation_mode="async",
        ),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "get_reserved_parallel_weight",
        lambda _db: 2,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "get_reserved_user_job_counts",
        lambda _db: {user_a: 3, user_b: 1},
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "list_queued_undispatched_jobs",
        lambda _db, *, limit=500: pending,
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "get_job_by_id",
        lambda _db, *, job_id: next((job for job in pending if job.id == job_id), None),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "add_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        simulation_service_module.uuid,
        "uuid4",
        lambda: "task-13",
    )

    class _TaskStub:
        @staticmethod
        def apply_async(*, args, task_id: str):
            job_id = args[0]
            dispatched.append(job_id)
            return SimpleNamespace(id=task_id)

    monkeypatch.setattr(simulation_service_module, "run_simulation_job", _TaskStub())

    SimulationService.dispatch_pending_jobs(db)

    assert dispatched == [13]
    assert first.celery_task_id is None
    assert second.celery_task_id is None
    assert third.celery_task_id == "task-13"


def test_reconcile_releases_stale_queued_task(monkeypatch: pytest.MonkeyPatch) -> None:
    db = DummyDbSession()
    job = _build_job(uuid.uuid4())
    job.id = 21
    job.celery_task_id = "dead-task"
    job.celery_dispatched_at = datetime.now(timezone.utc) - timedelta(minutes=45)
    events: list[dict[str, object]] = []

    monkeypatch.setattr(
        simulation_service_module,
        "get_settings",
        lambda: SimpleNamespace(sim_stale_task_minutes=30),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "list_active_jobs_with_task_id",
        lambda _db, *, limit=500: [job],
    )
    monkeypatch.setattr(
        SimulationService,
        "_collect_live_celery_task_ids",
        staticmethod(lambda: set()),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "add_event",
        lambda _db, **kwargs: events.append(kwargs),
    )

    reconciled = SimulationService.reconcile_stale_dispatched_jobs(db)

    assert reconciled == 1
    assert job.celery_task_id is None
    assert job.celery_dispatched_at is None
    assert events[0]["stage"] == "queue_reconcile"


def test_reconcile_fails_stale_running_task(monkeypatch: pytest.MonkeyPatch) -> None:
    db = DummyDbSession()
    job = _build_job(uuid.uuid4())
    job.id = 22
    job.status = "RUNNING"
    job.progress = 35.0
    job.celery_task_id = "dead-running-task"
    job.celery_dispatched_at = datetime.now(timezone.utc) - timedelta(minutes=45)
    events: list[dict[str, object]] = []

    monkeypatch.setattr(
        simulation_service_module,
        "get_settings",
        lambda: SimpleNamespace(sim_stale_task_minutes=30),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "list_active_jobs_with_task_id",
        lambda _db, *, limit=500: [job],
    )
    monkeypatch.setattr(
        SimulationService,
        "_collect_live_celery_task_ids",
        staticmethod(lambda: set()),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "add_event",
        lambda _db, **kwargs: events.append(kwargs),
    )

    reconciled = SimulationService.reconcile_stale_dispatched_jobs(db)

    assert reconciled == 1
    assert job.status == "FAILED"
    assert "worker fue terminado" in job.error_message
    assert events[0]["stage"] == "run_reconcile"


def test_reconcile_keeps_fresh_queued_task(monkeypatch: pytest.MonkeyPatch) -> None:
    db = DummyDbSession()
    job = _build_job(uuid.uuid4())
    job.id = 23
    job.celery_task_id = "fresh-task"
    job.celery_dispatched_at = datetime.now(timezone.utc)

    monkeypatch.setattr(
        simulation_service_module,
        "get_settings",
        lambda: SimpleNamespace(sim_stale_task_minutes=30),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "list_active_jobs_with_task_id",
        lambda _db, *, limit=500: [job],
    )
    monkeypatch.setattr(
        SimulationService,
        "_collect_live_celery_task_ids",
        staticmethod(lambda: set()),
    )
    monkeypatch.setattr(
        simulation_service_module.SimulationRepository,
        "add_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("No event expected")),
    )

    reconciled = SimulationService.reconcile_stale_dispatched_jobs(db)

    assert reconciled == 0
    assert job.celery_task_id == "fresh-task"
