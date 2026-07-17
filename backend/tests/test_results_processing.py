"""Tests unitarios para results_processing.py."""

from __future__ import annotations

from types import SimpleNamespace

import pyomo.environ as pyo
import pytest

from app.simulation.core.model_definition import create_abstract_model
from app.simulation.core.results_processing import (
    RoaAggregates,
    _apply_dense_ratio_fallback_if_needed,
    _coerce_number,
    _coerce_year,
    _collect_intermediate_parts,
    _compute_intermediate_variables,
    _compute_unmet_demand,
    _extract_annual_emissions,
    _extract_dispatch,
    _extract_new_capacity,
    _extract_pyomo_variable,
    _format_dispatch_from_aggregates,
    _format_unmet_demand_from_aggregates,
    _iter_intermediate_entries,
    _materialize_intermediate_dict,
    _precompute_roa_aggregates,
    _precompute_roa_aggregates_loop,
    _precompute_roa_aggregates_pd,
    _safe_extract,
    process_results,
    vars_to_load_from_solution,
)


@pytest.fixture
def mini_instance() -> pyo.ConcreteModel:
    """Modelo mínimo: 1 región, 2 techs, 2 TS, 1 modo, 3 años, 1 fuel, 1 emisión."""
    abstract = create_abstract_model(has_storage=False, has_udc=False)
    data = {
        None: {
            "YEAR": [2020, 2021, 2022],
            "TECHNOLOGY": ["T1", "T2"],
            "TIMESLICE": ["TS1", "TS2"],
            "FUEL": ["ELC"],
            "EMISSION": ["CO2"],
            "MODE_OF_OPERATION": ["1"],
            "REGION": ["R1"],
            "YearSplit": {
                ("TS1", 2020): 0.5,
                ("TS2", 2020): 0.5,
                ("TS1", 2021): 0.5,
                ("TS2", 2021): 0.5,
                ("TS1", 2022): 0.5,
                ("TS2", 2022): 0.5,
            },
            "OutputActivityRatio": {
                ("R1", "T1", "ELC", "1", 2020): 1.0,
                ("R1", "T1", "ELC", "1", 2021): 1.0,
                ("R1", "T1", "ELC", "1", 2022): 1.0,
                ("R1", "T2", "ELC", "1", 2020): 1.0,
                ("R1", "T2", "ELC", "1", 2021): 1.0,
                ("R1", "T2", "ELC", "1", 2022): 1.0,
            },
            "InputActivityRatio": {
                ("R1", "T1", "ELC", "1", 2020): 0.5,
                ("R1", "T1", "ELC", "1", 2021): 0.5,
                ("R1", "T1", "ELC", "1", 2022): 0.5,
            },
            "VariableCost": {
                ("R1", "T1", "1", 2020): 2.0,
                ("R1", "T1", "1", 2021): 2.0,
                ("R1", "T1", "1", 2022): 2.0,
                ("R1", "T2", "1", 2020): 4.0,
                ("R1", "T2", "1", 2021): 4.0,
                ("R1", "T2", "1", 2022): 4.0,
            },
            "Demand": {
                ("R1", "TS1", "ELC", 2020): 50.0,
                ("R1", "TS2", "ELC", 2020): 50.0,
                ("R1", "TS1", "ELC", 2021): 60.0,
                ("R1", "TS2", "ELC", 2021): 60.0,
                ("R1", "TS1", "ELC", 2022): 70.0,
                ("R1", "TS2", "ELC", 2022): 70.0,
            },
            "SpecifiedAnnualDemand": {("R1", "ELC", 2020): 100.0},
            "OperationalLife": {("R1", "T1"): 2, ("R1", "T2"): 2},
            "ResidualCapacity": {("R1", "T1", 2020): 1.0},
        },
    }
    instance = abstract.create_instance(data)

    # Asignar valores de solución manualmente (sin solver).
    instance.RateOfActivity["R1", "TS1", "T1", "1", 2020].set_value(10.0)
    instance.RateOfActivity["R1", "TS2", "T1", "1", 2020].set_value(20.0)
    instance.RateOfActivity["R1", "TS1", "T2", "1", 2020].set_value(5.0)
    instance.RateOfActivity["R1", "TS1", "T1", "1", 2021].set_value(15.0)
    instance.RateOfActivity["R1", "TS2", "T1", "1", 2022].set_value(1e-12)  # podado

    instance.NewCapacity["R1", "T1", 2020].set_value(3.0)
    instance.NewCapacity["R1", "T1", 2021].set_value(2.0)
    instance.NewCapacity["R1", "T2", 2020].set_value(1.0)

    instance.AnnualEmissions["R1", "CO2", 2020].set_value(12.0)
    instance.AnnualEmissions["R1", "CO2", 2021].set_value(8.0)
    instance.AnnualEmissions["R1", "CO2", 2022].set_value(0.0)

    instance.OperatingCost["R1", "T1", 2020].set_value(100.0)
    instance.CapitalInvestment["R1", "T1", 2020].set_value(50.0)

    return instance


