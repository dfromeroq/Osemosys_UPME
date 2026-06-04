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
    assert solver_module.normalize_solver_status_display("unknown") == "desconocido"


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


class _FakeHighs:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def setOptionValue(self, key: str, value: object) -> None:
        self.options[key] = value


def test_apply_highspy_options_sets_threads(monkeypatch) -> None:
    h = _FakeHighs()
    settings = SimpleNamespace(sim_solver_threads=8)
    monkeypatch.setattr(solver_module, "_resolve_solver_threads", lambda _s: 8)
    monkeypatch.setattr(solver_module, "_hardware_thread_limit", lambda: 16)

    configured, applied = solver_module._apply_highspy_options(h, settings=settings)

    assert configured == 8
    assert applied == 8
    assert h.options["threads"] == 8
    assert h.options["solver"] == "ipm"
    assert h.options["presolve"] == "on"
    assert h.options["parallel"] == "on"
    assert h.options["run_crossover"] == "choose"
    assert h.options["ipm_optimality_tolerance"] == solver_module.HIGHS_IPM_OPTIMALITY_TOLERANCE


def test_effective_solver_threads_caps_at_hardware(monkeypatch) -> None:
    monkeypatch.setattr(solver_module, "_hardware_thread_limit", lambda: 16)
    assert solver_module._effective_solver_threads(18) == 16
    assert solver_module._effective_solver_threads(0) == 16
    assert solver_module._effective_solver_threads(8) == 8


def test_read_highspy_threads_used_reads_option_or_hardware(monkeypatch) -> None:
    class _H:
        def __init__(self, opt: object) -> None:
            self._opt = opt

        def getOptionValue(self, _key: str) -> object:
            return (0, self._opt)

    monkeypatch.setattr(solver_module, "_hardware_thread_limit", lambda: 16)
    assert solver_module._read_highspy_threads_used(_H(12)) == 12
    assert solver_module._read_highspy_threads_used(_H(0)) == 16


def test_planned_solver_threads_highs_uses_cpu_count_when_zero(monkeypatch) -> None:
    monkeypatch.setattr(solver_module, "_resolve_solver_threads", lambda _s: 0)
    monkeypatch.setattr(solver_module, "_hardware_thread_limit", lambda: 12)

    assert solver_module.planned_solver_threads("highs", settings=object()) == 12


def test_planned_solver_threads_glpk_returns_none() -> None:
    assert solver_module.planned_solver_threads("glpk", settings=object()) is None


def test_apply_highspy_options_uses_cpu_count_when_threads_zero(monkeypatch) -> None:
    h = _FakeHighs()
    settings = SimpleNamespace(sim_solver_threads=0)
    monkeypatch.setattr(solver_module, "_resolve_solver_threads", lambda _s: 0)
    monkeypatch.setattr(solver_module, "_hardware_thread_limit", lambda: 16)

    configured, applied = solver_module._apply_highspy_options(h, settings=settings)

    assert configured == 0
    assert applied == 16
    assert h.options["threads"] == 16


def test_solve_model_highs_routes_to_highspy_lp(monkeypatch) -> None:
    highspy_calls: list[str] = []

    def _fake_highspy_lp(instance, lp_path, *, settings):  # noqa: ARG001
        highspy_calls.append(str(lp_path))
        return {
            "solver_name": "highs",
            "solver_status": "optimal",
            "objective_value": 99.0,
            "solver_threads_used": 4,
            "reserve_margin_dual": None,
            "infeasibility_diagnostics": None,
            "solver_backend": "highspy_lp",
            "read_model_seconds": 0.1,
            "highs_run_seconds": 0.2,
            "map_solution_seconds": 0.3,
        }

    def _fail_solver_factory(_name: str):
        raise AssertionError("SolverFactory no debe usarse cuando solver_name=highs")

    monkeypatch.setattr(solver_module, "_highs_available", lambda: True)
    monkeypatch.setattr(
        solver_module,
        "get_settings",
        lambda: SimpleNamespace(
            sim_solver_tee=False,
            sim_solver_keepfiles=False,
            sim_solver_threads=4,
        ),
    )
    monkeypatch.setattr(solver_module, "write_lp_file", lambda _inst, path: path)
    monkeypatch.setattr(solver_module, "_solve_with_highspy_lp", _fake_highspy_lp)
    monkeypatch.setattr(solver_module.pyo, "SolverFactory", _fail_solver_factory)

    result = solver_module.solve_model(_FakeInstance(), solver_name="highs")

    assert len(highspy_calls) == 1
    assert result["solver_status"] == "optimal"
    assert result["objective_value"] == 99.0
    assert result["solver_backend"] == "highspy_lp"
    assert "write_lp_seconds" in result


