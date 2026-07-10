from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_notebook_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "compare_notebook_vs_app.py"
    spec = importlib.util.spec_from_file_location("compare_notebook_sparse_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sparse_completion_preserves_legacy_set_order_for_emission_first(tmp_path) -> None:
    module = _load_notebook_module()
    root = str(tmp_path) + "/"
    for name, values in {
        "REGION": ["RE1"],
        "TECHNOLOGY": ["T1"],
        "FUEL": ["ELC", "OIL"],
        "EMISSION": ["CO2"],
        "MODE_OF_OPERATION": [1],
        "YEAR": [2030],
    }.items():
        pd.DataFrame({"VALUE": values}).to_csv(tmp_path / f"{name}.csv", index=False)

    # Orden de entrada inverso al set FUEL; el cartesiano legacy devuelve ELC primero.
    pd.DataFrame(
        [
            ["RE1", "T1", "OIL", "1.0", 2030, 2.0],
            ["RE1", "T1", "ELC", "1", 2030, 0.1],
        ],
        columns=["REGION", "TECHNOLOGY", "FUEL", "MODE_OF_OPERATION", "YEAR", "VALUE"],
    ).to_csv(tmp_path / "InputActivityRatio.csv", index=False)
    pd.DataFrame(
        [["RE1", "T1", "CO2", "1.0", 2030, 10.0]],
        columns=["REGION", "TECHNOLOGY", "EMISSION", "MODE_OF_OPERATION", "YEAR", "VALUE"],
    ).to_csv(tmp_path / "EmissionActivityRatio.csv", index=False)

    module.completar_Matrix_Act_Ratio(root, "InputActivityRatio.csv")
    module.completar_Matrix_Emission(root, "EmissionActivityRatio.csv")
    module.process_and_save_emission_ratios(
        "EmissionActivityRatio.csv",
        "InputActivityRatio.csv",
        "EmissionActivityRatio.csv",
        root,
    )

    inputs = pd.read_csv(tmp_path / "InputActivityRatio.csv")
    emissions = pd.read_csv(tmp_path / "EmissionActivityRatio.csv")
    assert inputs["FUEL"].tolist() == ["ELC", "OIL"]
    assert emissions["VALUE"].tolist() == [1.0]
