from __future__ import annotations

import pandas as pd

from app.simulation.core.data_processing import (
    UNBOUNDED_EMISSION_LIMIT_SENTINEL,
    normalize_effectively_unbounded_emission_limits,
    prune_small_activity_lower_limits,
)


def test_normalizes_only_effectively_unbounded_emission_limits(tmp_path) -> None:
    annual = tmp_path / "AnnualEmissionLimit.csv"
    model = tmp_path / "ModelPeriodEmissionLimit.csv"
    pd.DataFrame(
        {
            "REGION": ["RE1", "RE1", "RE1"],
            "EMISSION": ["CO2", "CH4", "N2O"],
            "YEAR": [2030, 2030, 2030],
            "VALUE": [1e17, 5_000_000.0, 9_999_999.0],
        }
    ).to_csv(annual, index=False)
    pd.DataFrame(
        {
            "REGION": ["RE1", "RE1"],
            "EMISSION": ["CO2", "CH4"],
            "VALUE": [1e22, 12_000_000.0],
        }
    ).to_csv(model, index=False)

    changed = normalize_effectively_unbounded_emission_limits(str(tmp_path))

    assert changed == {
        "AnnualEmissionLimit.csv": 1,
        "ModelPeriodEmissionLimit.csv": 1,
    }
    annual_values = pd.read_csv(annual)["VALUE"].tolist()
    model_values = pd.read_csv(model)["VALUE"].tolist()
    assert annual_values == [UNBOUNDED_EMISSION_LIMIT_SENTINEL, 5_000_000.0, 9_999_999.0]
    assert model_values == [UNBOUNDED_EMISSION_LIMIT_SENTINEL, 12_000_000.0]


def test_missing_emission_limit_files_are_ignored(tmp_path) -> None:
    assert normalize_effectively_unbounded_emission_limits(str(tmp_path)) == {}


def test_prunes_small_activity_lower_limits_only_when_enabled(tmp_path) -> None:
    path = tmp_path / "TotalTechnologyAnnualActivityLowerLimit.csv"
    pd.DataFrame(
        {
            "REGION": ["RE1"] * 5,
            "TECHNOLOGY": [f"T{i}" for i in range(5)],
            "YEAR": [2030] * 5,
            "VALUE": [0.0, 1e-8, 0.001, 0.0011, 2.0],
        }
    ).to_csv(path, index=False)

    assert prune_small_activity_lower_limits(str(tmp_path), tolerance=0.0) == 0
    assert prune_small_activity_lower_limits(str(tmp_path), tolerance=0.001) == 2
    assert pd.read_csv(path)["VALUE"].tolist() == [0.0, 0.0, 0.0, 0.0011, 2.0]


def test_prune_tolerance_can_come_from_env(tmp_path, monkeypatch) -> None:
    path = tmp_path / "TotalTechnologyAnnualActivityLowerLimit.csv"
    pd.DataFrame({"VALUE": [0.0005, 0.002]}).to_csv(path, index=False)
    monkeypatch.setenv("OSEMOSYS_ACTIVITY_LOWER_PRUNE_TOL", "0.001")
    assert prune_small_activity_lower_limits(str(tmp_path)) == 1