def test_solve_with_highspy_lp_resets_scheduler(monkeypatch, tmp_path) -> None:
    lp_path = tmp_path / "model.lp"
    lp_path.write_text("stub lp", encoding="utf-8")
    reset_calls: list[int] = []

    class _FakeHighsEngine:
        def setOptionValue(self, *_args, **_kwargs) -> None:
            pass

        def readModel(self, _path: str) -> None:
            pass

        def getModelStatus(self) -> str:
            return "kOptimal"

        def getOptionValue(self, _key: str) -> tuple[int, int]:
            return (0, 4)

        def getInfo(self) -> object:
            return SimpleNamespace(objective_function_value=1.0)

        def getSolution(self) -> object:
            return SimpleNamespace(col_value=[], row_dual=[])

        def getLp(self) -> object:
            return SimpleNamespace(col_names_=[], row_names_=[])

    fake_highspy_mod = SimpleNamespace(
        Highs=_FakeHighsEngine,
        HighsModelStatus=SimpleNamespace(kOptimal=1, kNotset=0),
    )
    monkeypatch.setitem(__import__("sys").modules, "highspy", fake_highspy_mod)
    monkeypatch.setattr(
        solver_module,
        "_reset_highspy_scheduler",
        lambda: reset_calls.append(1),
    )
    monkeypatch.setattr(solver_module, "_run_highspy", lambda _h, **_k: 0.1)
    monkeypatch.setattr(solver_module, "_highs_status_to_raw", lambda _s: "optimal")
    monkeypatch.setattr(solver_module, "_apply_highspy_solution", lambda *_a, **_k: 1.0)
    monkeypatch.setattr(solver_module, "_apply_highspy_duals", lambda *_a, **_k: None)
    monkeypatch.setattr(solver_module, "_extract_reserve_margin_dual", lambda _i: None)
    monkeypatch.setattr(solver_module, "_resolve_solver_threads", lambda _s: 18)
    monkeypatch.setattr(solver_module, "_hardware_thread_limit", lambda: 16)

    result = solver_module._solve_with_highspy_lp(
        _FakeInstance(),
        lp_path,
        settings=SimpleNamespace(sim_solver_threads=18, sim_solver_keepfiles=False),
    )

    assert reset_calls == [1]
    assert result["solver_threads_configured"] == 18
    assert result["solver_threads_used"] == 4


def test_solve_with_highspy_lp_infeasible_runs_appsi_diagnostics(monkeypatch, tmp_path) -> None:
    lp_path = tmp_path / "model.lp"
    lp_path.write_text("stub lp", encoding="utf-8")

    class _FakeHighsEngine:
        def setOptionValue(self, *_args, **_kwargs) -> None:
            pass

        def readModel(self, _path: str) -> None:
            pass

        def run(self) -> None:
            pass

        def getModelStatus(self) -> str:
            return "kInfeasible"

        def getOptionValue(self, _key: str) -> tuple[int, int]:
            return (0, 4)

    appsi_calls: list[int] = []
    diag_calls: list[int] = []

    fake_highspy_mod = SimpleNamespace(Highs=_FakeHighsEngine)
    monkeypatch.setitem(
        __import__("sys").modules,
        "highspy",
        fake_highspy_mod,
    )
    monkeypatch.setattr(solver_module, "_highs_status_to_raw", lambda _s: "infeasible")
    monkeypatch.setattr(
        solver_module,
        "_appsi_highs_solve_for_diagnostics",
        lambda *_a, **_k: appsi_calls.append(1),
    )
    monkeypatch.setattr(
        solver_module,
        "_run_infeasibility_diagnostics",
        lambda _inst: (
            diag_calls.append(1)
            or {"constraint_violations": [], "var_bound_conflicts": []}
        ),
    )
    monkeypatch.setattr(solver_module, "_resolve_solver_threads", lambda _s: 0)

    result = solver_module._solve_with_highspy_lp(
        _FakeInstance(),
        lp_path,
        settings=SimpleNamespace(sim_solver_threads=0, sim_solver_keepfiles=False),
    )

    assert result["solver_status"] == "infactible"
    assert appsi_calls == [1]
    assert diag_calls == [1]
    assert result["infeasibility_diagnostics"] is not None


def test_solve_with_highspy_lp_unknown_feasible_strict_does_not_map(
    monkeypatch, tmp_path,
) -> None:
    lp_path = tmp_path / "model.lp"
    lp_path.write_text("stub lp", encoding="utf-8")

    class _FakeInfo:
        primal_solution_status = 2

    class _FakeHighsEngine:
        def setOptionValue(self, *_args, **_kwargs) -> None:
            pass

        def readModel(self, _path: str) -> None:
            pass

        def run(self) -> None:
            pass

        def getModelStatus(self) -> str:
            return "kUnknown"

        def getInfo(self) -> _FakeInfo:
            return _FakeInfo()

        def getOptionValue(self, _key: str) -> tuple[int, int]:
            return (0, 4)

    fake_highspy_mod = SimpleNamespace(
        Highs=_FakeHighsEngine,
        kSolutionStatusFeasible=2,
    )
    monkeypatch.setitem(__import__("sys").modules, "highspy", fake_highspy_mod)
    monkeypatch.setattr(solver_module, "_highs_status_to_raw", lambda _s: "unknown")
    monkeypatch.setattr(solver_module, "_resolve_solver_threads", lambda _s: 4)

    result = solver_module._solve_with_highspy_lp(
        _FakeInstance(),
        lp_path,
        settings=SimpleNamespace(sim_solver_threads=4, sim_solver_keepfiles=False),
    )

    assert result["objective_value"] == 0.0
    assert result["solver_status"] == "desconocido"


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
