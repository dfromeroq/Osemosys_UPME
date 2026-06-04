"""Resolución del modelo OSeMOSYS.

Replica las celdas 27-28 del notebook OPT_YA_20260220:
  - Generación de archivo LP con symbolic_solver_labels (opcional)
  - HiGHS: highspy directo vía archivo LP (benchmark: ~6x más rápido que appsi_highs)
  - GLPK/Gurobi: Pyomo SolverFactory
  - Diagnósticos de infactibilidad (constraint violations, variable bounds)

Uso: recibe la instancia concreta de instance_builder.build_instance();
     devuelve dict con solver_name, solver_status, objective_value.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

import pyomo.environ as pyo
from pyomo.core import Constraint, Suffix, Var, value

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Alias usado en solve_model -> nombre del factory Pyomo (appsi_highs, glpk, gurobi).
SOLVER_FACTORIES: dict[str, str] = {
    "highs": "appsi_highs",
    "glpk": "glpk",
    "gurobi": "gurobi",
}


def normalize_solver_status_display(status: str) -> str:
    """Convierte términos en inglés del solver a etiquetas en español para la API/UI.

    Pyomo/HiGHS/GLPK devuelven ``infeasible``; en la aplicación se muestra ``infactible``.
    La detección interna sigue usando el valor bruto de Pyomo antes de normalizar.
    """
    s = str(status)
    if "infeasible" in s.lower():
        return re.sub("infeasible", "infactible", s, flags=re.IGNORECASE)
    if "unknown" in s.lower():
        return "desconocido"
    return s


def _highs_available() -> bool:
    """Comprueba si highspy está instalado y usable (ruta HiGHS productiva)."""
    try:
        import highspy  # noqa: F401

        highspy.Highs()
    except Exception:
        return False
    return True


def _gurobi_lightweight_available() -> bool:
    """Chequea si gurobipy está instalado SIN consumir licencia.

    `pyo.SolverFactory("gurobi").available()` crea un `gurobipy.Model()` para
    probar la licencia, lo cual con licencias **Single-Use** cuenta como una
    sesión activa. Cuando el api (3 uvicorn workers) y el simulation-worker
    arrancan en paralelo y todos llaman a `get_solver_availability()` se
    producen colisiones tipo "Single-use license. Another Gurobi process
    running.". Aquí solo verificamos que el módulo se pueda importar; la
    licencia se valida al hacer el `solve()` real.
    """
    try:
        import gurobipy  # noqa: F401
    except Exception:
        return False
    return True


def get_solver_availability() -> dict[str, bool]:
    """Comprueba para cada solver si está disponible (instalado y usable).

    Para Gurobi se hace un chequeo *liviano* basado solo en si `gurobipy`
    es importable, para no consumir una sesión de licencia Single-Use sólo
    para probar disponibilidad.
    """
    availability: dict[str, bool] = {}
    for solver_alias, solver_factory in SOLVER_FACTORIES.items():
        if solver_alias == "gurobi":
            availability[solver_alias] = _gurobi_lightweight_available()
            continue
        if solver_alias == "highs":
            availability[solver_alias] = _highs_available()
            continue
        solver = pyo.SolverFactory(solver_factory)
        availability[solver_alias] = bool(
            solver is not None and solver.available(exception_flag=False)
        )
    return availability


def write_lp_file(
    instance: pyo.ConcreteModel,
    lp_path: str | Path,
) -> Path:
    """Genera archivo LP con etiquetas simbólicas para debugging.

    Replica la celda 27 del notebook OPT_YA_20260220.
    symbolic_solver_labels=True hace que los nombres de restricciones/variables sean legibles.
    """
    lp_path = Path(lp_path)
    lp_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Generando archivo LP: %s", lp_path)
    instance.write(
        filename=str(lp_path),
        io_options={"symbolic_solver_labels": True},
    )
    file_size_mb = lp_path.stat().st_size / (1024 * 1024)
    logger.info("Archivo LP generado (%.2f MB): %s", file_size_mb, lp_path)
    return lp_path


def _release_solver(solver: object) -> None:
    """Libera recursos del solver inmediatamente tras el solve.

    Para Gurobi (`gurobi_direct` / `gurobi_persistent`) el objeto Pyomo guarda
    una referencia al ``gurobipy.Env`` y al ``gurobipy.Model``, manteniendo
    activa la sesión de licencia hasta que el GC los libere. Con licencia
    Single-Use eso impide cualquier otro solve concurrente.

    Estrategia:
      1. Llamar ``solver.close()`` / ``release()`` si lo expone.
      2. Cerrar ``_solver_model`` y ``_solver_env`` con ``dispose()``.
      3. Forzar ``gc.collect()`` para que cualquier referencia residual
         (e.g. capturada por results) se libere de inmediato.
    """
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
        # gurobi_direct/persistent: cerrar el solver_model y env explícitamente.
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

    # Limpiar referencias residuales (results, plugin) que pueden retener el
    # Env de gurobipy. gc.collect() acelera la liberación de la licencia.
    gc.collect()
    # gurobipy expone `disposeDefaultEnv()` para destruir el Env implícito
    # creado al usar `Model()` sin pasar Env explícito. Sin esto, en algunas
    # versiones la licencia queda tomada hasta que el proceso muera.
    try:
        import gurobipy as gp

        dispose_default = getattr(gp, "disposeDefaultEnv", None)
        if callable(dispose_default):
            dispose_default()
    except Exception:  # pragma: no cover - gurobipy no instalado
        pass


def _resolve_solver_threads(settings: object) -> int:
    """Devuelve los hilos a entregar al solver.

    Prioridad: ``core.system_setting['solver.threads']`` (configurable desde la
    UI admin) → ``SIM_SOLVER_THREADS`` (env var del despliegue). Si BD no está
    accesible (ej. tests sin DB), cae al env var.
    """
    fallback = int(getattr(settings, "sim_solver_threads", 0) or 0)
    try:
        from app.db.session import SessionLocal
        from app.services.system_settings_service import SystemSettingsService
    except Exception:  # pragma: no cover - import defensivo
        return fallback
    try:
        with SessionLocal() as db:
            return SystemSettingsService.get_solver_threads(db, fallback=fallback)
    except Exception:
        logger.exception(
            "No fue posible leer solver.threads desde BD; usando fallback=%s",
            fallback,
        )
        return fallback


def _hardware_thread_limit() -> int:
    """CPUs disponibles para el proceso (affinity o cpu_count)."""
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, NotImplementedError, OSError):
        return os.cpu_count() or 1


def _effective_solver_threads(configured: int) -> int:
    """Hilos a entregar al solver: cap por hardware; 0 → todos los CPUs."""
    limit = _hardware_thread_limit()
    if configured <= 0:
        return limit
    applied = min(configured, limit)
    if configured > limit:
        logger.warning(
            "solver.threads=%s excede CPUs disponibles (%s); usando %s",
            configured,
            limit,
            applied,
        )
    return applied


def _solver_thread_settings(settings: object) -> tuple[int, int]:
    """Devuelve (configurado admin/env, aplicado al solver tras cap hardware)."""
    configured = _resolve_solver_threads(settings)
    return configured, _effective_solver_threads(configured)


def _reset_highspy_scheduler() -> None:
    try:
        import highspy

        if hasattr(highspy.Highs, "resetGlobalScheduler"):
            highspy.Highs.resetGlobalScheduler()
    except Exception:  # pragma: no cover - best effort
        pass


def _read_highspy_threads_used(h: object) -> int:
    """Hilos que HiGHS aplicó (getOptionValue); threads=0 → hardware_limit."""
    try:
        result = h.getOptionValue("threads")
        opt = result[1] if isinstance(result, tuple) and len(result) >= 2 else result
        if opt is not None and int(opt) > 0:
            return int(opt)
    except (TypeError, ValueError, AttributeError):
        pass
    return _hardware_thread_limit()


def _highs_model_status_is_notset(status: object) -> bool:
    try:
        import highspy

        notset = getattr(highspy.HighsModelStatus, "kNotset", None)
        if notset is not None and status == notset:
            return True
    except (ImportError, AttributeError):
        pass
    return "notset" in str(status).lower()


def _run_highspy(h: object, *, settings: object) -> float:
    """Ejecuta h.run(); un retry tras reset scheduler si kNotset."""
    t0 = perf_counter()
    h.run()
    elapsed = perf_counter() - t0
    if not _highs_model_status_is_notset(h.getModelStatus()):
        return elapsed
    logger.warning(
        "HiGHS devolvió kNotset; reintentando run() tras resetGlobalScheduler",
    )
    _reset_highspy_scheduler()
    _, applied = _solver_thread_settings(settings)
    h.setOptionValue("threads", applied)
    t1 = perf_counter()
    h.run()
    return elapsed + (perf_counter() - t1)


def planned_solver_threads(solver_name: str, *, settings: object) -> int | None:
    """Hilos que se aplicarán al solver al iniciar la optimización.

    HiGHS: siempre devuelve hilos efectivos (configurados o ``cpu_count``).
    Gurobi: solo si hay valor explícito > 0 en configuración.
    GLPK y otros: ``None`` (single-thread).
    """
    name = (solver_name or "").lower()
    configured = _resolve_solver_threads(settings)
    if name == "highs":
        return _effective_solver_threads(configured)
    if name == "gurobi" and configured > 0:
        return configured
    return None


def _apply_solver_runtime_options(
    solver: object, *, candidate: str, settings: object
) -> int | None:
    """Aplica opciones runtime al solver y devuelve los hilos efectivos.

    Configura `threads` para HiGHS y Gurobi cuando hay un valor configurado
    (BD o env var). GLPK se mantiene sin cambios.

    Retorna:
      - El número efectivo de hilos leído del propio objeto solver tras
        configurarlo (no el parámetro de entrada). Permite reportar al usuario
        qué decidió finalmente el optimizador.
      - ``None`` si el solver es single-thread (GLPK) o si no se pudo leer.
    """
    configured_threads = _resolve_solver_threads(settings)

    if candidate == "highs":
        solver_threads = _effective_solver_threads(configured_threads)
        highs_options = getattr(solver, "highs_options", None)
        if not isinstance(highs_options, dict):
            logger.warning(
                "HiGHS no expone highs_options; no se puede leer/escribir threads",
            )
            return None
        highs_options["threads"] = solver_threads
        logger.info("Configurando HiGHS con threads=%s", solver_threads)
        effective = highs_options.get("threads")
        try:
            return int(effective) if effective is not None else None
        except (TypeError, ValueError):
            return None

    if candidate == "gurobi":
        gurobi_options = getattr(solver, "options", None)
        if gurobi_options is None:
            return None
        if configured_threads > 0:
            try:
                gurobi_options["Threads"] = configured_threads
                logger.info("Configurando Gurobi con Threads=%s", configured_threads)
            except Exception:  # pragma: no cover - depende de la versión de pyomo
                logger.warning(
                    "No fue posible aplicar Threads=%s a Gurobi vía solver.options",
                    configured_threads,
                )
        try:
            effective = gurobi_options["Threads"]
            return int(effective) if effective is not None else None
        except (KeyError, TypeError, ValueError):
            return None

    # GLPK u otros solvers single-thread.
    return None


def _pyomo_name_to_lp(name: str) -> str:
    """Convierte nombres Pyomo ``Var[...]`` al formato LP ``Var(...)``."""
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
        getattr(highspy.HighsModelStatus, "kUnknown", None): "unknown",
        getattr(highspy.HighsModelStatus, "kTimeLimit", None): "maxTimeLimit",
        getattr(highspy.HighsModelStatus, "kIterationLimit", None): "maxIterations",
        getattr(highspy.HighsModelStatus, "kObjectiveBound", None): "objectiveLimit",
    }
    for hs, label in mapping.items():
        if hs is not None and status == hs:
            return label
    return str(status)


def _ensure_dual_suffix(instance: pyo.ConcreteModel) -> Suffix:
    dual_suffix = getattr(instance, "dual", None)
    if dual_suffix is None:
        instance.dual = Suffix(direction=Suffix.IMPORT)
        dual_suffix = instance.dual
    return dual_suffix


# Tolerancia IPM más estricta que el default (1e-8): certifica postsolve dual en
# regional con run_crossover=choose sin activar crossover (~11s vs ~26s con on).
HIGHS_IPM_OPTIMALITY_TOLERANCE = 1e-12


def _apply_highspy_options(h: object, *, settings: object) -> tuple[int, int]:
    """Aplica opciones HiGHS fijas (ipm) + threads desde settings/BD o CPU count.

    Returns
    -------
    tuple[int, int]
        ``(solver_threads_configured, solver_threads_applied)``.
    """
    configured, applied = _solver_thread_settings(settings)
    h.setOptionValue("log_to_console", False)
    h.setOptionValue("output_flag", False)
    h.setOptionValue("solver", "ipm")
    h.setOptionValue("presolve", "on")
    h.setOptionValue("parallel", "on")
    h.setOptionValue("run_crossover", "choose")
    h.setOptionValue("ipm_optimality_tolerance", HIGHS_IPM_OPTIMALITY_TOLERANCE)
    h.setOptionValue("threads", applied)
    logger.info(
        "HiGHS directo (highspy): method=ipm presolve=on parallel=on "
        "run_crossover=choose ipm_optimality_tolerance=%s "
        "threads_configured=%s threads_applied=%s",
        HIGHS_IPM_OPTIMALITY_TOLERANCE,
        configured,
        applied,
    )
    return configured, applied


def _apply_highspy_solution(instance: pyo.ConcreteModel, h: object) -> float:
    """Mapea valores primales (columnas LP) a variables Pyomo."""
    solution = h.getSolution()
    lp = h.getLp()
    col_names = list(getattr(lp, "col_names_", []) or [])
    col_values = list(getattr(solution, "col_value", []) or [])

    col_map: dict[str, float] = {}
    for idx, name in enumerate(col_names):
        if idx < len(col_values):
            val = float(col_values[idx])
            col_map[name] = val
            col_map[_lp_name_to_pyomo(name)] = val

    for var in instance.component_data_objects(Var, active=True):
        pyomo_name = var.name
        lp_name = _pyomo_name_to_lp(pyomo_name)
        val = col_map.get(pyomo_name)
        if val is None:
            val = col_map.get(lp_name)
        if val is not None:
            var.set_value(val, skip_validation=True)

    try:
        info = h.getInfo()
        return float(getattr(info, "objective_function_value", 0.0))
    except Exception:
        try:
            return float(pyo.value(instance.OBJ))
        except Exception:
            return 0.0


def _apply_highspy_duals(instance: pyo.ConcreteModel, h: object) -> None:
    """Mapea duales de restricciones (filas LP) al Suffix ``instance.dual``."""
    solution = h.getSolution()
    lp = h.getLp()
    row_names = list(getattr(lp, "row_names_", []) or [])
    row_duals = list(getattr(solution, "row_dual", []) or [])
    if not row_names or not row_duals:
        return

    dual_map: dict[str, float] = {}
    for idx, name in enumerate(row_names):
        if idx < len(row_duals):
            dual_val = float(row_duals[idx])
            dual_map[name] = dual_val
            dual_map[_lp_name_to_pyomo(name)] = dual_val

    if not dual_map:
        return

    dual_suffix = _ensure_dual_suffix(instance)
    for con in instance.component_data_objects(Constraint, active=True):
        pyomo_name = con.name
        lp_name = _pyomo_name_to_lp(pyomo_name)
        dual_val = dual_map.get(pyomo_name)
        if dual_val is None:
            dual_val = dual_map.get(lp_name)
        if dual_val is not None:
            dual_suffix[con] = dual_val


def _appsi_highs_solve_for_diagnostics(
    instance: pyo.ConcreteModel,
    *,
    settings: object,
) -> None:
    """Ejecuta appsi_highs sin cargar solución para habilitar evaluación de constraints."""
    solver = pyo.SolverFactory("appsi_highs")
    if solver is None or not solver.available(exception_flag=False):
        logger.warning(
            "appsi_highs no disponible; diagnosticos basicos de infactibilidad omitidos",
        )
        return
    _apply_solver_runtime_options(solver, candidate="highs", settings=settings)
    try:
        solver.solve(
            instance,
            tee=False,
            keepfiles=getattr(settings, "sim_solver_keepfiles", False),
            load_solutions=False,
        )
    finally:
        _release_solver(solver)


def _solve_with_highspy_lp(
    instance: pyo.ConcreteModel,
    lp_path: Path,
    *,
    settings: object,
) -> dict:
    """Resuelve vía highspy leyendo un LP ya escrito por Pyomo."""
    import highspy

    lp_path = Path(lp_path)
    if not lp_path.is_file():
        raise FileNotFoundError(f"Archivo LP no encontrado: {lp_path}")

    _reset_highspy_scheduler()
    h = highspy.Highs()
    threads_configured, _threads_applied = _apply_highspy_options(h, settings=settings)

    t_read = perf_counter()
    h.readModel(str(lp_path))
    read_model_seconds = perf_counter() - t_read

    highs_run_seconds = _run_highspy(h, settings=settings)
    threads_used = _read_highspy_threads_used(h)

    raw_status = _highs_status_to_raw(h.getModelStatus())
    status_display = normalize_solver_status_display(raw_status)

    obj = 0.0
    map_solution_seconds = 0.0
    reserve_margin_dual: float | None = None
    diagnostics: dict | None = None

    if "optimal" in raw_status.lower():
        t_map = perf_counter()
        obj = _apply_highspy_solution(instance, h)
        _apply_highspy_duals(instance, h)
        map_solution_seconds = perf_counter() - t_map
        logger.info("SOLUCIÓN ÓPTIMA ENCONTRADA (highspy LP) - Objetivo: %.2f", obj)
        reserve_margin_dual = _extract_reserve_margin_dual(instance)
    elif "unknown" in raw_status.lower():
        logger.warning(
            "HiGHS terminó sin certificar optimalidad (status=%s); "
            "no se mapea la solución",
            raw_status,
        )
    elif "infeasible" in raw_status.lower():
        logger.warning(
            "Modelo infactible (highspy LP); fallback appsi_highs para diagnosticos basicos",
        )
        _appsi_highs_solve_for_diagnostics(instance, settings=settings)
        diagnostics = _run_infeasibility_diagnostics(instance)

    logger.info(
        "HiGHS highspy terminó: status=%s (raw=%s), objective=%.4f, "
        "read=%.2fs run=%.2fs map=%.2fs",
        status_display,
        raw_status,
        obj,
        read_model_seconds,
        highs_run_seconds,
        map_solution_seconds,
    )

    return {
        "solver_name": "highs",
        "solver_status": status_display,
        "objective_value": obj,
        "solver_threads_configured": threads_configured,
        "solver_threads_used": threads_used,
        "reserve_margin_dual": reserve_margin_dual,
        "infeasibility_diagnostics": diagnostics,
        "solver_backend": "highspy_lp",
        "read_model_seconds": read_model_seconds,
        "highs_run_seconds": highs_run_seconds,
        "map_solution_seconds": map_solution_seconds,
        "highs_options": {
            "run_crossover": "choose",
            "ipm_optimality_tolerance": HIGHS_IPM_OPTIMALITY_TOLERANCE,
            "threads_configured": threads_configured,
            "threads_used": threads_used,
        },
    }


def _run_infeasibility_diagnostics(instance: pyo.ConcreteModel) -> dict:
    """Analiza restricciones violadas y variable bounds conflictivos.

    Replica la lógica de diagnósticos de infactibilidad
    del notebook OPT_YA_20260220.
    - Recorre restricciones activas: si body < lower o body > upper (con tol 1e-6), registra violación.
    - Recorre variables: si lb > ub, registra conflicto de bounds.
    - Escribe en log las peores 10 y recomendaciones de debugging.
    - Retorna dict con listas estructuradas para persistencia y exportación.
    """
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
    """Extrae el valor dual máximo (absoluto) de la restricción de margen de reserva.

    Intenta primero la restricción nativa ``ReserveMarginConstraint[r, l, y]`` y,
    si UDC está activo, también ``UDC1_UserDefinedConstraintInequality[r, 'UDC_Margin', y]``.
    Devuelve el máximo valor absoluto entre todos los índices, o ``None`` si el
    solver no reportó información dual (e.g. modelo MIP o solver sin soporte).
    Un valor de 0 indica que la restricción no es binding en ningún período;
    un valor > 0 indica que es binding (activa con margen nulo) en al menos un período.
    """
    dual_suffix = getattr(instance, "dual", None)
    if dual_suffix is None:
        return None

    max_abs: float | None = None

    native = getattr(instance, "ReserveMarginConstraint", None)
    if native is not None:
        # `native.values()` itera ConstraintData directamente y evita el
        # re-lookup `native[idx]` por cada (r,l,y). Para modelos con horario
        # detallado son cientos de miles de iteraciones.
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
        # Para UDC necesitamos la clave para filtrar por 'UDC_Margin', así que
        # iteramos .items() en vez de .values().
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


def solve_model(
    instance: pyo.ConcreteModel,
    *,
    solver_name: str = "glpk",
    lp_path: str | Path | None = None,
    on_solver_finished: Callable[[pyo.ConcreteModel, Any, Any, dict], None] | None = None,
) -> dict:
    """Resuelve el modelo OSeMOSYS.

    - ``highs``: escribe LP + ``highspy.Highs().readModel/run`` + mapeo a Pyomo.
    - ``glpk`` / ``gurobi``: Pyomo ``SolverFactory`` (sin cambios).
    - Si el status es infactible (HiGHS), fallback appsi para diagnosticos basicos.

    Parameters
    ----------
    on_solver_finished :
        Hook opcional invocado justo antes de retornar, con la firma
        ``(instance, solver, results, solution_dict)``. Pensado para scripts
        locales que quieren acceder a la instancia Pyomo y al solver (ej. para
        correr un análisis de IIS). El pipeline productivo nunca lo usa.
    """
    settings = get_settings()

    if solver_name == "highs":
        if not _highs_available():
            raise RuntimeError(
                "Solver 'highs' solicitado pero highspy no está disponible.",
            )

        cleanup_lp = False
        effective_lp = lp_path
        if effective_lp is None:
            tmp_dir = Path(tempfile.mkdtemp(prefix="osemosys_lp_"))
            effective_lp = tmp_dir / "model.lp"
            cleanup_lp = True
        else:
            effective_lp = Path(effective_lp)

        t_write = perf_counter()
        write_lp_file(instance, effective_lp)
        write_lp_seconds = perf_counter() - t_write

        try:
            solution_dict = _solve_with_highspy_lp(
                instance,
                effective_lp,
                settings=settings,
            )
        except Exception:
            if cleanup_lp:
                try:
                    effective_lp.unlink(missing_ok=True)
                    effective_lp.parent.rmdir()
                except OSError:
                    pass
            raise

        solution_dict["write_lp_seconds"] = write_lp_seconds

        if cleanup_lp:
            try:
                effective_lp.unlink(missing_ok=True)
                effective_lp.parent.rmdir()
            except OSError:
                pass

        if on_solver_finished is not None:
            try:
                on_solver_finished(instance, None, None, solution_dict)
            except Exception:  # pragma: no cover
                logger.exception("on_solver_finished falló; se ignora y se continúa.")

        return solution_dict

    if lp_path is not None:
        write_lp_file(instance, lp_path)

    solver_availability = get_solver_availability()

    # Orden de intento: el solicitado primero, luego el resto.
    fallback_order = (
        [solver_name, *[n for n in SOLVER_FACTORIES if n != solver_name]]
        if solver_name in SOLVER_FACTORIES
        else list(SOLVER_FACTORIES.keys())
    )

    for candidate in fallback_order:
        if not solver_availability.get(candidate, False):
            continue

        if candidate == "highs":
            cleanup = False
            if lp_path is not None:
                effective = Path(lp_path)
            else:
                tmp_dir = Path(tempfile.mkdtemp(prefix="osemosys_lp_"))
                effective = tmp_dir / "model.lp"
                cleanup = True
            t_write = perf_counter()
            write_lp_file(instance, effective)
            write_lp_seconds = perf_counter() - t_write
            try:
                solution_dict = _solve_with_highspy_lp(
                    instance, effective, settings=settings,
                )
                solution_dict["write_lp_seconds"] = write_lp_seconds
            finally:
                if cleanup:
                    try:
                        effective.unlink(missing_ok=True)
                        effective.parent.rmdir()
                    except OSError:
                        pass
            if on_solver_finished is not None:
                try:
                    on_solver_finished(instance, None, None, solution_dict)
                except Exception:  # pragma: no cover
                    logger.exception("on_solver_finished falló; se ignora y se continúa.")
            return solution_dict

        factory_name = SOLVER_FACTORIES.get(candidate)
        if not factory_name:
            continue

        logger.info("Resolviendo con %s (SolverFactory('%s'))...", candidate, factory_name)
        solver = pyo.SolverFactory(factory_name)
        threads_used = _apply_solver_runtime_options(
            solver, candidate=candidate, settings=settings
        )
        results = solver.solve(
            instance,
            tee=settings.sim_solver_tee,
            keepfiles=settings.sim_solver_keepfiles,
            load_solutions=False,
        )

        raw_status = str(results.solver.termination_condition)
        status_display = normalize_solver_status_display(raw_status)
        obj = 0.0
        if "optimal" in raw_status.lower():
            instance.solutions.load_from(results)
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
        }

        if on_solver_finished is not None:
            try:
                on_solver_finished(instance, solver, results, solution_dict)
            except Exception:  # pragma: no cover - el hook es best-effort
                logger.exception("on_solver_finished falló; se ignora y se continúa.")

        # Libera la licencia del solver tan pronto se termina. Crítico para
        # Gurobi con licencia Single-Use: si el objeto solver queda vivo (por
        # referencias en post-procesamiento), el environment de gurobipy
        # mantiene la sesión tomada y bloquea cualquier otro solve.
        _release_solver(solver)

        return solution_dict

    # Ningún solver estaba disponible.
    avail_text = ", ".join(
        f"{n}={'ok' if e else 'missing'}" for n, e in solver_availability.items()
    )
    raise RuntimeError(
        f"No hay solvers disponibles. Solicitado: '{solver_name}'. "
        f"Disponibilidad: {avail_text}."
    )
