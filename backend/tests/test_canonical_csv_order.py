from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.simulation.core.canonical_csv_order import (
    canonical_record_key,
    canonicalize_csv_directory,
)
from app.simulation.core.data_processing import PARAM_INDEX


def _write_model(root: Path, *, reverse: bool) -> None:
    root.mkdir()
    sets = {
        "YEAR": [2030, 2025],
        "REGION": ["R10", "R2", "R1"],
        "TECHNOLOGY": ["T10", "T2", "T1"],
        "FUEL": ["F2", "F1"],
        "TIMESLICE": ["S10", "S2", "S1"],
        "MODE_OF_OPERATION": [2, 1],
    }
    for name, values in sets.items():
        rows = list(reversed(values)) if reverse else values
        pd.DataFrame({"VALUE": rows}).to_csv(root / f"{name}.csv", index=False)

    rows = [
        ["R2", "T10", "F1", 2, 2030, 1.5],
        ["R1", "T2", "F2", 1, 2025, 2.5],
        ["R1", "T1", "F1", 1, 2030, 3.5],
    ]
    if reverse:
        rows.reverse()
    pd.DataFrame(
        rows,
        columns=[
            "REGION",
            "TECHNOLOGY",
            "FUEL",
            "MODE_OF_OPERATION",
            "YEAR",
            "VALUE",
        ],
    ).to_csv(root / "OutputActivityRatio.csv", index=False)


def test_canonical_csv_order_is_independent_of_source_row_order(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write_model(left, reverse=False)
    _write_model(right, reverse=True)

    canonicalize_csv_directory(left, PARAM_INDEX)
    canonicalize_csv_directory(right, PARAM_INDEX)

    assert {path.name for path in left.glob("*.csv")} == {
        path.name for path in right.glob("*.csv")
    }
    for left_path in left.glob("*.csv"):
        assert left_path.read_bytes() == (right / left_path.name).read_bytes()

    assert pd.read_csv(left / "TECHNOLOGY.csv")["VALUE"].tolist() == ["T1", "T2", "T10"]
    assert pd.read_csv(left / "TIMESLICE.csv")["VALUE"].tolist() == ["S1", "S2", "S10"]


def test_canonical_csv_normalizes_one_ulp_value_differences(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    columns = ["REGION", "TECHNOLOGY", "YEAR", "VALUE"]
    pd.DataFrame(
        [["RE1", "T1", 2030, 2.7341160000000013e-8]],
        columns=columns,
    ).to_csv(left / "ResidualCapacity.csv", index=False)
    pd.DataFrame(
        [["RE1", "T1", 2030, 2.7341160000000000e-8]],
        columns=columns,
    ).to_csv(right / "ResidualCapacity.csv", index=False)

    canonicalize_csv_directory(left, PARAM_INDEX)
    canonicalize_csv_directory(right, PARAM_INDEX)

    assert (left / "ResidualCapacity.csv").read_bytes() == (
        right / "ResidualCapacity.csv"
    ).read_bytes()


def test_canonical_record_key_uses_dimensions_before_value() -> None:
    dimensions = ["REGION", "TECHNOLOGY", "YEAR"]
    rows = [
        {"REGION": "R1", "TECHNOLOGY": "T10", "YEAR": "2025", "VALUE": "1"},
        {"REGION": "R1", "TECHNOLOGY": "T2", "YEAR": "2030", "VALUE": "9"},
        {"REGION": "R1", "TECHNOLOGY": "T2", "YEAR": "2025", "VALUE": "3"},
    ]

    ordered = sorted(rows, key=lambda row: canonical_record_key(row, dimensions))

    assert [(row["TECHNOLOGY"], row["YEAR"]) for row in ordered] == [
        ("T2", "2025"),
        ("T2", "2030"),
        ("T10", "2025"),
    ]
