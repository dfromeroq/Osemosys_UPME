"""Resolución de configuración runtime del solver (env + system_settings)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Claves en core.system_setting (texto).
SOLVER_THREADS_KEY = "solver.threads"
SOLVER_HIGHS_METHOD_KEY = "solver.highs.method"
SOLVER_HIGHS_PRESOLVE_KEY = "solver.highs.presolve"
SOLVER_HIGHS_PARALLEL_KEY = "solver.highs.parallel"
SOLVER_HIGHS_HIPO_PARALLEL_TYPE_KEY = "solver.highs.hipo_parallel_type"
SOLVER_HIGHS_CROSSOVER_KEY = "solver.highs.run_crossover"
SOLVER_HIGHS_USE_DIRECT_KEY = "solver.highs.use_direct"
SOLVER_HIGHS_TIME_LIMIT_KEY = "solver.highs.time_limit"
SOLVER_HIGHS_IPM_TOL_KEY = "solver.highs.ipm_optimality_tolerance"
SOLVER_HIGHS_PRIMAL_TOL_KEY = "solver.highs.primal_feasibility_tolerance"
SOLVER_HIGHS_DUAL_TOL_KEY = "solver.highs.dual_feasibility_tolerance"

VALID_HIGHS_METHODS = frozenset({"choose", "simplex", "ipm", "ipx", "hipo"})
VALID_ON_OFF_CHOOSE = frozenset({"off", "on", "choose"})
HIGHS_USE_DEFAULT = ""


@dataclass(frozen=True)
class SolverHighsConfig:
    """Opciones HiGHS efectivas para una corrida.

    Campos vacíos (``""``) significan *no tocar* el default de HiGHS — el mismo
    comportamiento que ``highspy.Highs()`` sin ``setOptionValue`` en el notebook.
    """

    threads: int = 0
    method: str = HIGHS_USE_DEFAULT
    presolve: str = HIGHS_USE_DEFAULT
    parallel: str = HIGHS_USE_DEFAULT
    hipo_parallel_type: str = ""
    run_crossover: str = HIGHS_USE_DEFAULT
    use_direct: bool = True
    time_limit: float = 0.0
    ipm_optimality_tolerance: float = 1e-7
    primal_feasibility_tolerance: float = 1e-7
    dual_feasibility_tolerance: float = 1e-7
    log_to_console: bool | None = None


def _unset_highs_override(value: str | None) -> str:
    """``default`` / vacío → no aplicar opción (dejar HiGHS como viene)."""
    if not value:
        return HIGHS_USE_DEFAULT
    normalized = str(value).strip().lower()
    if normalized in {"", "default"}:
        return HIGHS_USE_DEFAULT
    return normalized


def _normalize_choice(value: str | None, *, allowed: frozenset[str], default: str) -> str:
    if not value:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"", "default"}:
        return HIGHS_USE_DEFAULT
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


def resolve_highs_config(settings: object) -> SolverHighsConfig:
    """Combina env vars con overrides de BD (admin UI)."""
    threads = int(getattr(settings, "sim_solver_threads", 0) or 0)
    method = _unset_highs_override(getattr(settings, "sim_solver_highs_method", HIGHS_USE_DEFAULT))
    presolve = _unset_highs_override(getattr(settings, "sim_solver_highs_presolve", HIGHS_USE_DEFAULT))
    parallel = _unset_highs_override(getattr(settings, "sim_solver_highs_parallel", HIGHS_USE_DEFAULT))
    hipo_parallel_type = str(
        getattr(settings, "sim_solver_highs_hipo_parallel_type", "") or ""
    )
    run_crossover = _unset_highs_override(
        getattr(settings, "sim_solver_highs_crossover", HIGHS_USE_DEFAULT)
    )
    use_direct = bool(getattr(settings, "sim_solver_highs_direct", True))
    time_limit = float(getattr(settings, "sim_solver_highs_time_limit", 0) or 0)
    ipm_tol = float(getattr(settings, "sim_solver_highs_ipm_tol", 1e-7) or 1e-7)
    primal_tol = float(getattr(settings, "sim_solver_highs_primal_tol", 1e-7) or 1e-7)
    dual_tol = float(getattr(settings, "sim_solver_highs_dual_tol", 1e-7) or 1e-7)

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
                    method = _unset_highs_override(db_method)
                db_presolve = _read_db_setting(db, SOLVER_HIGHS_PRESOLVE_KEY)
                if db_presolve is not None:
                    presolve = _unset_highs_override(db_presolve)
                db_parallel = _read_db_setting(db, SOLVER_HIGHS_PARALLEL_KEY)
                if db_parallel is not None:
                    parallel = _unset_highs_override(db_parallel)
                db_hipo_parallel_type = _read_db_setting(
                    db,
                    SOLVER_HIGHS_HIPO_PARALLEL_TYPE_KEY,
                )
                if db_hipo_parallel_type is not None:
                    hipo_parallel_type = db_hipo_parallel_type
                db_crossover = _read_db_setting(db, SOLVER_HIGHS_CROSSOVER_KEY)
                if db_crossover is not None:
                    run_crossover = _unset_highs_override(db_crossover)
                use_direct = _read_db_bool(db, SOLVER_HIGHS_USE_DIRECT_KEY, use_direct)
                time_limit = _read_db_float(db, SOLVER_HIGHS_TIME_LIMIT_KEY, time_limit)
                ipm_tol = _read_db_float(db, SOLVER_HIGHS_IPM_TOL_KEY, ipm_tol)
                primal_tol = _read_db_float(db, SOLVER_HIGHS_PRIMAL_TOL_KEY, primal_tol)
                dual_tol = _read_db_float(db, SOLVER_HIGHS_DUAL_TOL_KEY, dual_tol)
        except Exception:
            logger.exception("No fue posible leer solver settings desde BD; usando env defaults")

    return SolverHighsConfig(
        threads=threads,
        method=_normalize_choice(method, allowed=VALID_HIGHS_METHODS, default=HIGHS_USE_DEFAULT),
        presolve=_normalize_choice(presolve, allowed=VALID_ON_OFF_CHOOSE, default=HIGHS_USE_DEFAULT),
        parallel=_normalize_choice(parallel, allowed=VALID_ON_OFF_CHOOSE, default=HIGHS_USE_DEFAULT),
        hipo_parallel_type=hipo_parallel_type.strip().lower(),
        run_crossover=_normalize_choice(
            run_crossover,
            allowed=VALID_ON_OFF_CHOOSE,
            default=HIGHS_USE_DEFAULT,
        ),
        use_direct=use_direct,
        time_limit=max(0.0, time_limit),
        ipm_optimality_tolerance=ipm_tol,
        primal_feasibility_tolerance=primal_tol,
        dual_feasibility_tolerance=dual_tol,
        log_to_console=None,
    )


def _display_highs_value(value: str) -> str:
    return value if value else "default"


def apply_highs_options_to_model(h: object, config: SolverHighsConfig) -> int | None:
    """Aplica solo overrides explícitos a ``highspy.Highs`` o ``highs_options``.

    Sin overrides, HiGHS conserva sus defaults internos (mismo camino que el notebook).
    """
    options: dict[str, object] = {}
    if config.method:
        options["solver"] = config.method
    if config.presolve:
        options["presolve"] = config.presolve
    if config.parallel:
        options["parallel"] = config.parallel
    if config.run_crossover:
        options["run_crossover"] = config.run_crossover
    if config.log_to_console is not None:
        options["log_to_console"] = config.log_to_console
    if config.threads > 0:
        options["threads"] = config.threads
    if config.time_limit > 0:
        options["time_limit"] = config.time_limit
    if config.method == "ipm":
        options["ipm_optimality_tolerance"] = config.ipm_optimality_tolerance

    options["primal_feasibility_tolerance"] = config.primal_feasibility_tolerance
    options["dual_feasibility_tolerance"] = config.dual_feasibility_tolerance

    if config.method == "hipo" and config.hipo_parallel_type:
        options["hipo_parallel_type"] = config.hipo_parallel_type

    if not options:
        return None

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
            status = set_option(key, value)
        except Exception:  # pragma: no cover - depende de versión highspy
            logger.debug("HiGHS no aceptó opción %s=%s", key, value, exc_info=True)
            if key == "solver" and value == "hipo":
                raise ValueError(
                    "La instalación actual de HiGHS no acepta solver=hipo. "
                    "Reconstruye la imagen con HIGHS_BUILD_FROM_SOURCE=1 "
                    "y HIGHS_ENABLE_HIPO=1."
                )
            continue
        if _is_highs_status_error(status):
            logger.debug("HiGHS rechazó opción %s=%s: %s", key, value, status)
            if key == "solver" and value == "hipo":
                raise ValueError(
                    "La instalación actual de HiGHS no acepta solver=hipo. "
                    "Reconstruye la imagen con HIGHS_BUILD_FROM_SOURCE=1 "
                    "y HIGHS_ENABLE_HIPO=1."
                )
    try:
        if config.threads > 0:
            return int(config.threads)
    except (TypeError, ValueError):
        pass
    return None


def _is_highs_status_error(status: object) -> bool:
    """Detecta errores devueltos por ``highspy.Highs.setOptionValue``."""
    if status is None:
        return False
    if isinstance(status, str):
        return status.lower().endswith("kerror")
    try:
        import highspy

        return status == highspy.HighsStatus.kError
    except Exception:  # pragma: no cover - depende de highspy instalado
        return str(status).lower().endswith("kerror")
