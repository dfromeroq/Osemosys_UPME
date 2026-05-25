from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.simulation.tasks as tasks_module
from app.services.simulation_service import SimulationService


@dataclass
class DummyResult:
    rowcount: int


class DummyDbSession:
    def __init__(self, rowcount: int) -> None:
        self._rowcount = rowcount
        self.commit_calls = 0

    def execute(self, _stmt: object) -> DummyResult:
        return DummyResult(rowcount=self._rowcount)

    def commit(self) -> None:
        self.commit_calls += 1


class DummySessionFactory:
    def __init__(self, db: DummyDbSession) -> None:
        self._db = db

    def __call__(self):
        db = self._db

        class _Ctx:
            def __enter__(self_inner) -> DummyDbSession:
                return db

            def __exit__(self_inner, exc_type, exc, tb) -> bool:
                return False

        return _Ctx()


@pytest.mark.parametrize("status", ["RUNNING", "FAILED", "CANCELLED", "SUCCEEDED"])
def test_run_simulation_job_is_noop_for_non_queued_status(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    db = DummyDbSession(rowcount=0)
    job = SimpleNamespace(status=status)

    monkeypatch.setattr(tasks_module, "SessionLocal", DummySessionFactory(db))
    monkeypatch.setattr(
        tasks_module.SimulationRepository,
        "get_job_by_id",
        lambda _db, *, job_id: job,
    )
    monkeypatch.setattr(
        tasks_module.SimulationRepository,
        "add_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("No event expected")),
    )
    monkeypatch.setattr(
        tasks_module,
        "run_pipeline",
        lambda _db, *, job_id: (_ for _ in ()).throw(AssertionError("Pipeline should not run")),
    )

    tasks_module.run_simulation_job.run(123)

    assert db.commit_calls == 1


def test_handle_worker_lost_failure_marks_failed_by_task_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        tasks_module,
        "_mark_failed_by_task_or_job_id",
        lambda *, task_id, job_id, reason: captured.update(
            {"task_id": task_id, "job_id": job_id, "reason": reason}
        )
        or True,
    )
    monkeypatch.setattr(
        tasks_module,
        "_dispatch_pending_jobs_safely",
        lambda: captured.update({"dispatched": True}),
    )

    sender = SimpleNamespace(name=tasks_module.run_simulation_job.name)
    exc = RuntimeError("Worker exited prematurely: signal 9 (SIGKILL)")
    tasks_module.handle_worker_lost_failure(
        sender=sender,
        task_id="abc-task",
        exception=exc,
        args=(777,),
    )

    assert captured["task_id"] == "abc-task"
    assert captured["job_id"] == 777
    assert "WorkerLostError" in str(captured["reason"])
    assert captured["dispatched"] is True


def test_handle_worker_lost_failure_ignores_other_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_module,
        "_mark_failed_by_task_or_job_id",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not update")),
    )
    monkeypatch.setattr(
        tasks_module,
        "_dispatch_pending_jobs_safely",
        lambda: (_ for _ in ()).throw(AssertionError("must not dispatch")),
    )
    sender = SimpleNamespace(name="another.task")
    tasks_module.handle_worker_lost_failure(
        sender=sender,
        task_id="abc-task",
        exception=RuntimeError("Worker exited prematurely: signal 9 (SIGKILL)"),
        args=(777,),
    )


def test_handle_worker_lost_failure_ignores_non_workerlost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_module,
        "_mark_failed_by_task_or_job_id",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not update")),
    )
    monkeypatch.setattr(
        tasks_module,
        "_dispatch_pending_jobs_safely",
        lambda: (_ for _ in ()).throw(AssertionError("must not dispatch")),
    )
    sender = SimpleNamespace(name=tasks_module.run_simulation_job.name)
    tasks_module.handle_worker_lost_failure(
        sender=sender,
        task_id="abc-task",
        exception=RuntimeError("error funcional"),
        args=(777,),
    )


def test_cleanup_csv_upload_artifacts_removes_job_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploads_root = tmp_path / "csv_upload_jobs"
    job_root = uploads_root / "job-123"
    csv_root = job_root / "input" / "model"
    csv_root.mkdir(parents=True)
    (csv_root / "YEAR.csv").write_text("VALUE\n2025\n", encoding="utf-8")
    job = SimpleNamespace(id=123, input_mode="CSV_UPLOAD", input_ref=str(csv_root))

    monkeypatch.setattr(
        tasks_module,
        "get_settings",
        lambda: SimpleNamespace(simulation_artifacts_dir=str(tmp_path)),
    )

    tasks_module._cleanup_csv_upload_artifacts(job)

    assert not job_root.exists()


