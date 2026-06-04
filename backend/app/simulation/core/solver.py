"""Resolución del modelo OSeMOSYS.

Replica las celdas 27-28 del notebook OPT_YA_20260220:
  - Generación de archivo LP con symbolic_solver_labels (opcional)
  - SolverFactory("glpk").solve(instance) o appsi_highs / highspy directo
  - Diagnósticos de infactibilidad (constraint violations, variable bounds)

Uso: recibe la instancia concreta de instance_builder.build_instance();
     devuelve dict con solver_name, solver_status, objective_value.
"""

from __future__ import annotations

import logging
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

import pyomo.environ as pyo
from pyomo.core import Constraint, Suffix, Var, value

from app.core.config import get_settings
from app.simulation.core.solver_config import (
    SolverHighsConfig,
    apply_highs_options_to_model,
    resolve_highs_config,
)

logger = logging.getLogger(__name__)

# Alias usado en solve_model -> nombre del factory Pyomo (appsi_highs, glpk, gurobi).
SOLVER_FACTORIES: dict[str, str] = {
    "highs": "appsi_highs",
    "glpk": "glpk",
    "gurobi": "gurobi",
}


def normalize_solver_status_display(status: str) -> str:
    """Convierte términos en inglés del solver a etiquetas en español para la API/UI."""
    s = str(status)
    if "infeasible" not in s.lower():
        return s
    return re.sub("infeasible", "infactible", s, flags=re.IGNORECASE)


def _gurobi_lightweight_available() -> bool:
    try:
        import gurobipy  # noqa: F401
    except Exception:
        return False
    return True


def get_solver_availability() -> dict[str, bool]:
    availability: dict[str, bool] = {}
    for solver_alias, solver_factory in SOLVER_FACTORIES.items():
        if solver_alias == "gurobi":
            availability[solver_alias] = _gurobi_lightweight_available()
            continue
        solver = pyo.SolverFactory(solver_factory)
        availability[solver_alias] = bool(
            solver is not None and solver.available(exception_flag=False)
        )
    return availability


def write_lp_file(
    instance: pyo.ConcreteModel,
    lp_path: str | Path,
    *,
    symbolic_solver_labels: bool = True,
) -> Path:
    """Genera archivo LP (CPLEX) desde la instancia Pyomo."""
    lp_path = Path(lp_path)
    lp_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Generando archivo LP: %s", lp_path)
    instance.write(
        filename=str(lp_path),
        io_options={"symbolic_solver_labels": symbolic_solver_labels},
    )
    file_size_mb = lp_path.stat().st_size / (1024 * 1024)
    logger.info("Archivo LP generado (%.2f MB): %s", file_size_mb, lp_path)
    return lp_path


