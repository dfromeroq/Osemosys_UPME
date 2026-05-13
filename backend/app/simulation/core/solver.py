"""Resolución del modelo OSeMOSYS.

Replica las celdas 27-28 del notebook OPT_YA_20260220:
  - Generación de archivo LP con symbolic_solver_labels (opcional)
  - SolverFactory("glpk").solve(instance) o appsi_highs
  - Diagnósticos de infactibilidad (constraint violations, variable bounds)

Uso: recibe la instancia concreta de instance_builder.build_instance();
     devuelve dict con solver_name, solver_status, objective_value.

Nota de rendimiento (2026-05):
  appsi_highs transfiere el modelo a HiGHS row-by-row desde Python (~290 s para
  777 k filas). La ruta LP-directa escribe un archivo LP (etiquetas numéricas) y
  lo carga con highspy.readModel() en C puro, eliminando ese overhead.
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
    *,
    symbolic: bool = True,
) -> Path:
    """Genera archivo LP para debugging o descarga.

    Replica la celda 27 del notebook OPT_YA_20260220.
    symbolic=True → nombres legibles; symbolic=False → etiquetas x1/x2/... (más rápido).
    """
    lp_path = Path(lp_path)
    lp_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Generando archivo LP (symbolic=%s): %s", symbolic, lp_path)
    t0 = perf_counter()
    instance.write(
        filename=str(lp_path),
        io_options={"symbolic_solver_labels": symbolic},
    )
    file_size_mb = lp_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Archivo LP generado en %.1fs (%.2f MB): %s",
        perf_counter() - t0, file_size_mb, lp_path,
    )
    return lp_path


def _solve_highs_via_lp(
    instance: pyo.ConcreteModel,
    *,
    threads: int = 0,
    tee: bool = False,
) -> tuple[str, float, int | None]:
    """Resuelve via LP file + highspy.readModel() evitando el overhead row-by-row de appsi.

    Flujo:
      1. Escribe LP con etiquetas numéricas (etiquetas simbólicas son ~30% más lentas).
      2. Carga el LP en HiGHS vía C puro (h.readModel).
      3. Resuelve (h.run).
      4. Carga solución de vuelta a variables Pyomo por posición (mismo orden que
         component_data_objects usa al iterar Vars).
      5. Carga duals al Suffix ``instance.dual`` por posición de fila; si el conteo
         de filas HiGHS ≠ conteo de constraints activos Pyomo, se omite la carga dual.

    Retorna (raw_status, objective_value, threads_used).
    """
    try:
        import highspy  # type: ignore
    except ImportError as exc:
        raise RuntimeError("highspy no disponible para ruta LP directa") from exc

    tmp = Path(tempfile.mktemp(suffix=".lp"))
    tmp.parent.mkdir(parents=True, exist_ok=True)

    # ── 1. Escribir LP (etiquetas simbólicas) ───────────────────────────────
    # symbolic=True necesario para que h.getLp().col_names_ contenga nombres
    # reales; con numeric ("x1","x2",...) no es posible el mapeo por nombre.
    t_write = perf_counter()
    instance.write(str(tmp), io_options={"symbolic_solver_labels": True})
    lp_size_mb = tmp.stat().st_size / (1024 * 1024)
    logger.info(
        "LP write (symbolic labels): %.1fs  %.1f MB",
        perf_counter() - t_write, lp_size_mb,
    )

    # ── 2. Cargar y resolver en HiGHS ───────────────────────────────────────
    h = highspy.Highs()
    if not tee:
        h.setOptionValue("output_flag", False)
    else:
        h.setOptionValue("log_to_console", True)
    if threads > 0:
        h.setOptionValue("threads", threads)

    t_read = perf_counter()
    h.readModel(str(tmp))
    logger.info("HiGHS readModel: %.1fs", perf_counter() - t_read)

    t_run = perf_counter()
    h.run()
    logger.info("HiGHS run: %.1fs", perf_counter() - t_run)

    # ── 3. Estado y objetivo ─────────────────────────────────────────────────
    model_status = h.getModelStatus()
    is_optimal = (model_status == highspy.HighsModelStatus.kOptimal)
    is_infeasible = model_status in (
        highspy.HighsModelStatus.kInfeasible,
        highspy.HighsModelStatus.kUnboundedOrInfeasible,
    )

    obj_val = 0.0
    if is_optimal:
        _ok, obj_val = h.getInfoValue("objective_function_value")
        obj_val = float(obj_val)

    # ── 4. Cargar solución en variables Pyomo (mapeo por nombre) ────────────
    if is_optimal:
        t_load = perf_counter()
        from app.simulation.core.infeasibility_analysis import _canon_name

        sol = h.getSolution()
        col_values = sol.col_value
        lp_col_names = list(h.getLp().col_names_)

        # El LP writer ordena variables por primera aparición en constraints;
        # component_data_objects(Var) las devuelve en orden de declaración.
        # Usar _canon_name (alphanum lowercase) garantiza match sin importar
        # el formato exacto del LP writer (brackets, underscores, parens).
        pyomo_by_canon: dict[str, object] = {
            _canon_name(v.name): v
            for v in instance.component_data_objects(pyo.Var, active=True)
        }

        n_loaded = n_missing = 0
        for lp_name, val in zip(lp_col_names, col_values):
            var_data = pyomo_by_canon.get(_canon_name(lp_name))
            if var_data is not None:
                var_data.set_value(float(val))
                n_loaded += 1
            else:
                n_missing += 1

        if n_missing:
            logger.warning(
                "Vars sin match por nombre: %d/%d — solución incompleta",
                n_missing, len(lp_col_names),
            )
        logger.info(
            "Solución cargada (name-based): %d vars en %.1fs",
            n_loaded, perf_counter() - t_load,
        )

        # ── 5. Cargar duals al Suffix instance.dual ─────────────────────────
        dual_suffix = getattr(instance, "dual", None)
        if dual_suffix is not None:
            row_duals = sol.row_dual
            n_highs_rows = h.getNumRow()
            active_cons = list(
                instance.component_data_objects(pyo.Constraint, active=True)
            )
            n_pyomo_cons = len(active_cons)

            if n_highs_rows == n_pyomo_cons:
                for i, con in enumerate(active_cons):
                    dual_suffix[con] = float(row_duals[i])
                logger.info("Duals cargados (%d filas)", n_highs_rows)
            else:
                logger.info(
                    "Duals omitidos: HiGHS rows=%d ≠ Pyomo constraints=%d",
                    n_highs_rows, n_pyomo_cons,
                )

    try:
        tmp.unlink()
    except OSError:
        pass

    # threads_used
    _ok, effective_threads = h.getOptionValue("threads")
    if _ok == highspy.HighsStatus.kOk and effective_threads:
        threads_used: int | None = int(effective_threads)
    else:
        threads_used = threads if threads > 0 else None

    raw_status: str
    if is_optimal:
        raw_status = "optimal"
    elif is_infeasible:
        raw_status = "infeasible"
    else:
        raw_status = str(model_status).lower().replace("highs model status.", "")

    return raw_status, obj_val, threads_used


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

    def _update(con_data: object) -> None:
        nonlocal max_abs
        try:
            d = dual_suffix.get(con_data)
            if d is not None:
                abs_d = abs(float(d))
                if max_abs is None or abs_d > max_abs:
                    max_abs = abs_d
        except Exception:
            pass

    native = getattr(instance, "ReserveMarginConstraint", None)
    if native is not None:
        for idx in native:
            _update(native[idx])

    udc = getattr(instance, "UDC1_UserDefinedConstraintInequality", None)
    if udc is not None:
        for idx in udc:
            if isinstance(idx, tuple) and len(idx) >= 2 and idx[1] == "UDC_Margin":
                _update(udc[idx])

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
    """Resuelve el modelo usando Pyomo SolverFactory (GLPK/Gurobi) o LP-directo (HiGHS).

    Replica las celdas 27-28 del notebook OPT_YA_20260220.

    Para HiGHS usa ``_solve_highs_via_lp``: escribe LP numérico y llama
    ``highspy.readModel`` (C puro), evitando el overhead Python→C row-by-row de
    ``appsi_highs`` (~290 s para modelos con 777 k filas).

    Si lp_path no es None, escribe un LP simbólico (legible) **después** del solve;
    esto desacopla el archivo de descarga del camino crítico de resolución.

    Parameters
    ----------
    on_solver_finished :
        Hook opcional invocado justo antes de retornar, con la firma
        ``(instance, solver_or_highs, results_or_none, solution_dict)``.
        Pensado para scripts locales; el pipeline productivo nunca lo usa.
    """
    settings = get_settings()
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

        logger.info("Resolviendo con solver '%s'...", candidate)

        # ── Ruta LP-directa para HiGHS ──────────────────────────────────────
        if candidate == "highs":
            solver_threads = _resolve_solver_threads(settings)
            raw_status, obj, threads_used = _solve_highs_via_lp(
                instance,
                threads=solver_threads,
                tee=settings.sim_solver_tee,
            )
            solver_obj = None  # no hay objeto SolverFactory en esta ruta
            results_obj = None

        # ── Ruta legacy Pyomo SolverFactory (GLPK, Gurobi) ─────────────────
        else:
            factory_name = SOLVER_FACTORIES.get(candidate)
            if not factory_name:
                continue
            solver_obj = pyo.SolverFactory(factory_name)
            threads_used = _apply_solver_runtime_options(
                solver_obj, candidate=candidate, settings=settings
            )
            results_obj = solver_obj.solve(
                instance,
                tee=settings.sim_solver_tee,
                keepfiles=settings.sim_solver_keepfiles,
                load_solutions=False,
            )
            raw_status = str(results_obj.solver.termination_condition)
            obj = 0.0
            if "optimal" in raw_status.lower():
                instance.solutions.load_from(results_obj)
                try:
                    obj = float(pyo.value(instance.OBJ))
                except Exception:
                    pass

        # ── Resultado común ──────────────────────────────────────────────────
        status_display = normalize_solver_status_display(raw_status)
        logger.info(
            "Solver %s terminó: status=%s (raw=%s), objective=%.4f",
            candidate, status_display, raw_status, obj,
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
                on_solver_finished(instance, solver_obj, results_obj, solution_dict)
            except Exception:  # pragma: no cover - el hook es best-effort
                logger.exception("on_solver_finished falló; se ignora y se continúa.")

        # Libera la licencia del solver (crítico para Gurobi Single-Use).
        if solver_obj is not None:
            _release_solver(solver_obj)

        # Genera LP simbólico para descarga DESPUÉS del solve (no bloquea el camino crítico).
        if lp_path is not None:
            try:
                write_lp_file(instance, lp_path, symbolic=True)
            except Exception:
                logger.warning("No se pudo escribir LP simbólico en %s", lp_path, exc_info=True)

        return solution_dict

    # Ningún solver estaba disponible.
    avail_text = ", ".join(
        f"{n}={'ok' if e else 'missing'}" for n, e in solver_availability.items()
    )
    raise RuntimeError(
        f"No hay solvers disponibles. Solicitado: '{solver_name}'. "
        f"Disponibilidad: {avail_text}."
    )