@pytest.fixture
def mini_lookups() -> dict:
    return {
        "region_id_by_name": {"R1": 1},
        "technology_id_by_name": {"T1": 10, "T2": 20},
        "region_name_by_id": {1: "R1"},
        "timeslice_id_by_name": {"TS1": 100, "TS2": 200},
    }


@pytest.fixture
def solver_result() -> dict:
    return {
        "objective_value": 123.45,
        "solver_name": "highs",
        "solver_status": "optimal",
    }


class TestCoerceHelpers:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (2020, 2020),
            (2020.0, 2020),
            ("2021", 2021),
            ("2030.0", 2030),
            (None, None),
            ("", None),
            (True, 1),
        ],
    )
    def test_coerce_year(self, value, expected) -> None:
        assert _coerce_year(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, 0.0),
            ("", 0.0),
            ("3.5", 3.5),
            (2, 2.0),
            (True, 1.0),
        ],
    )
    def test_coerce_number(self, value, expected) -> None:
        assert _coerce_number(value) == expected


class TestSafeExtract:
    def test_safe_extract_var_prunes_near_zero(self, mini_instance) -> None:
        raw = _safe_extract(mini_instance.RateOfActivity)
        assert ("R1", "TS2", "T1", "1", 2022) not in raw
        assert raw[("R1", "TS1", "T1", "1", 2020)] == pytest.approx(10.0)

    def test_safe_extract_param_none_to_zero(self, mini_instance) -> None:
        raw = _safe_extract(mini_instance.YearSplit)
        assert raw[("TS1", 2020)] == pytest.approx(0.5)

    def test_safe_extract_cache(self, mini_instance) -> None:
        first = _safe_extract(mini_instance.NewCapacity)
        second = _safe_extract(mini_instance.NewCapacity)
        assert first is second

    def test_safe_extract_falls_back_to_dot_value_when_private_value_none(
        self,
    ) -> None:
        """Simula VarData con _value=None pero .value poblado (post-HiGHS)."""
        from unittest.mock import MagicMock, PropertyMock

        mock_var = MagicMock(spec=pyo.Var)
        mock_vd = MagicMock()
        mock_vd._value = None
        type(mock_vd).value = PropertyMock(return_value=99.0)
        key = ("R1", "TS1", "T1", "1", 2020)
        mock_var._data = {key: mock_vd}
        raw = _safe_extract(mock_var, use_cache=False)
        assert raw[key] == pytest.approx(99.0)


class TestAggregates:
    def test_loop_and_pandas_match(self, mini_instance) -> None:
        loop_agg = _precompute_roa_aggregates_loop(mini_instance)
        pd_agg = _precompute_roa_aggregates_pd(mini_instance)
        assert loop_agg.activity_by_rlty == pytest.approx(pd_agg.activity_by_rlty)
        assert loop_agg.cost_by_rlty == pytest.approx(pd_agg.cost_by_rlty)
        assert loop_agg.prod_by_rfy == pytest.approx(pd_agg.prod_by_rfy)
        assert loop_agg.prod_by_rftly == pytest.approx(pd_agg.prod_by_rftly)
        assert loop_agg.use_by_rftly == pytest.approx(pd_agg.use_by_rftly)

    def test_precompute_entry_point(self, mini_instance) -> None:
        agg = _precompute_roa_aggregates(mini_instance)
        assert agg.activity_by_rlty[("R1", "TS1", "T1", 2020)] == pytest.approx(5.0)
        assert agg.activity_by_rlty[("R1", "TS2", "T1", 2020)] == pytest.approx(10.0)

    def test_dense_ratio_fallback_when_sparse_oar_empty(self, mini_instance) -> None:
        agg = RoaAggregates(
            roa_raw={("R1", "TS1", "T1", "1", 2020): 10.0},
            ys_data={("TS1", 2020): 0.5},
            activity_by_rlty={("R1", "TS1", "T1", 2020): 5.0},
            oar_data={},
            iar_data={},
            prod_by_rftly={},
        )
        fixed = _apply_dense_ratio_fallback_if_needed(mini_instance, agg)
        assert fixed.prod_by_rftly
        assert fixed.oar_data


