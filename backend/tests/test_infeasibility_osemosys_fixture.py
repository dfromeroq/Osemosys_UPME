from __future__ import annotations

from pathlib import Path

from app.simulation.core.infeasibility_analysis import InfeasibilityReport, analyze
from app.simulation.core.instance_builder import build_instance
from app.simulation.core.model_definition import create_abstract_model


def _write(root: Path, name: str, content: str) -> None:
    (root / f"{name}.csv").write_text(content, encoding="utf-8")


def _base_demand_fixture(root: Path, *, emission: bool = False) -> None:
    sets = [
        ("REGION", "R1"),
        ("YEAR", "2030"),
        ("TECHNOLOGY", "PWR"),
        ("TIMESLICE", "L1"),
        ("FUEL", "ELC"),
        ("MODE_OF_OPERATION", "1"),
    ]
    if emission:
        sets.append(("EMISSION", "CO2"))
    for set_name, value in sets:
        _write(root, set_name, f"VALUE\n{value}\n")
    _write(root, "YearSplit", "TIMESLICE,YEAR,VALUE\nL1,2030,1\n")
    _write(
        root,
        "SpecifiedAnnualDemand",
        "REGION,FUEL,YEAR,VALUE\nR1,ELC,2030,10\n",
    )
    _write(
        root,
        "SpecifiedDemandProfile",
        "REGION,FUEL,TIMESLICE,YEAR,VALUE\nR1,ELC,L1,2030,1\n",
    )
    _write(
        root,
        "OutputActivityRatio",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,FUEL,YEAR,VALUE\n"
        "R1,PWR,1,ELC,2030,1\n",
    )


def _diagnose(root: Path, *, has_udc: bool = False) -> InfeasibilityReport:
    instance = build_instance(
        create_abstract_model(has_storage=False, has_udc=has_udc),
        str(root),
        has_storage=False,
        has_udc=has_udc,
    )
    lp_path = root / "fixture.lp"
    instance.write(str(lp_path), io_options={"symbolic_solver_labels": True})
    return analyze(
        solution={
            "solver_name": "highs",
            "solver_status": "infeasible",
            "infeasibility_diagnostics": {},
        },
        instance=instance,
        csv_dir=root,
        lp_path=lp_path,
    )


def _assert_certified(report: InfeasibilityReport) -> None:
    assert report.classification.code == "INFEASIBLE_CERTIFIED"
    assert report.certificate.validated is True
    assert report.iis.irreducible is True
    assert report.feasibility_relaxation.available is True


def test_capacity_zero_fixture_explains_and_quantifies_infeasibility(
    tmp_path: Path,
) -> None:
    _base_demand_fixture(tmp_path)
    _write(
        tmp_path,
        "TotalAnnualMaxCapacity",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2030,0\n",
    )

    report = _diagnose(tmp_path)

    _assert_certified(report)
    assert report.structural_findings[0]["code"] == (
        "DEMAND_WITH_ONLY_BLOCKED_PRODUCERS"
    )
    [change] = report.feasibility_relaxation.relaxations
    assert change.constraint_type == "TotalAnnualMaxCapacityConstraint"
    assert change.side == "UB"
    assert change.slack == 10.0


def test_emission_limit_fixture_recommends_required_relaxation(tmp_path: Path) -> None:
    _base_demand_fixture(tmp_path, emission=True)
    _write(
        tmp_path,
        "EmissionActivityRatio",
        "REGION,TECHNOLOGY,EMISSION,MODE_OF_OPERATION,YEAR,VALUE\n"
        "R1,PWR,CO2,1,2030,1\n",
    )
    _write(
        tmp_path,
        "AnnualEmissionLimit",
        "REGION,EMISSION,YEAR,VALUE\nR1,CO2,2030,0\n",
    )

    report = _diagnose(tmp_path)

    _assert_certified(report)
    [change] = report.feasibility_relaxation.relaxations
    assert change.constraint_type == "AnnualEmissionsLimit"
    assert change.slack == 10.0


def test_reserve_margin_fixture_quantifies_missing_capacity(tmp_path: Path) -> None:
    _base_demand_fixture(tmp_path)
    _write(
        tmp_path,
        "ReserveMarginTagTechnology",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2030,1\n",
    )
    _write(
        tmp_path,
        "ReserveMarginTagFuel",
        "REGION,FUEL,YEAR,VALUE\nR1,ELC,2030,1\n",
    )
    _write(tmp_path, "ReserveMargin", "REGION,YEAR,VALUE\nR1,2030,1.2\n")
    _write(
        tmp_path,
        "TotalAnnualMaxCapacity",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2030,10\n",
    )

    report = _diagnose(tmp_path)

    _assert_certified(report)
    [change] = report.feasibility_relaxation.relaxations
    assert change.constraint_type == "TotalAnnualMaxCapacityConstraint"
    assert change.slack == 2.0


def test_udc_fixture_quantifies_contradictory_capacity_limit(tmp_path: Path) -> None:
    _base_demand_fixture(tmp_path)
    _write(tmp_path, "UDC", "VALUE\nU1\n")
    _write(tmp_path, "UDCTag", "REGION,UDC,VALUE\nR1,U1,0\n")
    _write(
        tmp_path,
        "UDCMultiplierTotalCapacity",
        "REGION,TECHNOLOGY,UDC,YEAR,VALUE\nR1,PWR,U1,2030,1\n",
    )
    _write(
        tmp_path,
        "UDCConstant",
        "REGION,UDC,YEAR,VALUE\nR1,U1,2030,0\n",
    )

    report = _diagnose(tmp_path, has_udc=True)

    _assert_certified(report)
    [change] = report.feasibility_relaxation.relaxations
    assert change.constraint_type == "UDC1_UserDefinedConstraintInequality"
    assert change.slack == 10.0
