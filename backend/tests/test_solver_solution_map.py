"""Tests de mapeo selectivo de solución HiGHS → instancia Pyomo."""

from __future__ import annotations

import pyomo.environ as pyo
import pytest

from app.simulation.core.model_definition import create_abstract_model
from app.simulation.core.solver import (
    _count_nonzero_var_values,
    _ensure_rate_of_activity_mapped,
    _map_all_vars_from_col_map,
    _pyomo_name_to_lp,
    _set_var_value_from_col_map,
)


@pytest.fixture
def tiny_instance() -> pyo.ConcreteModel:
    abstract = create_abstract_model(has_storage=False, has_udc=False)
    data = {
        None: {
            "YEAR": [2020],
            "TECHNOLOGY": ["T1"],
            "TIMESLICE": ["TS1"],
            "FUEL": ["ELC"],
            "EMISSION": ["CO2"],
            "MODE_OF_OPERATION": ["1"],
            "REGION": ["R1"],
            "YearSplit": {("TS1", 2020): 1.0},
            "OutputActivityRatio": {("R1", "T1", "ELC", "1", 2020): 1.0},
        }
    }
    instance = abstract.create_instance(data)
    instance.RateOfActivity["R1", "TS1", "T1", "1", 2020].set_value(0.0)
    return instance


class TestSelectiveSolutionMap:
    def test_count_nonzero_var_values(self, tiny_instance) -> None:
        assert _count_nonzero_var_values(tiny_instance.RateOfActivity) == 0
        tiny_instance.RateOfActivity["R1", "TS1", "T1", "1", 2020].set_value(7.5)
        assert _count_nonzero_var_values(tiny_instance.RateOfActivity) == 1

    def test_ensure_rate_of_activity_mapped_fallback(self, tiny_instance) -> None:
        idx = ("R1", "TS1", "T1", "1", 2020)
        pyomo_name = tiny_instance.RateOfActivity[idx].name
        lp_name = _pyomo_name_to_lp(pyomo_name)
        col_map = {lp_name: 12.5}

        _ensure_rate_of_activity_mapped(
            tiny_instance, col_map, selective_was_used=True
        )
        assert tiny_instance.RateOfActivity[idx].value == pytest.approx(12.5)
        assert _count_nonzero_var_values(tiny_instance.RateOfActivity) == 1

    def test_map_all_vars_from_col_map_highs_underscore(self, tiny_instance) -> None:
        idx = ("R1", "TS1", "T1", "1", 2020)
        var = tiny_instance.RateOfActivity[idx]
        highs_name = "RateOfActivity(R1_TS1_T1_1_2020)"
        _map_all_vars_from_col_map(tiny_instance, {highs_name: 3.0})
        assert var.value == pytest.approx(3.0)

    def test_set_var_value_from_col_map_pyomo_and_lp_names(self, tiny_instance) -> None:
        idx = ("R1", "TS1", "T1", "1", 2020)
        var = tiny_instance.RateOfActivity[idx]
        pyomo_name = var.name
        lp_name = _pyomo_name_to_lp(pyomo_name)

        _set_var_value_from_col_map(var, {pyomo_name: 1.25})
        assert var.value == pytest.approx(1.25)

        var.set_value(0.0)
        _set_var_value_from_col_map(var, {lp_name: 2.5})
        assert var.value == pytest.approx(2.5)
