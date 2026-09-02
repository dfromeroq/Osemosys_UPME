from __future__ import annotations

import pandas as pd
import pytest

from app.services.employment_factors_service import (
    OM_FACTOR_TYPE,
    CONSTRUCTION_FACTOR_TYPE,
    EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT,
    EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT_PRE_HORIZON,
    EMPLOYMENT_FTEYEAR_OM_DIRECT_CUMULATIVE_IN_HORIZON,
    EMPLOYMENT_FTEYEAR_TOTAL_DIRECT_CUMULATIVE_IN_HORIZON,
    EMPLOYMENT_FTE_CONSMANU_DIRECT_ANNUALIZED_IN_HORIZON,
    EMPLOYMENT_FTE_OM_DIRECT_ANNUAL,
    EMPLOYMENT_FTE_TOTAL_DIRECT_ANNUAL_IN_HORIZON,
    EmploymentComponent,
    TechnologyAssumption,
    calculate_employment_outputs,
    load_technology_mapping,
    pj_per_year_to_mw,
)


def _factors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Technology": "Utility-scale solar PV",
                "Year": 2025,
                "Factor_Type": CONSTRUCTION_FACTOR_TYPE,
                "Job_Type": "Direct",
                "Unit": "job-yr/MW",
                "Source": "Test",
                "Value_Numeric": 2.0,
            },
            {
                "Technology": "Utility-scale solar PV",
                "Year": 2025,
                "Factor_Type": CONSTRUCTION_FACTOR_TYPE,
                "Job_Type": "Indirect",
                "Unit": "job-yr/MW",
                "Source": "Test",
                "Value_Numeric": 99.0,
            },
            {
                "Technology": "Battery storage (grid)",
                "Year": 2025,
                "Factor_Type": CONSTRUCTION_FACTOR_TYPE,
                "Job_Type": "Direct",
                "Unit": "job-yr/MW",
                "Source": "Test",
                "Value_Numeric": 10.0,
            },
            {
                "Technology": "Utility-scale solar PV",
                "Year": 2025,
                "Factor_Type": OM_FACTOR_TYPE,
                "Job_Type": "Direct",
                "Unit": "job/MW",
                "Source": "Test",
                "Value_Numeric": 0.5,
            },
        ]
    )


def _assumptions() -> dict[str, TechnologyAssumption]:
    return {
        "Utility-scale solar PV": TechnologyAssumption(
            employment_technology="Utility-scale solar PV",
            construction_time_years=1.0,
            lifetime_years=25.0,
        ),
        "Battery storage (grid)": TechnologyAssumption(
            employment_technology="Battery storage (grid)",
            construction_time_years=1.0,
            lifetime_years=15.0,
        ),
    }


def _by_variable(rows: list[dict], variable_name: str) -> list[dict]:
    return [row for row in rows if row["variable_name"] == variable_name]


def test_pj_per_year_to_mw_uses_documented_conversion() -> None:
    assert pj_per_year_to_mw(31.5576) == pytest.approx(1000.0)


def test_load_technology_mapping_uses_model_floating_wind_code() -> None:
    mapping = load_technology_mapping()

    assert "PWRWNDOFS_FLO" in mapping
    assert "PWRWNDOFS_FLT" not in mapping
    assert mapping["PWRWNDOFS_FLO"][0].employment_technology == "Offshore wind (floating)"


def test_calculate_employment_outputs_uses_new_capacity_for_construction_only() -> None:
    solution = {
        "new_capacity": [
            {
                "region_id": 1,
                "technology_id": 2,
                "region_name": "RE1",
                "technology_name": "PWRSOLUGE",
                "year": 2025,
                "new_capacity": 31.5576,
            }
        ],
        "intermediate_variables": {},
    }
    mapping = {"PWRSOLUGE": [EmploymentComponent("Utility-scale solar PV")]}

    rows = calculate_employment_outputs(
        solution,
        factors=_factors(),
        mapping=mapping,
        assumptions=_assumptions(),
    )

    cm_rows = _by_variable(rows, EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT)
    assert len(cm_rows) == 1
    assert cm_rows[0]["source_variable"] == "NewCapacity"
    assert cm_rows[0]["job_type"] == "Direct"
    assert cm_rows[0]["model_capacity_mw"] == pytest.approx(1000.0)
    assert cm_rows[0]["value"] == pytest.approx(2000.0)

    annualized = _by_variable(
        rows,
        EMPLOYMENT_FTE_CONSMANU_DIRECT_ANNUALIZED_IN_HORIZON,
    )
    assert len(annualized) == 1
    assert annualized[0]["year"] == 2025
    assert annualized[0]["value"] == pytest.approx(2000.0)


