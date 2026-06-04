from __future__ import annotations

from types import SimpleNamespace

import app.simulation.core.solver as solver_module
from app.simulation.core.solver_config import (
    SolverHighsConfig,
    apply_highs_options_to_model,
    resolve_highs_config,
)


class _FakeResults:
    def __init__(self, status: str) -> None:
        self.solver = SimpleNamespace(termination_condition=status)


class _FakeSolver:
    def __init__(self, status: str) -> None:
        self._status = status
        self.last_kwargs: dict[str, object] | None = None
        self.highs_options: dict[str, object] = {}
        self.config = SimpleNamespace(stream_solver=True, load_solution=True, report_timing=False)

    def solve(self, instance, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResults(self._status)


class _FakeInstance:
    def __init__(self) -> None:
        self.OBJ = 1.0
        self.solutions = SimpleNamespace(load_from=lambda _results: None)


def _fake_settings(**overrides: object) -> SimpleNamespace:
    base = dict(
        sim_solver_tee=False,
        sim_solver_keepfiles=False,
        sim_solver_threads=8,
        sim_solver_highs_method="ipm",
        sim_solver_highs_presolve="on",
        sim_solver_highs_parallel="on",
        sim_solver_highs_hipo_parallel_type="",
        sim_solver_highs_crossover="choose",
        sim_solver_highs_direct=False,
        sim_solver_highs_time_limit=0.0,
        sim_solver_highs_ipm_tol=1e-7,
        sim_solver_highs_primal_tol=1e-7,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_normalize_solver_status_display_maps_infeasible_to_spanish() -> None:
    assert solver_module.normalize_solver_status_display("infeasible") == "infactible"
    assert solver_module.normalize_solver_status_display("optimal") == "optimal"


def test_resolve_highs_config_from_env() -> None:
    cfg = resolve_highs_config(
        _fake_settings(
            sim_solver_highs_method="hipo",
            sim_solver_highs_hipo_parallel_type="both",
        )
    )
    assert cfg.method == "hipo"
    assert cfg.presolve == "on"
    assert cfg.parallel == "on"
    assert cfg.hipo_parallel_type == "both"
    assert cfg.threads == 8


def test_apply_highs_options_to_dict() -> None:
    opts: dict[str, object] = {}
    cfg = SolverHighsConfig(threads=4, method="ipm", presolve="on", parallel="on")
    threads = apply_highs_options_to_model(opts, cfg)
    assert threads == 4
    assert opts["solver"] == "ipm"
    assert opts["presolve"] == "on"
    assert opts["parallel"] == "on"
    assert opts["log_to_console"] is False


def test_apply_highs_options_to_dict_includes_hipo_parallel_type() -> None:
    opts: dict[str, object] = {}
    cfg = SolverHighsConfig(
        threads=4,
        method="hipo",
        presolve="on",
        parallel="on",
        hipo_parallel_type="both",
    )
    apply_highs_options_to_model(opts, cfg)

    assert opts["solver"] == "hipo"
    assert opts["hipo_parallel_type"] == "both"


def test_apply_highs_options_raises_when_hipo_is_rejected() -> None:
    class _RejectingHighs:
        def setOptionValue(self, key, value):  # noqa: ANN001, N802
            if key == "solver" and value == "hipo":
                return "HighsStatus.kError"
            return "HighsStatus.kOk"

    cfg = SolverHighsConfig(method="hipo")

    try:
        apply_highs_options_to_model(_RejectingHighs(), cfg)
    except ValueError as exc:
        assert "solver=hipo" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError when HiGHS rejects hipo")


def test_pyomo_lp_name_roundtrip() -> None:
    pyomo = "RateOfActivity[COL,1,AN_PWRSOL,1,2030]"
    lp = solver_module._pyomo_name_to_lp(pyomo)
    assert lp == "RateOfActivity(COL,1,AN_PWRSOL,1,2030)"
    assert solver_module._lp_name_to_pyomo(lp) == pyomo


def test_solve_model_uses_settings_for_tee_and_keepfiles(monkeypatch) -> None:
    fake_solver = _FakeSolver(status="optimal")
    monkeypatch.setattr(solver_module, "get_settings", lambda: _fake_settings(sim_solver_threads=0))
    monkeypatch.setattr(
        solver_module,
        "get_solver_availability",
        lambda: {"glpk": True, "highs": False},
    )
    monkeypatch.setattr(
        solver_module.pyo,
        "SolverFactory",
        lambda _factory_name: fake_solver,
    )
    monkeypatch.setattr(solver_module.pyo, "value", lambda _obj: 0.0)

    result = solver_module.solve_model(_FakeInstance(), solver_name="glpk")

    assert result["solver_status"] == "optimal"
    assert fake_solver.last_kwargs is not None
    assert fake_solver.last_kwargs["tee"] is False
    assert fake_solver.last_kwargs["keepfiles"] is False
    assert fake_solver.last_kwargs["load_solutions"] is False
    assert "solver_timings" in result


def test_solve_model_sets_highs_threads_and_options_when_appsi(monkeypatch) -> None:
    fake_solver = _FakeSolver(status="optimal")
    monkeypatch.setattr(
        solver_module,
        "get_settings",
        lambda: _fake_settings(sim_solver_highs_direct=False),
    )
    monkeypatch.setattr(
        solver_module,
        "resolve_highs_config",
        lambda _settings: SolverHighsConfig(
            threads=8,
            method="ipm",
            presolve="on",
            parallel="on",
            use_direct=False,
        ),
    )
    monkeypatch.setattr(
        solver_module,
        "get_solver_availability",
        lambda: {"glpk": False, "highs": True},
    )
    monkeypatch.setattr(
        solver_module.pyo,
        "SolverFactory",
        lambda _factory_name: fake_solver,
    )
    monkeypatch.setattr(solver_module.pyo, "value", lambda _obj: 0.0)

    result = solver_module.solve_model(_FakeInstance(), solver_name="highs")

    assert result["solver_status"] == "optimal"
    assert fake_solver.highs_options["threads"] == 8
    assert fake_solver.highs_options["solver"] == "ipm"
    assert fake_solver.config.stream_solver is False


def test_solve_model_routes_to_direct_highspy(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    def _fake_direct(instance, *, highs_config, lp_path, timings):
        calls["direct"] = True
        timings["solver_backend"] = "direct_highspy"
        return "optimal", 123.0, 16

    monkeypatch.setattr(solver_module, "_solve_with_direct_highspy", _fake_direct)
    monkeypatch.setattr(
        solver_module,
        "get_settings",
        lambda: _fake_settings(sim_solver_highs_direct=True),
    )
    monkeypatch.setattr(
        solver_module,
        "resolve_highs_config",
        lambda _settings: SolverHighsConfig(threads=16, use_direct=True),
    )
    monkeypatch.setattr(
        solver_module,
        "get_solver_availability",
        lambda: {"glpk": False, "highs": True},
    )

    result = solver_module.solve_model(_FakeInstance(), solver_name="highs")

    assert calls.get("direct") is True
    assert result["objective_value"] == 123.0
    assert result["solver_timings"]["solver_backend"] == "direct_highspy"


def test_solve_model_does_not_set_glpk_threads(monkeypatch) -> None:
    fake_solver = _FakeSolver(status="optimal")
    monkeypatch.setattr(
        solver_module,
        "get_settings",
        lambda: _fake_settings(sim_solver_threads=8),
    )
    monkeypatch.setattr(
        solver_module,
        "get_solver_availability",
        lambda: {"glpk": True, "highs": False},
    )
    monkeypatch.setattr(
        solver_module.pyo,
        "SolverFactory",
        lambda _factory_name: fake_solver,
    )
    monkeypatch.setattr(solver_module.pyo, "value", lambda _obj: 0.0)

    result = solver_module.solve_model(_FakeInstance(), solver_name="glpk")

    assert result["solver_status"] == "optimal"
    assert not hasattr(fake_solver, "highs_options") or fake_solver.highs_options == {}


class _FakeConstraint:
    def __init__(self, idx: int) -> None:
        self.name = f"C{idx}"
        self.body = 0.0
        self.lower = 10.0
        self.upper = None

    def has_lb(self) -> bool:
        return True

    def has_ub(self) -> bool:
        return False


class _FakeDiagInstance:
    def __init__(self, constraints: list[_FakeConstraint]) -> None:
        self._constraints = constraints

    def component_data_objects(self, cls, active=True):  # noqa: ARG002
        if cls is solver_module.Constraint:
            return self._constraints
        if cls is solver_module.Var:
            return []
        return []


def test_infeasibility_diagnostics_does_not_truncate_payload(monkeypatch) -> None:
    constraints = [_FakeConstraint(i) for i in range(25)]
    monkeypatch.setattr(solver_module, "value", lambda obj, exception=False: obj)  # noqa: ARG005

    diagnostics = solver_module._run_infeasibility_diagnostics(_FakeDiagInstance(constraints))

    assert len(diagnostics["constraint_violations"]) == 25
    assert diagnostics["var_bound_conflicts"] == []
