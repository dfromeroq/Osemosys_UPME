from __future__ import annotations

import pandas as pd
import pytest

from app.services.employment_factors_service import (
    EMPLOYMENT_VARIABLE_BY_FACTOR_TYPE,
    OM_FACTOR_TYPE,
    CONSTRUCTION_FACTOR_TYPE,
    EmploymentComponent,
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

    rows = calculate_employment_outputs(solution, factors=_factors(), mapping=mapping)

    assert len(rows) == 1
    assert rows[0]["variable_name"] == EMPLOYMENT_VARIABLE_BY_FACTOR_TYPE[CONSTRUCTION_FACTOR_TYPE]
    assert rows[0]["source_variable"] == "NewCapacity"
    assert rows[0]["job_type"] == "Direct"
    assert rows[0]["model_capacity_mw"] == pytest.approx(1000.0)
    assert rows[0]["value"] == pytest.approx(2000.0)


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

    rows = calculate_employment_outputs(solution, factors=_factors(), mapping=mapping)

    assert len(rows) == 1
    assert rows[0]["variable_name"] == EMPLOYMENT_VARIABLE_BY_FACTOR_TYPE[OM_FACTOR_TYPE]
    assert rows[0]["source_variable"] == "AccumulatedNewCapacity"
    assert rows[0]["region_id"] == 1
    assert rows[0]["technology_id"] == 2
    assert rows[0]["value"] == pytest.approx(500.0)


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

    rows = calculate_employment_outputs(solution, factors=_factors(), mapping=mapping)

    assert len(rows) == 1
    assert rows[0]["value"] == pytest.approx(8000.0)
    assert len(rows[0]["components"]) == 2
    assert rows[0]["components"][1]["capacity_mw"] == pytest.approx(600.0)