def test_calculate_employment_outputs_uses_accumulated_new_capacity_for_om() -> None:
    solution = {
        "new_capacity": [],
        "intermediate_variables": {
            "AccumulatedNewCapacity": [
                {"index": ["RE1", "PWRSOLUGE", 2025], "value": 31.5576},
            ],
        },
        "dimension_lookups": {
            "REGION": {"RE1": 1},
            "TECHNOLOGY": {"PWRSOLUGE": 2},
        },
    }
    mapping = {"PWRSOLUGE": [EmploymentComponent("Utility-scale solar PV")]}

    rows = calculate_employment_outputs(
        solution,
        factors=_factors(),
        mapping=mapping,
        assumptions=_assumptions(),
    )

    om_rows = _by_variable(rows, EMPLOYMENT_FTE_OM_DIRECT_ANNUAL)
    assert len(om_rows) == 1
    assert om_rows[0]["source_variable"] == "AccumulatedNewCapacity"
    assert om_rows[0]["region_id"] == 1
    assert om_rows[0]["technology_id"] == 2
    assert om_rows[0]["value"] == pytest.approx(500.0)

    cumulative = _by_variable(rows, EMPLOYMENT_FTEYEAR_OM_DIRECT_CUMULATIVE_IN_HORIZON)
    assert len(cumulative) == 1
    assert cumulative[0]["value"] == pytest.approx(500.0)


def test_calculate_employment_outputs_sums_hybrid_solar_battery_components() -> None:
    solution = {
        "new_capacity": [
            {
                "region_id": 1,
                "technology_id": 2,
                "region_name": "RE1",
                "technology_name": "PWRSOLUGE_BAT",
                "year": 2025,
                "new_capacity": 31.5576,
            }
        ],
        "intermediate_variables": {},
    }
    mapping = {
        "PWRSOLUGE_BAT": [
            EmploymentComponent("Utility-scale solar PV", multiplier=1.0),
            EmploymentComponent("Battery storage (grid)", multiplier=0.6),
        ]
    }

    rows = calculate_employment_outputs(
        solution,
        factors=_factors(),
        mapping=mapping,
        assumptions=_assumptions(),
    )

    cm_rows = _by_variable(rows, EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT)
    assert len(cm_rows) == 1
    assert cm_rows[0]["value"] == pytest.approx(8000.0)
    assert len(cm_rows[0]["components"]) == 2
    assert cm_rows[0]["components"][1]["capacity_mw"] == pytest.approx(600.0)


def test_calculate_employment_outputs_splits_pre_horizon_construction() -> None:
    solution = {
        "new_capacity": [
            {
                "region_id": 1,
                "technology_id": 2,
                "region_name": "RE1",
                "technology_name": "PWRSOLUGE",
                "year": 2025,
                "new_capacity": 47.3364,
            }
        ],
        "intermediate_variables": {},
    }
    mapping = {"PWRSOLUGE": [EmploymentComponent("Utility-scale solar PV")]}
    assumptions = {
        "Utility-scale solar PV": TechnologyAssumption(
            employment_technology="Utility-scale solar PV",
            construction_time_years=3.0,
            lifetime_years=25.0,
        )
    }

    rows = calculate_employment_outputs(
        solution,
        factors=_factors(),
        mapping=mapping,
        assumptions=assumptions,
    )

    cm_original = _by_variable(rows, EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT)[0]
    pre_horizon = _by_variable(rows, EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT_PRE_HORIZON)[0]
    annualized = _by_variable(
        rows,
        EMPLOYMENT_FTE_CONSMANU_DIRECT_ANNUALIZED_IN_HORIZON,
    )

    assert cm_original["value"] == pytest.approx(3000.0)
    assert pre_horizon["value"] == pytest.approx(2000.0)
    assert len(annualized) == 1
    assert annualized[0]["year"] == 2025
    assert annualized[0]["value"] == pytest.approx(1000.0)


def test_calculate_employment_outputs_cumulative_total_combines_cm_and_om() -> None:
    solution = {
        "new_capacity": [
            {
                "region_id": 1,
                "technology_id": 2,
                "region_name": "RE1",
                "technology_name": "PWRSOLUGE",
                "year": 2025,
                "new_capacity": 31.5576,
            }
        ],
        "intermediate_variables": {
            "AccumulatedNewCapacity": [
                {"index": ["RE1", "PWRSOLUGE", 2025], "value": 31.5576},
                {"index": ["RE1", "PWRSOLUGE", 2026], "value": 63.1152},
            ],
        },
        "dimension_lookups": {
            "REGION": {"RE1": 1},
            "TECHNOLOGY": {"PWRSOLUGE": 2},
        },
    }
    factors = pd.concat(
        [
            _factors(),
            pd.DataFrame(
                [
                    {
                        "Technology": "Utility-scale solar PV",
                        "Year": 2026,
                        "Factor_Type": OM_FACTOR_TYPE,
                        "Job_Type": "Direct",
                        "Unit": "job/MW",
                        "Source": "Test",
                        "Value_Numeric": 0.5,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    mapping = {"PWRSOLUGE": [EmploymentComponent("Utility-scale solar PV")]}

    rows = calculate_employment_outputs(
        solution,
        factors=factors,
        mapping=mapping,
        assumptions=_assumptions(),
    )

    total_annual = _by_variable(rows, EMPLOYMENT_FTE_TOTAL_DIRECT_ANNUAL_IN_HORIZON)
    total_by_year = {row["year"]: row["value"] for row in total_annual}
    assert total_by_year[2025] == pytest.approx(2500.0)
    assert total_by_year[2026] == pytest.approx(1000.0)

    cumulative_total = _by_variable(
        rows,
        EMPLOYMENT_FTEYEAR_TOTAL_DIRECT_CUMULATIVE_IN_HORIZON,
    )
    cumulative_by_year = {row["year"]: row["value"] for row in cumulative_total}
    assert cumulative_by_year[2025] == pytest.approx(2500.0)
    assert cumulative_by_year[2026] == pytest.approx(3500.0)
