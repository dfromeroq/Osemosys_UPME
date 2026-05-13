from __future__ import annotations

from types import SimpleNamespace

import app.simulation.core.solver as solver_module


class _FakeResults:
    def __init__(self, status: str) -> None:
        self.solver = SimpleNamespace(termination_condition=status)


class _FakeSolver:
    def __init__(self, status: str) -> None:
        self._status = status
        self.last_kwargs: dict[str, object] | None = None

    def solve(self, instance, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResults(self._status)


class _FakeInstance:
    def __init__(self) -> None:
        self.OBJ = 1.0
        self.solutions = SimpleNamespace(load_from=lambda _results: None)


def test_normalize_solver_status_display_maps_infeasible_to_spanish() -> None:
    assert solver_module.normalize_solver_status_display("infeasible") == "infactible"
    assert solver_module.normalize_solver_status_display("optimal") == "optimal"


def test_solve_model_uses_settings_for_tee_and_keepfiles(monkeypatch) -> None:
    fake_solver = _FakeSolver(status="optimal")
    monkeypatch.setattr(
        solver_module,
        "get_settings",
        lambda: SimpleNamespace(
            sim_solver_tee=False,
            sim_solver_keepfiles=False,
            sim_solver_threads=0,
        ),
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
    assert fake_solver.last_kwargs is not None
    assert fake_solver.last_kwargs["tee"] is False
    assert fake_solver.last_kwargs["keepfiles"] is False
    assert fake_solver.last_kwargs["load_solutions"] is False


def test_solve_model_sets_highs_threads_when_configured(monkeypatch) -> None:
    """La ruta HiGHS LP-directa recibe el nro de threads desde _resolve_solver_threads."""
    captured: dict = {}

    def _fake_solve_highs_via_lp(instance, *, threads, tee):  # noqa: ARG001
        captured["threads"] = threads
        return ("optimal", 1.0, threads or None)

    monkeypatch.setattr(
        solver_module,
        "get_settings",
        lambda: SimpleNamespace(
            sim_solver_tee=False,
            sim_solver_keepfiles=False,
            sim_solver_threads=8,
        ),
    )
    monkeypatch.setattr(
        solver_module,
        "get_solver_availability",
        lambda: {"glpk": False, "highs": True},
    )
    monkeypatch.setattr(solver_module, "_resolve_solver_threads", lambda _settings: 8)
    monkeypatch.setattr(solver_module, "_solve_highs_via_lp", _fake_solve_highs_via_lp)

    result = solver_module.solve_model(_FakeInstance(), solver_name="highs")

    assert result["solver_status"] == "optimal"
    assert captured["threads"] == 8
    assert result["solver_threads_used"] == 8


def test_solve_model_does_not_set_glpk_threads(monkeypatch) -> None:
    fake_solver = _FakeSolver(status="optimal")
    monkeypatch.setattr(
        solver_module,
        "get_settings",
        lambda: SimpleNamespace(
            sim_solver_tee=False,
            sim_solver_keepfiles=False,
            sim_solver_threads=8,
        ),
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
    assert not hasattr(fake_solver, "highs_options")


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
