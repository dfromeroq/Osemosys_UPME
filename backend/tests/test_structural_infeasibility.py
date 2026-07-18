from __future__ import annotations

from pathlib import Path

from app.simulation.core.data_validation import detect_bound_conflicts
from app.simulation.core.structural_infeasibility import (
    analyze_structural_infeasibility,
)


def _write(path: Path, name: str, text: str) -> None:
    (path / f"{name}.csv").write_text(text, encoding="utf-8")


def _specified_demand(path: Path) -> None:
    _write(path, "SpecifiedAnnualDemand", "REGION,FUEL,YEAR,VALUE\nR1,ELC,2030,10\n")
    _write(
        path,
        "SpecifiedDemandProfile",
        "REGION,FUEL,TIMESLICE,YEAR,VALUE\nR1,ELC,L1,2030,1\n",
    )


def test_detects_activity_minimum_greater_than_maximum(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "TotalTechnologyAnnualActivityLowerLimit",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2030,10\n",
    )
    _write(
        tmp_path,
        "TotalTechnologyAnnualActivityUpperLimit",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2030,5\n",
    )

    conflicts = detect_bound_conflicts(tmp_path)

    assert len(conflicts) == 1
    assert conflicts[0].severity == "real_conflict"
    assert conflicts[0].gap == 5.0
    findings = analyze_structural_infeasibility(tmp_path)
    assert findings[0].code == "PARAMETER_BOUND_CONFLICT"


