"""Resolución de configuración runtime del solver (env + system_settings)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Claves en core.system_setting (texto).
SOLVER_THREADS_KEY = "solver.threads"
SOLVER_HIGHS_METHOD_KEY = "solver.highs.method"
SOLVER_HIGHS_PRESOLVE_KEY = "solver.highs.presolve"
SOLVER_HIGHS_PARALLEL_KEY = "solver.highs.parallel"
SOLVER_HIGHS_CROSSOVER_KEY = "solver.highs.run_crossover"
SOLVER_HIGHS_USE_DIRECT_KEY = "solver.highs.use_direct"
SOLVER_HIGHS_TIME_LIMIT_KEY = "solver.highs.time_limit"
SOLVER_HIGHS_IPM_TOL_KEY = "solver.highs.ipm_optimality_tolerance"
SOLVER_HIGHS_PRIMAL_TOL_KEY = "solver.highs.primal_feasibility_tolerance"

VALID_HIGHS_METHODS = frozenset({"choose", "simplex", "ipm", "ipx", "hipo"})
VALID_ON_OFF_CHOOSE = frozenset({"off", "on", "choose"})


@dataclass(frozen=True)
class SolverHighsConfig:
    """Opciones HiGHS efectivas para una corrida."""

    threads: int = 0
    method: str = "choose"
    presolve: str = "on"
    parallel: str = "on"
    run_crossover: str = "on"
    use_direct: bool = False
    time_limit: float = 0.0
    ipm_optimality_tolerance: float = 1e-7
    primal_feasibility_tolerance: float = 1e-7
    log_to_console: bool = False


def _normalize_choice(value: str | None, *, allowed: frozenset[str], default: str) -> str:
    if not value:
        return default
    normalized = str(value).strip().lower()
    if normalized in allowed:
        return normalized
    logger.warning("Valor solver inválido %r; usando default=%s", value, default)
    return default


def _read_db_setting(db, key: str) -> str | None:
    from app.services.system_settings_service import SystemSettingsService

    row = SystemSettingsService.get_raw(db, key)
    if row is None or row.value is None:
        return None
    text = str(row.value).strip()
    return text if text else None


def _read_db_float(db, key: str, default: float) -> float:
    raw = _read_db_setting(db, key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _read_db_bool(db, key: str, default: bool) -> bool:
    raw = _read_db_setting(db, key)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def resolve_highs_config(settings: object, *, simulation_type: str | None = None) -> SolverHighsConfig:
    """Combina env vars con overrides de BD (admin UI)."""
    threads = int(getattr(settings, "sim_solver_threads", 0) or 0)
    method = str(getattr(settings, "sim_solver_highs_method", "choose") or "choose")
    presolve = str(getattr(settings, "sim_solver_highs_presolve", "on") or "on")
    parallel = str(getattr(settings, "sim_solver_highs_parallel", "on") or "on")
    run_crossover = str(getattr(settings, "sim_solver_highs_crossover", "on") or "on")
    use_direct = bool(getattr(settings, "sim_solver_highs_direct", False))
    time_limit = float(getattr(settings, "sim_solver_highs_time_limit", 0) or 0)
    ipm_tol = float(getattr(settings, "sim_solver_highs_ipm_tol", 1e-7) or 1e-7)
    primal_tol = float(getattr(settings, "sim_solver_highs_primal_tol", 1e-7) or 1e-7)

    if str(simulation_type or "").strip().upper() == "REGIONAL":
        regional_threads = getattr(settings, "sim_solver_highs_regional_threads", None)
        if regional_threads is not None:
            threads = int(regional_threads)

        regional_method = getattr(settings, "sim_solver_highs_regional_method", None)
        if regional_method:
            method = str(regional_method)

        regional_presolve = getattr(settings, "sim_solver_highs_regional_presolve", None)
        if regional_presolve:
            presolve = str(regional_presolve)

        regional_parallel = getattr(settings, "sim_solver_highs_regional_parallel", None)
        if regional_parallel:
            parallel = str(regional_parallel)

        regional_crossover = getattr(settings, "sim_solver_highs_regional_crossover", None)
        if regional_crossover:
            run_crossover = str(regional_crossover)

        regional_direct = getattr(settings, "sim_solver_highs_regional_direct", None)
        if regional_direct is not None:
            use_direct = bool(regional_direct)

        regional_time_limit = getattr(settings, "sim_solver_highs_regional_time_limit", None)
        if regional_time_limit is not None:
            time_limit = float(regional_time_limit)

        regional_ipm_tol = getattr(settings, "sim_solver_highs_regional_ipm_tol", None)
        if regional_ipm_tol is not None:
            ipm_tol = float(regional_ipm_tol)

        regional_primal_tol = getattr(settings, "sim_solver_highs_regional_primal_tol", None)
        if regional_primal_tol is not None:
            primal_tol = float(regional_primal_tol)

    try:
        from app.db.session import SessionLocal
    except Exception:  # pragma: no cover
        SessionLocal = None  # type: ignore[misc, assignment]

    if SessionLocal is not None:
        try:
            with SessionLocal() as db:
                from app.services.system_settings_service import SystemSettingsService

                threads = SystemSettingsService.get_solver_threads(db, fallback=threads)
                db_method = _read_db_setting(db, SOLVER_HIGHS_METHOD_KEY)
                if db_method is not None:
                    method = db_method
                db_presolve = _read_db_setting(db, SOLVER_HIGHS_PRESOLVE_KEY)
                if db_presolve is not None:
                    presolve = db_presolve
                db_parallel = _read_db_setting(db, SOLVER_HIGHS_PARALLEL_KEY)
                if db_parallel is not None:
                    parallel = db_parallel
                db_crossover = _read_db_setting(db, SOLVER_HIGHS_CROSSOVER_KEY)
                if db_crossover is not None:
                    run_crossover = db_crossover
                use_direct = _read_db_bool(db, SOLVER_HIGHS_USE_DIRECT_KEY, use_direct)
                time_limit = _read_db_float(db, SOLVER_HIGHS_TIME_LIMIT_KEY, time_limit)
                ipm_tol = _read_db_float(db, SOLVER_HIGHS_IPM_TOL_KEY, ipm_tol)
                primal_tol = _read_db_float(db, SOLVER_HIGHS_PRIMAL_TOL_KEY, primal_tol)
        except Exception:
            logger.exception("No fue posible leer solver settings desde BD; usando env defaults")

    return SolverHighsConfig(
        threads=threads,
        method=_normalize_choice(method, allowed=VALID_HIGHS_METHODS, default="choose"),
        presolve=_normalize_choice(presolve, allowed=VALID_ON_OFF_CHOOSE, default="on"),
        parallel=_normalize_choice(parallel, allowed=VALID_ON_OFF_CHOOSE, default="on"),
        run_crossover=_normalize_choice(run_crossover, allowed=VALID_ON_OFF_CHOOSE, default="on"),
        use_direct=use_direct,
        time_limit=max(0.0, time_limit),
        ipm_optimality_tolerance=ipm_tol,
        primal_feasibility_tolerance=primal_tol,
        log_to_console=False,
    )


def apply_highs_options_to_model(h: object, config: SolverHighsConfig) -> int | None:
    """Aplica ``SolverHighsConfig`` a un ``highspy.Highs`` o dict ``highs_options``."""
    options: dict[str, object] = {
        "solver": config.method,
        "presolve": config.presolve,
        "parallel": config.parallel,
        "run_crossover": config.run_crossover,
        "log_to_console": config.log_to_console,
        "output_flag": False,
        "ipm_optimality_tolerance": config.ipm_optimality_tolerance,
        "primal_feasibility_tolerance": config.primal_feasibility_tolerance,
    }
    if config.threads > 0:
        options["threads"] = config.threads
    if config.time_limit > 0:
        options["time_limit"] = config.time_limit

    if isinstance(h, dict):
        h.update(options)
        effective = h.get("threads")
        try:
            return int(effective) if effective is not None else None
        except (TypeError, ValueError):
            return None

    set_option = getattr(h, "setOptionValue", None)
    if not callable(set_option):
        return None
    for key, value in options.items():
        try:
            set_option(key, value)
        except Exception:  # pragma: no cover - depende de versión highspy
            logger.debug("HiGHS no aceptó opción %s=%s", key, value, exc_info=True)
    try:
        if config.threads > 0:
            return int(config.threads)
    except (TypeError, ValueError):
        pass
    return None
