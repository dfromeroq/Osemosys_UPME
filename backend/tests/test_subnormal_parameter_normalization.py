from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.simulation.core.data_processing import (
    normalize_subnormal_parameter_values,
)


def _write_values(path: Path, values: list[float]) -> None:
    pd.DataFrame(
        {
            "REGION": ["COL"] * len(values),
            "TECHNOLOGY": [f"T{i}" for i in range(len(values))],
            "YEAR": [2030] * len(values),
            "VALUE": values,
        }
    ).to_csv(path, index=False)


def test_normalize_subnormal_parameter_values_only_replaces_sentinels(
    tmp_path: Path,
) -> None:
    residual = tmp_path / "ResidualCapacity.csv"
    lower = tmp_path / "TotalTechnologyAnnualActivityLowerLimit.csv"
    values = [0.0, 2.561736903927082e-308, -2.561736903927082e-308, 1e-299, 1e-12]
    _write_values(residual, values)
    _write_values(lower, values)

    changed = normalize_subnormal_parameter_values(str(tmp_path))

    assert changed == {
        "ResidualCapacity.csv": 2,
        "TotalTechnologyAnnualActivityLowerLimit.csv": 2,
    }
    for path in (residual, lower):
        result = pd.read_csv(path)["VALUE"].tolist()
        assert result == [0.0, 0.0, 0.0, 1e-299, 1e-12]


def test_normalize_subnormal_parameter_values_ignores_other_parameters(
    tmp_path: Path,
) -> None:
    other = tmp_path / "SpecifiedAnnualDemand.csv"
    _write_values(other, [2.561736903927082e-308])

    changed = normalize_subnormal_parameter_values(str(tmp_path))

    assert changed == {}
    assert pd.read_csv(other).loc[0, "VALUE"] == 2.561736903927082e-308
