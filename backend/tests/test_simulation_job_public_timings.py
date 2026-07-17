from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.simulation_service import SimulationService


def test_to_public_includes_stage_and_model_timings() -> None:
    now = datetime.now(timezone.utc)
    job = SimpleNamespace(
        id=42,
        scenario_id=1,
        user_id="user-1",
        solver_name="highs",
        input_mode="SCENARIO",
        input_name=None,
        simulation_type="REGIONAL",
        status="SUCCEEDED",
        progress=100.0,
        cancel_requested=False,
        result_ref="ref",
        error_message=None,
        queued_at=now,
        started_at=now,
        finished_at=now,
        run_iis_analysis=False,
        generate_lp=False,
        lp_path=None,
        is_public=True,
        display_name=None,
        description=None,
        infeasibility_diagnostics_json=None,
        stage_times_json={"extract_data_seconds": 1.2, "persist_results_seconds": 8.5},
        model_timings_json={
            "solver_run_seconds": 200.0,
            "solver_write_lp_seconds": 80.0,
            "solver_map_solution_seconds": 29.0,
            "solver_status": "optimal",
        },
    )

    public = SimulationService._to_public(job)

    assert public["stage_times"]["extract_data_seconds"] == 1.2
    assert public["stage_times"]["persist_results_seconds"] == 8.5
    assert public["model_timings"]["solver_run_seconds"] == 200.0
    assert public["model_timings"]["solver_write_lp_seconds"] == 80.0
    assert public["model_timings"]["solver_status"] == "optimal"
