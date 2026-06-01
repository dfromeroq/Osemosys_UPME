from __future__ import annotations

from pathlib import Path

import pytest
from pyomo.environ import AbstractModel, Param, Set

from app.simulation.core import instance_builder as ib


def test_coerce_index_value_year_and_mode_as_int() -> None:
    assert ib._coerce_index_value("YEAR", "2022") == 2022
    assert ib._coerce_index_value("MODE_OF_OPERATION", "1") == 1


def test_coerce_index_value_string_dims_unchanged() -> None:
    assert ib._coerce_index_value("REGION", "RE1") == "RE1"
    assert ib._coerce_index_value("TECHNOLOGY", "DEMAGFDSL") == "DEMAGFDSL"
    assert ib._coerce_index_value("FUEL", "DSL") == "DSL"


def test_load_param_pandas_matches_dataportal_index_types(tmp_path: Path) -> None:
    """El índice del param debe ser compatible con sets cargados vía filename."""
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()

    (csv_dir / "REGION.csv").write_text("REGION\nRE1\n", encoding="utf-8")
    (csv_dir / "TECHNOLOGY.csv").write_text("TECHNOLOGY\nDEMAGFDSL\n", encoding="utf-8")
    (csv_dir / "FUEL.csv").write_text("FUEL\nDSL\n", encoding="utf-8")
    (csv_dir / "MODE_OF_OPERATION.csv").write_text("MODE_OF_OPERATION\n1\n", encoding="utf-8")
    (csv_dir / "YEAR.csv").write_text("YEAR\n2022\n", encoding="utf-8")
    (csv_dir / "InputActivityRatio.csv").write_text(
        "REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR,VALUE\n"
        "RE1,DEMAGFDSL,DSL,1,2022,1.0\n",
        encoding="utf-8",
    )

    model = AbstractModel()
    model.REGION = Set()
    model.TECHNOLOGY = Set()
    model.FUEL = Set()
    model.MODE_OF_OPERATION = Set()
    model.YEAR = Set()
    model.InputActivityRatio = Param(
        model.REGION,
        model.TECHNOLOGY,
        model.FUEL,
        model.MODE_OF_OPERATION,
        model.YEAR,
        default=0.0,
    )

    instance = ib.build_instance(model, str(csv_dir), has_storage=False, has_udc=False)

    assert ("RE1", "DEMAGFDSL", "DSL", 1, 2022) in instance.InputActivityRatio
    assert instance.InputActivityRatio["RE1", "DEMAGFDSL", "DSL", 1, 2022] == pytest.approx(1.0)


def test_csv_has_data_short_value_header(tmp_path: Path) -> None:
    """CSVs con header 'VALUE' y un solo valor corto (ej. '1') deben detectarse correctamente."""
    f = tmp_path / "MODE_OF_OPERATION.csv"
    f.write_text("VALUE\n1\n", encoding="utf-8")
    assert ib._csv_has_data(str(f)) is True

    f2 = tmp_path / "empty.csv"
    f2.write_text("VALUE\n", encoding="utf-8")
    assert ib._csv_has_data(str(f2)) is False


def test_load_param_pandas_with_value_header_sets(tmp_path: Path) -> None:
    """Reproduce el bug original: sets con header 'VALUE' y MODE_OF_OPERATION='1' (8 bytes)."""
    csv_dir = tmp_path / "csv_val"
    csv_dir.mkdir()

    (csv_dir / "REGION.csv").write_text("VALUE\nRE1\n", encoding="utf-8")
    (csv_dir / "TECHNOLOGY.csv").write_text("VALUE\nDEMAGFDSL\n", encoding="utf-8")
    (csv_dir / "FUEL.csv").write_text("VALUE\nDSL\n", encoding="utf-8")
    (csv_dir / "MODE_OF_OPERATION.csv").write_text("VALUE\n1\n", encoding="utf-8")
    (csv_dir / "YEAR.csv").write_text("VALUE\n2022\n", encoding="utf-8")
    (csv_dir / "InputActivityRatio.csv").write_text(
        "REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR,VALUE\n"
        "RE1,DEMAGFDSL,DSL,1,2022,1.0\n",
        encoding="utf-8",
    )

    model = AbstractModel()
    model.REGION = Set()
    model.TECHNOLOGY = Set()
    model.FUEL = Set()
    model.MODE_OF_OPERATION = Set()
    model.YEAR = Set()
    model.InputActivityRatio = Param(
        model.REGION,
        model.TECHNOLOGY,
        model.FUEL,
        model.MODE_OF_OPERATION,
        model.YEAR,
        default=0.0,
    )

    instance = ib.build_instance(model, str(csv_dir), has_storage=False, has_udc=False)
    assert ("RE1", "DEMAGFDSL", "DSL", 1, 2022) in instance.InputActivityRatio
    assert instance.InputActivityRatio["RE1", "DEMAGFDSL", "DSL", 1, 2022] == pytest.approx(1.0)


def test_build_instance_respects_fast_dataportal_env(monkeypatch, tmp_path: Path) -> None:
    csv_dir = tmp_path / "csv2"
    csv_dir.mkdir()
    (csv_dir / "REGION.csv").write_text("REGION\nRE1\n", encoding="utf-8")
    (csv_dir / "YEAR.csv").write_text("YEAR\n2022\n", encoding="utf-8")
    (csv_dir / "DiscountRate.csv").write_text("REGION,VALUE\nRE1,0.05\n", encoding="utf-8")

    model = AbstractModel()
    model.REGION = Set()
    model.YEAR = Set()
    model.DiscountRate = Param(model.REGION, default=0.0)

    monkeypatch.setattr(ib, "_USE_PANDAS_DATAPORTAL", False)

    instance = ib.build_instance(model, str(csv_dir), has_storage=False, has_udc=False)
    assert instance.DiscountRate["RE1"] == pytest.approx(0.05)
