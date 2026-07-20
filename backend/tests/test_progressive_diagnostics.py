from __future__ import annotations

from pathlib import Path

from app.simulation.core.progressive_diagnostics import (
    run_family_diagnosis,
    run_highs_presolve_diagnostic,
)


def _lp(tmp_path: Path) -> Path:
    path = tmp_path / "conflict.lp"
    path.write_text(
        """Minimize
 obj: x
Subject To
 c_l_DemandFloor(R1_ELC_2030)_: x >= 2
 c_u_CapacityCeiling(R1_PWR_2030)_: x <= 1
Bounds
 x free
End
""",
        encoding="utf-8",
    )
    return path


def test_presolve_reports_certified_infeasibility(tmp_path: Path) -> None:
    report = run_highs_presolve_diagnostic(_lp(tmp_path))

    assert report["available"] is True
    assert report["infeasible_in_presolve"] is True
    assert report["evidence_level"] == "CERTIFIED"


def test_family_diagnosis_is_incremental_and_not_claimed_as_iis(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("OSEMOSYS_FAMILY_DIAG_MAX_PROBES", "10")
    report = run_family_diagnosis(_lp(tmp_path))

    assert report["available"] is True
    assert report["global_certificate"] is False
    assert report["probe_count"] >= 2
    assert {row["family"] for row in report["ablation"]} == {
        "DemandFloor", "CapacityCeiling"
    }
    assert all(row["necessary_for_current_conflict"] for row in report["ablation"])