class TestExtractDispatch:
    def test_dispatch_basic(self, mini_instance, mini_lookups) -> None:
        agg = _precompute_roa_aggregates(mini_instance)
        rows = _format_dispatch_from_aggregates(
            agg,
            mini_lookups["region_id_by_name"],
            mini_lookups["technology_id_by_name"],
            timeslice_id_by_name=mini_lookups["timeslice_id_by_name"],
        )
        by_key = {(r["technology_name"], r["timeslice_name"], r["year"]): r for r in rows}
        assert by_key[("T1", "TS1", 2020)]["dispatch"] == pytest.approx(5.0)
        assert by_key[("T1", "TS2", 2020)]["dispatch"] == pytest.approx(10.0)
        assert by_key[("T1", "TS1", 2020)]["cost"] == pytest.approx(2.0)
        assert by_key[("T1", "TS1", 2020)]["fuel_name"] == "ELC"
        assert by_key[("T1", "TS1", 2020)]["timeslice_id"] == 100

    def test_dispatch_zero_pruning(self, mini_instance, mini_lookups) -> None:
        rows = _extract_dispatch(
            mini_instance,
            mini_lookups["region_id_by_name"],
            mini_lookups["technology_id_by_name"],
        )
        assert all(r["year"] != 2022 or r["technology_name"] != "T1" or r["timeslice_name"] != "TS2" for r in rows)

    def test_dispatch_timeslice_preserved(self, mini_instance, mini_lookups) -> None:
        rows = _extract_dispatch(
            mini_instance,
            mini_lookups["region_id_by_name"],
            mini_lookups["technology_id_by_name"],
            timeslice_id_by_name=mini_lookups["timeslice_id_by_name"],
        )
        assert {r["timeslice_name"] for r in rows} <= {"TS1", "TS2"}


class TestNewCapacity:
    def test_extract_new_capacity(self, mini_instance, mini_lookups) -> None:
        rows = _extract_new_capacity(
            mini_instance,
            mini_lookups["region_id_by_name"],
            mini_lookups["technology_id_by_name"],
        )
        by_key = {(r["technology_name"], r["year"]): r["new_capacity"] for r in rows}
        assert by_key[("T1", 2020)] == pytest.approx(3.0)
        assert by_key[("T1", 2021)] == pytest.approx(2.0)


class TestUnmetDemand:
    def test_unmet_gap(self, mini_instance, mini_lookups) -> None:
        agg = _precompute_roa_aggregates(mini_instance)
        rows = _format_unmet_demand_from_aggregates(agg, mini_lookups["region_id_by_name"])
        by_year = {r["year"]: r["unmet_demand"] for r in rows}
        assert by_year[2020] == pytest.approx(82.5)
        assert by_year[2021] == pytest.approx(112.5)

    def test_unmet_via_wrapper(self, mini_instance, mini_lookups) -> None:
        rows = _compute_unmet_demand(mini_instance, mini_lookups["region_id_by_name"])
        assert rows


class TestAnnualEmissions:
    def test_no_emissions_returns_zeros(self, mini_instance, mini_lookups) -> None:
        rows = _extract_annual_emissions(
            mini_instance,
            mini_lookups["region_id_by_name"],
            ["R1"],
            [2020, 2021],
            [],
        )
        assert all(r["annual_emissions"] == 0.0 for r in rows)

    def test_with_emissions(self, mini_instance, mini_lookups) -> None:
        rows = _extract_annual_emissions(
            mini_instance,
            mini_lookups["region_id_by_name"],
            ["R1"],
            [2020, 2021, 2022],
            ["CO2"],
        )
        by_year = {r["year"]: r["annual_emissions"] for r in rows}
        assert by_year[2020] == pytest.approx(12.0)
        assert by_year[2021] == pytest.approx(8.0)
        assert by_year[2022] == pytest.approx(0.0)