def test_detects_residual_capacity_above_total_maximum(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "ResidualCapacity",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2030,12\n",
    )
    _write(
        tmp_path,
        "TotalAnnualMaxCapacity",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2030,10\n",
    )

    findings = analyze_structural_infeasibility(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "RESIDUAL_CAPACITY_EXCEEDS_MAXIMUM"
    assert findings[0].values["gap"] == 2.0


def test_detects_positive_demand_without_local_producer(tmp_path: Path) -> None:
    _specified_demand(tmp_path)

    findings = analyze_structural_infeasibility(tmp_path)

    assert [finding.code for finding in findings] == [
        "DEMAND_WITHOUT_LOCAL_PRODUCER"
    ]
    assert findings[0].dimensions == {
        "REGION": "R1",
        "FUEL": "ELC",
        "YEAR": "2030",
    }


def test_detects_demand_fuel_in_cycle_without_primary_input_route(tmp_path: Path) -> None:
    _write(tmp_path, "AccumulatedAnnualDemand", "REGION,FUEL,YEAR,VALUE\nR1,ELC,2030,10\n")
    _write(
        tmp_path,
        "InputActivityRatio",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,FUEL,YEAR,VALUE\n"
        "R1,MAKE_ELC,1,GAS,2030,1\nR1,MAKE_GAS,1,ELC,2030,1\n",
    )
    _write(
        tmp_path,
        "OutputActivityRatio",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,FUEL,YEAR,VALUE\n"
        "R1,MAKE_ELC,1,ELC,2030,1\nR1,MAKE_GAS,1,GAS,2030,1\n",
    )

    findings = analyze_structural_infeasibility(tmp_path)

    assert [finding.code for finding in findings] == [
        "DEMAND_FUEL_WITHOUT_PRIMARY_INPUT_ROUTE"
    ]
    assert findings[0].values["primary_processes"] == 0


def test_detects_demand_when_all_producers_are_explicitly_blocked(tmp_path: Path) -> None:
    _specified_demand(tmp_path)
    _write(
        tmp_path,
        "OutputActivityRatio",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,FUEL,YEAR,VALUE\n"
        "R1,PWR,1,ELC,2030,1\n",
    )
    _write(
        tmp_path,
        "TotalAnnualMaxCapacity",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2030,0\n",
    )

    findings = analyze_structural_infeasibility(tmp_path)

    assert [finding.code for finding in findings] == [
        "DEMAND_WITH_ONLY_BLOCKED_PRODUCERS"
    ]
    reasons = findings[0].values["blocking_reasons"]
    assert reasons == {"PWR": ["total_max_capacity_zero"]}


def test_detects_activity_minimum_above_capacity_and_live_investment(tmp_path: Path) -> None:
    _write(tmp_path, "YEAR", "VALUE\n2022\n2023\n")
    _write(tmp_path, "YearSplit", "TIMESLICE,YEAR,VALUE\nL1,2023,1\n")
    _write(
        tmp_path,
        "TotalTechnologyAnnualActivityLowerLimit",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2023,4\n",
    )
    _write(
        tmp_path,
        "ResidualCapacity",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2023,3\n",
    )
    _write(
        tmp_path,
        "TotalAnnualMaxCapacityInvestment",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2022,0\nR1,PWR,2023,0.5\n",
    )
    _write(tmp_path, "OperationalLife", "REGION,TECHNOLOGY,VALUE\nR1,PWR,20\n")
    _write(tmp_path, "CapacityToActivityUnit", "REGION,TECHNOLOGY,VALUE\nR1,PWR,1\n")

    findings = analyze_structural_infeasibility(tmp_path)

    assert [finding.code for finding in findings] == [
        "MANDATED_ANNUAL_ACTIVITY_WITHOUT_USABLE_CAPACITY"
    ]
    assert findings[0].values["capacity_activity_upper_bound"] == 3.5
    assert findings[0].values["gap"] == 0.5


def test_detects_demand_without_usable_capacity_or_investment_path(tmp_path: Path) -> None:
    _specified_demand(tmp_path)
    _write(tmp_path, "YEAR", "VALUE\n2030\n")
    _write(
        tmp_path,
        "OutputActivityRatio",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,FUEL,YEAR,VALUE\n"
        "R1,PWR,1,ELC,2030,1\n",
    )
    _write(
        tmp_path,
        "TotalAnnualMaxCapacityInvestment",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2030,0\n",
    )
    _write(
        tmp_path,
        "ResidualCapacity",
        "REGION,TECHNOLOGY,YEAR,VALUE\nR1,PWR,2030,0\n",
    )

    findings = analyze_structural_infeasibility(tmp_path)

    assert [finding.code for finding in findings] == [
        "DEMAND_WITHOUT_USABLE_CAPACITY_PATH"
    ]
    assert findings[0].values["blocking_reasons"] == {
        "PWR": ["no_residual_or_live_investment_path"]
    }


def test_does_not_report_false_positive_with_active_producer(tmp_path: Path) -> None:
    _specified_demand(tmp_path)
    _write(
        tmp_path,
        "OutputActivityRatio",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,FUEL,YEAR,VALUE\n"
        "R1,PWR,1,ELC,2030,1\n",
    )

    assert analyze_structural_infeasibility(tmp_path) == []


def test_detects_invalid_storage_fraction_and_negative_rate(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "MinStorageCharge",
        "REGION,STORAGE,YEAR,VALUE\nR1,BAT,2030,1.2\n",
    )
    _write(
        tmp_path,
        "StorageMaxChargeRate",
        "REGION,STORAGE,VALUE\nR1,BAT,-1\n",
    )

    findings = analyze_structural_infeasibility(tmp_path)

    assert {finding.code for finding in findings} == {
        "INVALID_MIN_STORAGE_CHARGE",
        "NEGATIVE_STORAGE_RATE_LIMIT",
    }


def test_regional_demand_cannot_rely_on_unmodeled_trade(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "AccumulatedAnnualDemand",
        "REGION,FUEL,YEAR,VALUE\nR2,ELC,2030,5\n",
    )
    _write(
        tmp_path,
        "OutputActivityRatio",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,FUEL,YEAR,VALUE\n"
        "R1,PWR,1,ELC,2030,1\n",
    )
    _write(
        tmp_path,
        "TradeRoute",
        "REGION,FUEL,REGION2,YEAR,VALUE\nR1,ELC,R2,2030,5\n",
    )

    findings = analyze_structural_infeasibility(tmp_path)

    assert {finding.code for finding in findings} == {
        "DEMAND_WITHOUT_LOCAL_PRODUCER",
        "TRADE_ROUTE_NOT_MODELED",
    }


def test_warns_that_positive_interregional_trade_is_not_modeled(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "TradeRoute",
        "REGION,FUEL,REGION2,YEAR,VALUE\nR1,ELC,R2,2030,5\n",
    )

    findings = analyze_structural_infeasibility(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "TRADE_ROUTE_NOT_MODELED"
    assert findings[0].severity == "WARNING"