def test_cleanup_csv_upload_artifacts_ignores_paths_outside_upload_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external_root = tmp_path / "other"
    external_root.mkdir()
    external_csv = external_root / "YEAR.csv"
    external_csv.write_text("VALUE\n2025\n", encoding="utf-8")
    job = SimpleNamespace(id=123, input_mode="CSV_UPLOAD", input_ref=str(external_root))

    monkeypatch.setattr(
        tasks_module,
        "get_settings",
        lambda: SimpleNamespace(simulation_artifacts_dir=str(tmp_path / "artifacts")),
    )

    tasks_module._cleanup_csv_upload_artifacts(job)

    assert external_root.exists()


def test_run_simulation_job_cleans_csv_upload_artifacts_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = DummyDbSession(rowcount=1)
    job = SimpleNamespace(
        id=123,
        status="QUEUED",
        progress=0.0,
        input_mode="CSV_UPLOAD",
        input_ref="/tmp/csv_upload_jobs/job-123/input",
        finished_at=None,
        error_message=None,
    )
    cleaned: list[object] = []

    monkeypatch.setattr(tasks_module, "SessionLocal", DummySessionFactory(db))
    monkeypatch.setattr(
        tasks_module.SimulationRepository,
        "get_job_by_id",
        lambda _db, *, job_id: job,
    )
    monkeypatch.setattr(
        tasks_module.SimulationRepository,
        "add_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(tasks_module, "run_pipeline_from_csv", lambda _db, *, job_id: None)
    monkeypatch.setattr(
        tasks_module,
        "_cleanup_csv_upload_artifacts",
        lambda current_job: cleaned.append(current_job),
    )
    monkeypatch.setattr(
        SimulationService,
        "dispatch_pending_jobs",
        staticmethod(lambda _db: None),
    )

    tasks_module.run_simulation_job.run(123)

    assert cleaned == [job]
    assert job.status == "SUCCEEDED"


def test_run_simulation_job_cleans_csv_upload_artifacts_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = DummyDbSession(rowcount=1)
    job = SimpleNamespace(
        id=123,
        status="QUEUED",
        progress=0.0,
        input_mode="CSV_UPLOAD",
        input_ref="/tmp/csv_upload_jobs/job-123/input",
        finished_at=None,
        error_message=None,
    )
    cleaned: list[object] = []

    monkeypatch.setattr(tasks_module, "SessionLocal", DummySessionFactory(db))
    monkeypatch.setattr(
        tasks_module.SimulationRepository,
        "get_job_by_id",
        lambda _db, *, job_id: job,
    )
    monkeypatch.setattr(
        tasks_module.SimulationRepository,
        "add_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        tasks_module,
        "run_pipeline_from_csv",
        lambda _db, *, job_id: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        tasks_module,
        "_cleanup_csv_upload_artifacts",
        lambda current_job: cleaned.append(current_job),
    )
    monkeypatch.setattr(
        SimulationService,
        "dispatch_pending_jobs",
        staticmethod(lambda _db: None),
    )

    tasks_module.run_simulation_job.run(123)

    assert cleaned == [job]
    assert job.status == "FAILED"
    assert job.error_message == "boom"


def test_run_simulation_job_dispatches_pending_after_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = DummyDbSession(rowcount=1)
    job = SimpleNamespace(
        id=123,
        status="QUEUED",
        progress=0.0,
        input_mode="SCENARIO",
        input_ref=None,
        finished_at=None,
        error_message=None,
    )
    dispatched: list[str] = []

    monkeypatch.setattr(tasks_module, "SessionLocal", DummySessionFactory(db))
    monkeypatch.setattr(
        tasks_module.SimulationRepository,
        "get_job_by_id",
        lambda _db, *, job_id: job,
    )
    monkeypatch.setattr(
        tasks_module.SimulationRepository,
        "add_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(tasks_module, "run_pipeline", lambda _db, *, job_id: None)
    monkeypatch.setattr(
        SimulationService,
        "dispatch_pending_jobs",
        staticmethod(lambda _db: dispatched.append("ok")),
    )

    tasks_module.run_simulation_job.run(123)

    assert job.status == "SUCCEEDED"
    assert dispatched == ["ok"]
