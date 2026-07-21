from __future__ import annotations

from app.models import SimulationJob
from app.simulation.tasks import _persist_solver_failure_metadata


def test_persist_solver_failure_metadata_merges_existing_timings() -> None:
    job = SimulationJob(model_timings_json={"create_instance_seconds": 12.5})
    exc = RuntimeError("time limit")
    exc.solver_failure_metadata = {  # type: ignore[attr-defined]
        "solver_status_raw": "maxTimeLimit",
        "solver_run_seconds": 600.0,
        "solver_highs_method": "ipm",
    }

    _persist_solver_failure_metadata(job, exc)

    assert job.model_timings_json == {
        "create_instance_seconds": 12.5,
        "solver_status_raw": "maxTimeLimit",
        "solver_run_seconds": 600.0,
        "solver_highs_method": "ipm",
    }