class TestIntermediateVariables:
    def test_capacity_derivatives(self, mini_instance) -> None:
        out = _compute_intermediate_variables(
            mini_instance,
            regions=["R1"],
            technologies=["T1", "T2"],
            years=[2020, 2021, 2022],
            emissions=["CO2"],
            has_storage=False,
            parallel=False,
        )
        assert "TotalCapacityAnnual" in out
        assert "AccumulatedNewCapacity" in out
        assert "ProductionByTechnology" in out
        assert "UseByTechnology" in out

    def test_emission_vars_only_when_emissions(self, mini_instance) -> None:
        with_em = _compute_intermediate_variables(
            mini_instance, ["R1"], ["T1"], [2020], ["CO2"], False, parallel=False,
        )
        without_em = _compute_intermediate_variables(
            mini_instance, ["R1"], ["T1"], [2020], [], False, parallel=False,
        )
        assert "AnnualTechnologyEmission" not in without_em or without_em.get("AnnualTechnologyEmission") is None
        assert "OperatingCost" in with_em

    def test_parallel_matches_sequential(self, mini_instance) -> None:
        kwargs = dict(
            instance=mini_instance,
            regions=["R1"],
            technologies=["T1", "T2"],
            years=[2020, 2021, 2022],
            emissions=["CO2"],
            has_storage=False,
        )
        seq = _compute_intermediate_variables(**kwargs, parallel=False)
        par = _compute_intermediate_variables(**kwargs, parallel=True)
        assert set(seq.keys()) == set(par.keys())
        for name in seq:
            assert len(seq[name]) == len(par[name])
            seq_vals = sorted((tuple(e["index"]), e["value"]) for e in seq[name])
            par_vals = sorted((tuple(e["index"]), e["value"]) for e in par[name])
            assert seq_vals == pytest.approx(par_vals)


class TestProcessResults:
    def test_process_results_structure(
        self, mini_instance, mini_lookups, solver_result,
    ) -> None:
        result = process_results(
            mini_instance,
            solver_result,
            regions=["R1"],
            technologies=["T1", "T2"],
            years=[2020, 2021, 2022],
            emissions=["CO2"],
            has_storage=False,
            region_id_by_name=mini_lookups["region_id_by_name"],
            technology_id_by_name=mini_lookups["technology_id_by_name"],
            region_name_by_id=mini_lookups["region_name_by_id"],
            timeslice_id_by_name=mini_lookups["timeslice_id_by_name"],
            parallel=False,
        )
        for key in (
            "dispatch", "new_capacity", "unmet_demand", "annual_emissions",
            "sol", "intermediate_variables", "model_timings", "dimension_lookups",
            "coverage_ratio", "total_demand", "total_dispatch", "total_unmet",
        ):
            assert key in result

    def test_coverage_ratio(self, mini_instance, mini_lookups, solver_result) -> None:
        result = process_results(
            mini_instance,
            solver_result,
            regions=["R1"],
            technologies=["T1", "T2"],
            years=[2020, 2021, 2022],
            emissions=["CO2"],
            has_storage=False,
            region_id_by_name=mini_lookups["region_id_by_name"],
            technology_id_by_name=mini_lookups["technology_id_by_name"],
            region_name_by_id=mini_lookups["region_name_by_id"],
            parallel=False,
        )
        assert 0.0 <= result["coverage_ratio"] <= 1.0
        assert result["total_demand"] == pytest.approx(100.0)

    def test_parallel_matches_sequential_process_results(
        self, mini_instance, mini_lookups, solver_result,
    ) -> None:
        common = dict(
            instance=mini_instance,
            solver_result=solver_result,
            regions=["R1"],
            technologies=["T1", "T2"],
            years=[2020, 2021, 2022],
            emissions=["CO2"],
            has_storage=False,
            region_id_by_name=mini_lookups["region_id_by_name"],
            technology_id_by_name=mini_lookups["technology_id_by_name"],
            region_name_by_id=mini_lookups["region_name_by_id"],
            timeslice_id_by_name=mini_lookups["timeslice_id_by_name"],
        )
        seq = process_results(**common, parallel=False)
        par = process_results(**common, parallel=True)

        assert seq["dispatch"] == pytest.approx(par["dispatch"], rel=0, abs=1e-9)
        assert seq["new_capacity"] == pytest.approx(par["new_capacity"], rel=0, abs=1e-9)
        assert seq["unmet_demand"] == pytest.approx(par["unmet_demand"], rel=0, abs=1e-9)
        assert seq["annual_emissions"] == pytest.approx(par["annual_emissions"], rel=0, abs=1e-9)
        assert seq["coverage_ratio"] == pytest.approx(par["coverage_ratio"])
        assert set(seq["intermediate_variables"].keys()) == set(par["intermediate_variables"].keys())

    def test_extract_pyomo_variable(self, mini_instance) -> None:
        entries = _extract_pyomo_variable(mini_instance, "OperatingCost")
        assert entries
        assert entries[0]["index"] == ["R1", "T1", 2020]
        assert entries[0]["value"] == pytest.approx(100.0)


