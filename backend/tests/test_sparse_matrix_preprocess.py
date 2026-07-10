from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.simulation.core.data_processing import (
    completar_Matrix_Act_Ratio,
    completar_Matrix_Cost,
    completar_Matrix_Emission,
    completar_Matrix_Storage,
)


def _write_set(root: Path, name: str, values: list[object]) -> None:
    pd.DataFrame({"VALUE": values}).to_csv(root / f"{name}.csv", index=False)


def _sorted(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    return df.sort_values(list(df.columns)).reset_index(drop=True)


@pytest.mark.parametrize(
    ("filename", "columns", "rows", "function"),
    [
        (
            "InputActivityRatio.csv",
            ["REGION", "TECHNOLOGY", "FUEL", "MODE_OF_OPERATION", "YEAR", "VALUE"],
            [["RE1", "T1", "F1", "1.0", 2030, 2.0], ["RE1", "T2", "F2", "2", 2031, 3.0]],
            completar_Matrix_Act_Ratio,
        ),
        (
            "EmissionActivityRatio.csv",
            ["REGION", "TECHNOLOGY", "EMISSION", "MODE_OF_OPERATION", "YEAR", "VALUE"],
            [["RE1", "T1", "E1", "1.0", 2030, 2.0], ["RE1", "T2", "E1", "2", 2031, 3.0]],
            completar_Matrix_Emission,
        ),
        (
            "VariableCost.csv",
            ["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR", "VALUE"],
            [["RE1", "T1", "1.0", 2030, 2.0], ["RE1", "T2", "2", 2031, 3.0]],
            completar_Matrix_Cost,
        ),
        (
            "TechnologyToStorage.csv",
            ["REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION", "VALUE"],
            [["RE1", "T1", "S1", "1.0", 2.0], ["RE1", "T2", "S1", "2", 3.0]],
            completar_Matrix_Storage,
        ),
    ],
)
def test_sparse_preprocess_matches_legacy_useful_rows(
    tmp_path, monkeypatch, filename, columns, rows, function
) -> None:
    legacy = tmp_path / "legacy"
    sparse = tmp_path / "sparse"
    legacy.mkdir()
    sparse.mkdir()
    for root in (legacy, sparse):
        _write_set(root, "TECHNOLOGY", ["T1", "T2"])
        _write_set(root, "FUEL", ["F1", "F2"])
        _write_set(root, "EMISSION", ["E1"])
        _write_set(root, "MODE_OF_OPERATION", [1, 2])
        _write_set(root, "YEAR", [2030, 2031])
        _write_set(root, "STORAGE", ["S1"])
        pd.DataFrame(rows, columns=columns).to_csv(root / filename, index=False)

    monkeypatch.setenv("OSEMOSYS_SPARSE_MATRIX_PREPROCESS", "0")
    function(str(legacy) + "/", filename)
    monkeypatch.setenv("OSEMOSYS_SPARSE_MATRIX_PREPROCESS", "1")
    function(str(sparse) + "/", filename)

    pd.testing.assert_frame_equal(_sorted(legacy / filename), _sorted(sparse / filename))
