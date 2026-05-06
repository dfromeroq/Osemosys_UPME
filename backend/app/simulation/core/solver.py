"""Resolución del modelo OSeMOSYS.

Replica las celdas 27-28 del notebook OPT_YA_20260220:
  - Generación de archivo LP con symbolic_solver_labels (opcional)
  - SolverFactory("glpk").solve(instance) o appsi_highs
  - Diagnósticos de infactibilidad (constraint violations, variable bounds)

Uso: recibe la instancia concreta de instance_builder.build_instance();
     devuelve dict con solver_name, solver_status, objective_value.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyomo.environ as pyo
from pyomo.core import Constraint, Var, value

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
    if "infeasible" not in s.lower():
        return s
    return re.sub("infeasible", "infactible", s, flags=re.IGNORECASE)


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
    solver_threads = _resolve_solver_threads(settings)

    if candidate == "highs":
        highs_options = getattr(solver, "highs_options", None)
        if not isinstance(highs_options, dict):
            logger.warning(
                "HiGHS no expone highs_options; no se puede leer/escribir threads",
            )
            return None
        if solver_threads > 0:
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
        if solver_threads > 0:
            try:
                gurobi_options["Threads"] = solver_threads
                logger.info("Configurando Gurobi con Threads=%s", solver_threads)
            except Exception:  # pragma: no cover - depende de la versión de pyomo
                logger.warning(
                    "No fue posible aplicar Threads=%s a Gurobi vía solver.options",
                    solver_threads,
                )
        try:
            effective = gurobi_options["Threads"]
            return int(effective) if effective is not None else None
        except (KeyError, TypeError, ValueError):
            return None

    # GLPK u otros solvers single-thread.
    return None


def _run_infeasibility_diagnostics(instance: pyo.ConcreteModel) -> None:
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


def solve_model(
    instance: pyo.ConcreteModel,
    *,
    solver_name: str = "glpk",
    lp_path: str | Path | None = None,
    on_solver_finished: Callable[[pyo.ConcreteModel, Any, Any, dict], None] | None = None,
) -> dict:
    """Resuelve el modelo usando Pyomo SolverFactory.

    Replica las celdas 27-28 del notebook OPT_YA_20260220.
    - Si lp_path no es None, escribe el .lp antes de resolver.
    - Prueba primero el solver solicitado; si no está disponible, prueba el otro (highs/glpk).
    - Si el status es infactible, ejecuta _run_infeasibility_diagnostics.
    - Retorna dict con solver_name, solver_status, objective_value y,
      si infactible, infeasibility_diagnostics.

    Parameters
    ----------
    on_solver_finished :
        Hook opcional invocado justo antes de retornar, con la firma
        ``(instance, solver, results, solution_dict)``. Pensado para scripts
        locales que quieren acceder a la instancia Pyomo y al solver (ej. para
        correr un análisis de IIS). El pipeline productivo nunca lo usa.
    """
    settings = get_settings()
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
        factory_name = SOLVER_FACTORIES.get(candidate)
        if not factory_name or not solver_availability.get(candidate, False):
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
        if "infeasible" in raw_status.lower():
            diagnostics = _run_infeasibility_diagnostics(instance)
        elif "optimal" in raw_status.lower():
            logger.info("SOLUCIÓN ÓPTIMA ENCONTRADA - Objetivo: %.2f", obj)

        solution_dict = {
            "solver_name": candidate,
            "solver_status": status_display,
            "objective_value": obj,
            "solver_threads_used": threads_used,
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