def _release_solver(solver: object) -> None:
    import gc

    closed = False
    for attr in ("close", "release", "_release_solver"):
        fn = getattr(solver, attr, None)
        if callable(fn):
            try:
                fn()
                closed = True
                break
            except Exception:  # pragma: no cover
                logger.debug("Error cerrando solver vía %s", attr, exc_info=True)
    if not closed:
        solver_model = getattr(solver, "_solver_model", None)
        if solver_model is not None:
            for closer in ("dispose", "close"):
                fn = getattr(solver_model, closer, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:  # pragma: no cover
                        logger.debug(
                            "Error cerrando solver_model vía %s",
                            closer,
                            exc_info=True,
                        )
                    break
        env = getattr(solver, "_solver_env", None)
        if env is not None:
            for closer in ("dispose", "close"):
                fn = getattr(env, closer, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:  # pragma: no cover
                        logger.debug(
                            "Error cerrando solver_env vía %s",
                            closer,
                            exc_info=True,
                        )
                    break

    gc.collect()
    try:
        import gurobipy as gp

        dispose_default = getattr(gp, "disposeDefaultEnv", None)
        if callable(dispose_default):
            dispose_default()
    except Exception:  # pragma: no cover
        pass


def _resolve_solver_threads(settings: object) -> int:
    """Compat: delega en ``resolve_highs_config``."""
    return resolve_highs_config(settings).threads


def _apply_solver_runtime_options(
    solver: object, *, candidate: str, settings: object, highs_config: SolverHighsConfig | None = None
) -> int | None:
    if highs_config is None:
        highs_config = resolve_highs_config(settings)

    if candidate == "highs":
        highs_options = getattr(solver, "highs_options", None)
        if not isinstance(highs_options, dict):
            logger.warning(
                "HiGHS no expone highs_options; no se puede leer/escribir opciones",
            )
            return None
        threads_used = apply_highs_options_to_model(highs_options, highs_config)
        logger.info(
            "Configurando HiGHS (appsi): method=%s presolve=%s parallel=%s threads=%s",
            highs_config.method,
            highs_config.presolve,
            highs_config.parallel,
            highs_config.threads or "default",
        )
        if hasattr(solver, "config"):
            try:
                solver.config.stream_solver = False
                solver.config.load_solution = False
            except Exception:  # pragma: no cover
                pass
        return threads_used

    if candidate == "gurobi":
        gurobi_options = getattr(solver, "options", None)
        if gurobi_options is None:
            return None
        if highs_config.threads > 0:
            try:
                gurobi_options["Threads"] = highs_config.threads
                logger.info("Configurando Gurobi con Threads=%s", highs_config.threads)
            except Exception:  # pragma: no cover
                logger.warning(
                    "No fue posible aplicar Threads=%s a Gurobi vía solver.options",
                    highs_config.threads,
                )
        try:
            effective = gurobi_options["Threads"]
            return int(effective) if effective is not None else None
        except (KeyError, TypeError, ValueError):
            return None

    return None


def _pyomo_name_to_lp(name: str) -> str:
    """Normaliza nombres Pyomo ``Var[...]`` al formato LP ``Var(...)``."""
    if "[" in name and name.endswith("]"):
        base, rest = name.split("[", 1)
        return f"{base}({rest[:-1]})"
    return name


def _lp_name_to_pyomo(name: str) -> str:
    if "(" in name and name.endswith(")"):
        base, rest = name.split("(", 1)
        return f"{base}[{rest[:-1]}]"
    return name


def _highs_status_to_raw(status: object) -> str:
    try:
        import highspy
    except ImportError:  # pragma: no cover
        return str(status)

    mapping = {
        getattr(highspy.HighsModelStatus, "kOptimal", None): "optimal",
        getattr(highspy.HighsModelStatus, "kInfeasible", None): "infeasible",
        getattr(highspy.HighsModelStatus, "kUnbounded", None): "unbounded",
        getattr(highspy.HighsModelStatus, "kTimeLimit", None): "maxTimeLimit",
        getattr(highspy.HighsModelStatus, "kIterationLimit", None): "maxIterations",
        getattr(highspy.HighsModelStatus, "kObjectiveBound", None): "objectiveLimit",
    }
    for hs, label in mapping.items():
        if hs is not None and status == hs:
            return label
    return str(status)


def _ensure_dual_suffix(instance: pyo.ConcreteModel) -> None:
    if getattr(instance, "dual", None) is None:
        instance.dual = Suffix(direction=Suffix.IMPORT)


def _apply_highspy_solution_to_instance(
    instance: pyo.ConcreteModel,
    h: object,
) -> tuple[float, dict[str, float]]:
    """Carga primals/duals de highspy en la instancia Pyomo."""
    solution = h.getSolution()
    lp = h.getLp()
    col_names = list(getattr(lp, "col_names_", []) or [])
    row_names = list(getattr(lp, "row_names_", []) or [])
    col_values = list(getattr(solution, "col_value", []) or [])
    row_duals = list(getattr(solution, "row_dual", []) or [])

    col_map: dict[str, float] = {}
    for idx, name in enumerate(col_names):
        if idx < len(col_values):
            col_map[name] = float(col_values[idx])
            col_map[_lp_name_to_pyomo(name)] = float(col_values[idx])

    for var in instance.component_data_objects(Var, active=True):
        pyomo_name = var.name
        lp_name = _pyomo_name_to_lp(pyomo_name)
        val = col_map.get(pyomo_name)
        if val is None:
            val = col_map.get(lp_name)
        if val is not None:
            var.set_value(val, skip_validation=True)

    dual_map: dict[str, float] = {}
    for idx, name in enumerate(row_names):
        if idx < len(row_duals):
            dual_map[name] = float(row_duals[idx])
            dual_map[_lp_name_to_pyomo(name)] = float(row_duals[idx])

    if dual_map:
        _ensure_dual_suffix(instance)
        for con in instance.component_data_objects(Constraint, active=True):
            pyomo_name = con.name
            lp_name = _pyomo_name_to_lp(pyomo_name)
            dual_val = dual_map.get(pyomo_name)
            if dual_val is None:
                dual_val = dual_map.get(lp_name)
            if dual_val is not None:
                instance.dual[con] = dual_val

    try:
        info = h.getInfo()
        obj = float(getattr(info, "objective_function_value", 0.0))
    except Exception:
        try:
            obj = float(pyo.value(instance.OBJ))
        except Exception:
            obj = 0.0
    return obj, dual_map


def _solve_with_direct_highspy(
    instance: pyo.ConcreteModel,
    *,
    highs_config: SolverHighsConfig,
    lp_path: Path | None,
    timings: dict[str, float],
) -> tuple[str, float, int | None]:
    import highspy

    t0 = perf_counter()
    if lp_path is None:
        with tempfile.NamedTemporaryFile(suffix=".lp", delete=False) as tmp:
            lp_path = Path(tmp.name)
        write_lp_file(instance, lp_path, symbolic_solver_labels=True)
        timings["solver_write_lp_seconds"] = perf_counter() - t0
        cleanup_lp = True
    else:
        if not lp_path.exists():
            write_lp_file(instance, lp_path, symbolic_solver_labels=True)
        timings["solver_write_lp_seconds"] = perf_counter() - t0
        cleanup_lp = False

    h = highspy.Highs()
    threads_used = apply_highs_options_to_model(h, highs_config)
    logger.info(
        "HiGHS directo: method=%s presolve=%s parallel=%s threads=%s crossover=%s",
        highs_config.method,
        highs_config.presolve,
        highs_config.parallel,
        highs_config.threads or "default",
        highs_config.run_crossover,
    )

    t_read = perf_counter()
    h.readModel(str(lp_path))
    timings["solver_read_model_seconds"] = perf_counter() - t_read

    t_run = perf_counter()
    h.run()
    timings["solver_run_seconds"] = perf_counter() - t_run

    raw_status = _highs_status_to_raw(h.getModelStatus())

    t_map = perf_counter()
    obj = 0.0
    if "optimal" in raw_status.lower() or raw_status.lower() in {
        "maxtimelimit",
        "maxiterations",
        "objectivelimit",
    }:
        obj, _ = _apply_highspy_solution_to_instance(instance, h)
    timings["solver_map_solution_seconds"] = perf_counter() - t_map
    timings["solver_backend"] = "direct_highspy"

    if cleanup_lp:
        try:
            lp_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception:  # pragma: no cover
            pass

    return raw_status, obj, threads_used


def _solve_with_appsi_highs(
    instance: pyo.ConcreteModel,
    *,
    highs_config: SolverHighsConfig,
    settings: object,
    timings: dict[str, float],
) -> tuple[object, object, str, float, int | None]:
    solver = pyo.SolverFactory("appsi_highs")
    threads_used = _apply_solver_runtime_options(
        solver, candidate="highs", settings=settings, highs_config=highs_config
    )
    if hasattr(solver, "config"):
        try:
            solver.config.report_timing = True
        except Exception:  # pragma: no cover
            pass

    t0 = perf_counter()
    results = solver.solve(
        instance,
        tee=False,
        keepfiles=getattr(settings, "sim_solver_keepfiles", False),
        load_solutions=False,
    )
    timings["solver_run_seconds"] = perf_counter() - t0
    timings["solver_backend"] = "appsi_highs"

    raw_status = str(results.solver.termination_condition)
    obj = 0.0
    if "optimal" in raw_status.lower():
        t_load = perf_counter()
        instance.solutions.load_from(results)
        timings["solver_load_solution_seconds"] = perf_counter() - t_load
        try:
            obj = float(pyo.value(instance.OBJ))
        except Exception:
            pass

    return solver, results, raw_status, obj, threads_used


def _validate_hipo_runtime_support(highs_config: SolverHighsConfig) -> None:
    """Falla temprano si el runtime highspy no fue compilado con soporte HiPO."""
    if highs_config.method != "hipo":
        return

    try:
        import highspy
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "SIM_SOLVER_HIGHS_METHOD=hipo requiere highspy instalado."
        ) from exc

    try:
        h = highspy.Highs()
        apply_highs_options_to_model(h, highs_config)
    except Exception as exc:
        raise RuntimeError(
            "SIM_SOLVER_HIGHS_METHOD=hipo está configurado, pero esta imagen "
            "no tiene HiGHS compilado con soporte HiPO. Reconstruye con "
            "HIGHS_BUILD_FROM_SOURCE=1 y HIGHS_ENABLE_HIPO=1."
        ) from exc


def _run_infeasibility_diagnostics(instance: pyo.ConcreteModel) -> dict:
    tol = 1e-6

    logger.warning("=" * 70)
    logger.warning("MODELO INFACTIBLE - ANÁLISIS DIAGNÓSTICO")
    logger.warning("=" * 70)

    constraint_violations_raw: list[tuple[str, float, float | None, float | None, str, float]] = []
    for con in instance.component_data_objects(Constraint, active=True):
        body_val = value(con.body, exception=False)
        if body_val is None:
            continue

        lb = value(con.lower, exception=False) if con.has_lb() else None
        ub = value(con.upper, exception=False) if con.has_ub() else None

        violation = 0.0
        bound_side = ""
        if lb is not None and body_val < lb - tol:
            violation = lb - body_val
            bound_side = "LB"
        elif ub is not None and body_val > ub + tol:
            violation = body_val - ub
            bound_side = "UB"

        if violation > tol:
            constraint_violations_raw.append(
                (con.name, body_val, lb, ub, bound_side, violation)
            )

    constraint_violations_raw.sort(key=lambda x: -x[5])

    if constraint_violations_raw:
        logger.warning(
            "Encontradas %d restricciones violadas", len(constraint_violations_raw),
        )
        for idx, (name, body_val, lb, ub, side, vio) in enumerate(
            constraint_violations_raw[:10]
        ):
            lb_txt = f"{lb:.2e}" if lb is not None else "-inf"
            ub_txt = f"{ub:.2e}" if ub is not None else "+inf"
            logger.warning(
                "  %d. %s: Body=%.6e, Bounds=[%s, %s], Violated=%s, Violation=%.2e",
                idx + 1, name, body_val, lb_txt, ub_txt, side, vio,
            )
    else:
        logger.warning(
            "No se detectaron violaciones explícitas de restricciones; "
            "la infactibilidad puede deberse a bounds conflictivos de variables"
        )

    var_bound_conflicts_raw: list[tuple[str, float, float, float]] = []
    for var in instance.component_data_objects(Var, active=True):
        lb = value(var.lb, exception=False) if var.has_lb() else None
        ub = value(var.ub, exception=False) if var.has_ub() else None
        if lb is not None and ub is not None and lb > ub + tol:
            var_bound_conflicts_raw.append((var.name, lb, ub, lb - ub))

    var_bound_conflicts_raw.sort(key=lambda x: -x[3])

    if var_bound_conflicts_raw:
        logger.warning(
            "Encontradas %d variables con bounds infactibles (LB > UB):",
            len(var_bound_conflicts_raw),
        )
        for idx, (name, lb, ub, gap) in enumerate(var_bound_conflicts_raw[:10]):
            logger.warning(
                "  %d. %s: LB=%.2e, UB=%.2e, Gap=%.2e",
                idx + 1, name, lb, ub, gap,
            )
    else:
        logger.warning("Todos los bounds de variables son consistentes (LB <= UB)")

    logger.warning("RECOMENDACIONES DE DEBUGGING:")
    logger.warning("  1. Verificar restricciones de demanda vs capacidad disponible")
    logger.warning("  2. Verificar ResidualCapacity y upper bounds no sean restrictivos")
    logger.warning("  3. Inspeccionar InputActivityRatio/OutputActivityRatio")
    logger.warning("  4. Confirmar consistencia de unidades entre fuels, actividades y capacidades")
    logger.warning("  5. Revisar balance energético: todos los fuels deben tener rutas de suministro")
    logger.warning("  6. Verificar datos de matrices (CapacityFactor, ActivityRatios)")
    logger.warning("=" * 70)

    return {
        "constraint_violations": [
            {
                "name": name,
                "body": body_val,
                "lower": lb,
                "upper": ub,
                "side": side,
                "violation": vio,
            }
            for name, body_val, lb, ub, side, vio in constraint_violations_raw
        ],
        "var_bound_conflicts": [
            {"name": name, "lb": lb, "ub": ub, "gap": gap}
            for name, lb, ub, gap in var_bound_conflicts_raw
        ],
    }


def _extract_reserve_margin_dual(instance: pyo.ConcreteModel) -> float | None:
    dual_suffix = getattr(instance, "dual", None)
    if dual_suffix is None:
        return None

    max_abs: float | None = None

    native = getattr(instance, "ReserveMarginConstraint", None)
    if native is not None:
        for con_data in native.values():
            try:
                d = dual_suffix.get(con_data)
            except Exception:
                continue
            if d is None:
                continue
            try:
                abs_d = abs(float(d))
            except (TypeError, ValueError):
                continue
            if max_abs is None or abs_d > max_abs:
                max_abs = abs_d

    udc = getattr(instance, "UDC1_UserDefinedConstraintInequality", None)
    if udc is not None:
        for idx, con_data in udc.items():
            if not (isinstance(idx, tuple) and len(idx) >= 2 and idx[1] == "UDC_Margin"):
                continue
            try:
                d = dual_suffix.get(con_data)
            except Exception:
                continue
            if d is None:
                continue
            try:
                abs_d = abs(float(d))
            except (TypeError, ValueError):
                continue
            if max_abs is None or abs_d > max_abs:
                max_abs = abs_d

    if max_abs is None:
        return None
    logger.info("Dual máximo margen de reserva: %.6f", max_abs)
    return max_abs


def _solve_highs(
    instance: pyo.ConcreteModel,
    *,
    settings: object,
    highs_config: SolverHighsConfig,
    lp_path: Path | None,
    on_solver_finished: Callable[[pyo.ConcreteModel, Any, Any, dict], None] | None,
) -> dict:
    solver_timings: dict[str, float] = {}
    solver_obj: object | None = None
    results_obj: object | None = None
    raw_status: str
    obj: float
    threads_used: int | None

    _validate_hipo_runtime_support(highs_config)

    if highs_config.use_direct:
        try:
            raw_status, obj, threads_used = _solve_with_direct_highspy(
                instance,
                highs_config=highs_config,
                lp_path=Path(lp_path) if lp_path is not None else None,
                timings=solver_timings,
            )
        except Exception:
            logger.exception(
                "HiGHS directo falló; reintentando con appsi_highs",
            )
            solver_obj, results_obj, raw_status, obj, threads_used = _solve_with_appsi_highs(
                instance,
                highs_config=highs_config,
                settings=settings,
                timings=solver_timings,
            )
    else:
        solver_obj, results_obj, raw_status, obj, threads_used = _solve_with_appsi_highs(
            instance,
            highs_config=highs_config,
            settings=settings,
            timings=solver_timings,
        )

    status_display = normalize_solver_status_display(raw_status)
    logger.info(
        "Solver highs terminó: status=%s (raw=%s), objective=%.4f, backend=%s",
        status_display,
        raw_status,
        obj,
        solver_timings.get("solver_backend", "unknown"),
    )

    diagnostics: dict | None = None
    reserve_margin_dual: float | None = None
    if "infeasible" in raw_status.lower():
        diagnostics = _run_infeasibility_diagnostics(instance)
    elif "optimal" in raw_status.lower():
        logger.info("SOLUCIÓN ÓPTIMA ENCONTRADA - Objetivo: %.2f", obj)
        reserve_margin_dual = _extract_reserve_margin_dual(instance)

    solution_dict = {
        "solver_name": "highs",
        "solver_status": status_display,
        "objective_value": obj,
        "solver_threads_used": threads_used,
        "reserve_margin_dual": reserve_margin_dual,
        "infeasibility_diagnostics": diagnostics,
        "solver_timings": solver_timings,
        "solver_highs_config": {
            "method": highs_config.method,
            "presolve": highs_config.presolve,
            "parallel": highs_config.parallel,
            "run_crossover": highs_config.run_crossover,
            "use_direct": highs_config.use_direct,
            "time_limit": highs_config.time_limit,
        },
    }

    if on_solver_finished is not None:
        try:
            on_solver_finished(instance, solver_obj, results_obj, solution_dict)
        except Exception:  # pragma: no cover
            logger.exception("on_solver_finished falló; se ignora y se continúa.")

    if solver_obj is not None:
        _release_solver(solver_obj)

    return solution_dict


def solve_model(
    instance: pyo.ConcreteModel,
    *,
    solver_name: str = "glpk",
    lp_path: str | Path | None = None,
    on_solver_finished: Callable[[pyo.ConcreteModel, Any, Any, dict], None] | None = None,
) -> dict:
    """Resuelve el modelo usando Pyomo SolverFactory o highspy directo."""
    settings = get_settings()
    highs_config = resolve_highs_config(settings)

    if lp_path is not None and solver_name != "highs":
        write_lp_file(instance, lp_path)

    solver_availability = get_solver_availability()

    fallback_order = (
        [solver_name, *[n for n in SOLVER_FACTORIES if n != solver_name]]
        if solver_name in SOLVER_FACTORIES
        else list(SOLVER_FACTORIES.keys())
    )

    for candidate in fallback_order:
        factory_name = SOLVER_FACTORIES.get(candidate)
        if not factory_name or not solver_availability.get(candidate, False):
            continue

        if candidate == "highs":
            logger.info("Resolviendo con highs (direct=%s)...", highs_config.use_direct)
            return _solve_highs(
                instance,
                settings=settings,
                highs_config=highs_config,
                lp_path=Path(lp_path) if lp_path is not None else None,
                on_solver_finished=on_solver_finished,
            )

        logger.info("Resolviendo con %s (SolverFactory('%s'))...", candidate, factory_name)
        solver = pyo.SolverFactory(factory_name)
        threads_used = _apply_solver_runtime_options(
            solver, candidate=candidate, settings=settings, highs_config=highs_config
        )
        solver_timings: dict[str, float] = {}
        t0 = perf_counter()
        results = solver.solve(
            instance,
            tee=getattr(settings, "sim_solver_tee", False),
            keepfiles=getattr(settings, "sim_solver_keepfiles", False),
            load_solutions=False,
        )
        solver_timings["solver_run_seconds"] = perf_counter() - t0
        solver_timings["solver_backend"] = factory_name

        raw_status = str(results.solver.termination_condition)
        status_display = normalize_solver_status_display(raw_status)
        obj = 0.0
        if "optimal" in raw_status.lower():
            t_load = perf_counter()
            instance.solutions.load_from(results)
            solver_timings["solver_load_solution_seconds"] = perf_counter() - t_load
            try:
                obj = float(pyo.value(instance.OBJ))
            except Exception:
                pass

        logger.info(
            "Solver %s terminó: status=%s (raw=%s), objective=%.4f",
            candidate,
            status_display,
            raw_status,
            obj,
        )

        diagnostics: dict | None = None
        reserve_margin_dual: float | None = None
        if "infeasible" in raw_status.lower():
            diagnostics = _run_infeasibility_diagnostics(instance)
        elif "optimal" in raw_status.lower():
            logger.info("SOLUCIÓN ÓPTIMA ENCONTRADA - Objetivo: %.2f", obj)
            reserve_margin_dual = _extract_reserve_margin_dual(instance)

        solution_dict = {
            "solver_name": candidate,
            "solver_status": status_display,
            "objective_value": obj,
            "solver_threads_used": threads_used,
            "reserve_margin_dual": reserve_margin_dual,
            "infeasibility_diagnostics": diagnostics,
            "solver_timings": solver_timings,
        }

        if on_solver_finished is not None:
            try:
                on_solver_finished(instance, solver, results, solution_dict)
            except Exception:  # pragma: no cover
                logger.exception("on_solver_finished falló; se ignora y se continúa.")

        _release_solver(solver)
        return solution_dict

    avail_text = ", ".join(
        f"{n}={'ok' if e else 'missing'}" for n, e in solver_availability.items()
    )
    raise RuntimeError(
        f"No hay solvers disponibles. Solicitado: '{solver_name}'. "
        f"Disponibilidad: {avail_text}."
    )