class TestStreamingIntermediate:
    def test_iter_includes_rate_prod_use_aliases(self, mini_instance) -> None:
        kwargs = dict(
            instance=mini_instance,
            regions=["R1"],
            technologies=["T1", "T2"],
            years=[2020, 2021, 2022],
            emissions=["CO2"],
            has_storage=False,
            parallel=False,
        )
        streamed = list(_iter_intermediate_entries(*_collect_intermediate_parts(**kwargs)))
        var_names = {name for name, _ in streamed}
        assert "RateOfProductionByTechnology" in var_names
        assert "RateOfUseByTechnology" in var_names
        assert "ProductionByTechnology" in var_names
        assert "UseByTechnology" in var_names
        prod = [e for n, e in streamed if n == "ProductionByTechnology"]
        rate_prod = [e for n, e in streamed if n == "RateOfProductionByTechnology"]
        assert prod == rate_prod

    def test_roa_reused_when_aggregates_provided(self, mini_instance) -> None:
        aggregates = _precompute_roa_aggregates(mini_instance)
        kwargs = dict(
            instance=mini_instance,
            regions=["R1"],
            technologies=["T1", "T2"],
            years=[2020, 2021, 2022],
            emissions=["CO2"],
            has_storage=False,
            parallel=False,
            aggregates=aggregates,
        )
        pyomo_out, *_ = _collect_intermediate_parts(**kwargs)
        assert "RateOfActivity" in pyomo_out
        direct = _extract_pyomo_variable(mini_instance, "RateOfActivity")
        assert sorted((tuple(e["index"]), e["value"]) for e in pyomo_out["RateOfActivity"]) == sorted(
            (tuple(e["index"]), e["value"]) for e in direct
        )

    def test_vars_to_load_from_solution(self, mini_instance) -> None:
        names = vars_to_load_from_solution(
            mini_instance,
            emissions=["CO2"],
            has_storage=False,
        )
        assert "NewCapacity" in names
        assert "AnnualEmissions" in names
        assert "RateOfActivity" in names
        assert "OperatingCost" in names
        assert "OBJ" in names

    def test_iter_matches_materialized_dict(self, mini_instance) -> None:
        kwargs = dict(
            instance=mini_instance,
            regions=["R1"],
            technologies=["T1", "T2"],
            years=[2020, 2021, 2022],
            emissions=["CO2"],
            has_storage=False,
            parallel=False,
        )
        parts = _collect_intermediate_parts(**kwargs)
        materialized = _materialize_intermediate_dict(*parts)
        streamed = list(_iter_intermediate_entries(*parts))

        flat = []
        for var_name, entries in materialized.items():
            for entry in entries:
                flat.append((var_name, tuple(entry["index"]), entry["value"]))

        stream_flat = [
            (var_name, tuple(entry["index"]), entry["value"])
            for var_name, entry in streamed
        ]
        assert sorted(flat) == pytest.approx(sorted(stream_flat), rel=0, abs=1e-9)

    def test_materialize_intermediate_false_exposes_iter(
        self, mini_instance, mini_lookups, solver_result,
    ) -> None:
        result = process_results(
            mini_instance,
            solver_result,
            regions=["R1"],
            technologies=["T1", "T2"],
            years=[2020, 2021, 2022],
            emissions=["CO2"],
            has_storage=False,
            region_id_by_name=mini_lookups["region_id_by_name"],
            technology_id_by_name=mini_lookups["technology_id_by_name"],
            region_name_by_id=mini_lookups["region_name_by_id"],
            parallel=False,
            materialize_intermediate=False,
        )
        assert result["intermediate_variables"] == {}
        assert "_intermediate_entry_iter" in result
        entries = list(result["_intermediate_entry_iter"])
        assert entries
        assert entries[0][0]  # var_name non-empty
