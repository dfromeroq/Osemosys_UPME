"""Resolución de configuración runtime del solver (env + system_settings)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Claves en core.system_setting (texto).
SOLVER_THREADS_KEY = "solver.threads"
SOLVER_PROFILE_KEY = "solver.profile"
SOLVER_HIGHS_METHOD_KEY = "solver.highs.method"
SOLVER_HIGHS_PRESOLVE_KEY = "solver.highs.presolve"
SOLVER_HIGHS_PARALLEL_KEY = "solver.highs.parallel"
SOLVER_HIGHS_HIPO_PARALLEL_TYPE_KEY = "solver.highs.hipo_parallel_type"
SOLVER_HIGHS_CROSSOVER_KEY = "solver.highs.run_crossover"
SOLVER_HIGHS_OPTIONS_JSON_KEY = "solver.highs.options_json"
SOLVER_HIGHS_USE_DIRECT_KEY = "solver.highs.use_direct"
SOLVER_HIGHS_TIME_LIMIT_KEY = "solver.highs.time_limit"
SOLVER_HIGHS_IPM_TOL_KEY = "solver.highs.ipm_optimality_tolerance"
SOLVER_HIGHS_PRIMAL_TOL_KEY = "solver.highs.primal_feasibility_tolerance"
SOLVER_HIGHS_DUAL_TOL_KEY = "solver.highs.dual_feasibility_tolerance"
SOLVER_GLPK_PROFILE_KEY = "solver.glpk.profile"
SOLVER_GLPK_TIME_LIMIT_KEY = "solver.glpk.time_limit"
SOLVER_GLPK_OPTIONS_JSON_KEY = "solver.glpk.options_json"

VALID_HIGHS_METHODS = frozenset({"choose", "simplex", "ipm", "ipx", "hipo"})
VALID_ON_OFF_CHOOSE = frozenset({"off", "on", "choose"})
VALID_SOLVER_PROFILES = frozenset({"default", "balanced", "fast", "memory"})
VALID_GLPK_PROFILES = frozenset({"default", "fast", "strict"})
HIGHS_USE_DEFAULT = ""

# Presets conservadores: no fijan threads para evitar sobre-suscripción. Usa
# SIM_SOLVER_THREADS / solver.threads para asignar cores por despliegue.
_HIGHS_PROFILE_PRESETS: dict[str, dict[str, object]] = {
    "default": {},
    "balanced": {
        "presolve": "on",
        "parallel": "choose",
        "run_crossover": "off",
        "use_direct": True,
    },
    "fast": {
        "method": "ipm",
        "presolve": "on",
        "parallel": "on",
        "run_crossover": "off",
        "use_direct": True,
    },
    "memory": {
        "method": "simplex",
        "presolve": "on",
        "parallel": "off",
        "run_crossover": "off",
        "use_direct": True,
    },
}


@dataclass(frozen=True)
class SolverHighsConfig:
    """Opciones HiGHS efectivas para una corrida.

    Campos vacíos (``""``) significan *no tocar* el default de HiGHS — el mismo
    comportamiento que ``highspy.Highs()`` sin ``setOptionValue`` en el notebook.
    """

    profile: str = "default"
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
    extra_options: dict[str, Any] | None = None
    log_to_console: bool | None = None


@dataclass(frozen=True)
class SolverGlpkConfig:
    """Opciones GLPK aisladas de HiGHS.

    ``fast`` corresponde al perfil A validado (defaults primal+presolve de
    GLPK sobre el modelo reducido). ``strict`` usa simplex exacto (perfil B).
    """

    profile: str = "fast"
    time_limit: float = 0.0
    extra_options: dict[str, Any] | None = None


def _normalize_profile(value: str | None) -> str:
    normalized = str(value or "default").strip().lower()
    if normalized in {"", "default"}:
        return "default"
    if normalized in VALID_SOLVER_PROFILES:
        return normalized
    logger.warning("Perfil solver inválido %r; usando default", value)
    return "default"


def _normalize_glpk_profile(value: str | None) -> str:
    normalized = str(value or "fast").strip().lower()
    if normalized in VALID_GLPK_PROFILES:
        return normalized
    logger.warning("Perfil GLPK inválido %r; usando fast", value)
    return "fast"


def _profile_value(profile: str, key: str, current: object, *, unset: object) -> object:
    """Devuelve valor de perfil solo si el valor actual está explícitamente vacío."""
    if current != unset:
        return current
    return _HIGHS_PROFILE_PRESETS.get(profile, {}).get(key, current)


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


def _parse_options_json(raw: str | None) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Opciones JSON del solver inválidas; se ignoran")
        return {}
    if not isinstance(parsed, dict):
        logger.warning("Opciones JSON del solver deben ser un objeto; se ignoran")
        return {}
    return {str(k): v for k, v in parsed.items()}


def resolve_glpk_config(settings: object) -> SolverGlpkConfig:
    """Combina perfil/opciones GLPK de env y BD sin tocar HiGHS."""
    profile = _normalize_glpk_profile(
        getattr(settings, "sim_solver_glpk_profile", "fast")
    )
    time_limit = float(getattr(settings, "sim_solver_glpk_time_limit", 0) or 0)
    extra_options = _parse_options_json(
        getattr(settings, "sim_solver_glpk_options_json", "")
    )
    try:
        from app.db.session import SessionLocal
    except Exception:  # pragma: no cover
        SessionLocal = None  # type: ignore[misc, assignment]
    if SessionLocal is not None:
        try:
            with SessionLocal() as db:
                db_profile = _read_db_setting(db, SOLVER_GLPK_PROFILE_KEY)
                if db_profile is not None:
                    profile = _normalize_glpk_profile(db_profile)
                time_limit = _read_db_float(db, SOLVER_GLPK_TIME_LIMIT_KEY, time_limit)
                db_options = _read_db_setting(db, SOLVER_GLPK_OPTIONS_JSON_KEY)
                if db_options is not None:
                    extra_options.update(_parse_options_json(db_options))
        except Exception:
            logger.exception("No fue posible leer GLPK settings desde BD; usando env")
    return SolverGlpkConfig(
        profile=profile,
        time_limit=max(0.0, time_limit),
        extra_options=extra_options,
    )


def glpk_options(config: SolverGlpkConfig) -> dict[str, Any]:
    """Traduce perfiles A/B a flags de ``glpsol`` aceptados por Pyomo."""
    options: dict[str, Any] = {}
    if config.profile == "fast":
        # Los defaults GLPK ya son primal+scale+adv+presolve. Forzar dual fue
        # más rápido pero no recuperó una solución factible en el modelo UPME.
        pass
    elif config.profile == "strict":
        options.update({"exact": None})
    if config.time_limit > 0:
        options["tmlim"] = max(1, int(config.time_limit))
    if config.extra_options:
        options.update(config.extra_options)
    return options


def apply_glpk_options_to_solver(solver: object, config: SolverGlpkConfig) -> dict[str, Any]:
    options = glpk_options(config)
    target = getattr(solver, "options", None)
    if target is not None:
        target.update(options)
    return options


def resolve_highs_config(settings: object) -> SolverHighsConfig:
    """Combina env vars con perfil y overrides de BD (admin UI).

    Precedencia: defaults HiGHS < perfil < overrides específicos env < perfil BD
    < overrides específicos BD. El perfil no pisa opciones específicas ya
    definidas; solo rellena vacíos.
    """
    profile = _normalize_profile(getattr(settings, "sim_solver_profile", "default"))
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
    extra_options = _parse_options_json(getattr(settings, "sim_solver_highs_options_json", ""))

    method = str(_profile_value(profile, "method", method, unset=HIGHS_USE_DEFAULT))
    presolve = str(_profile_value(profile, "presolve", presolve, unset=HIGHS_USE_DEFAULT))
    parallel = str(_profile_value(profile, "parallel", parallel, unset=HIGHS_USE_DEFAULT))
    run_crossover = str(_profile_value(profile, "run_crossover", run_crossover, unset=HIGHS_USE_DEFAULT))
    use_direct = bool(_profile_value(profile, "use_direct", use_direct, unset=True))

    try:
        from app.db.session import SessionLocal
    except Exception:  # pragma: no cover
        SessionLocal = None  # type: ignore[misc, assignment]

    if SessionLocal is not None:
        try:
            with SessionLocal() as db:
                from app.services.system_settings_service import SystemSettingsService

                threads = SystemSettingsService.get_solver_threads(db, fallback=threads)
                db_profile = _read_db_setting(db, SOLVER_PROFILE_KEY)
                if db_profile is not None:
                    profile = _normalize_profile(db_profile)
                    method = str(_profile_value(profile, "method", method, unset=HIGHS_USE_DEFAULT))
                    presolve = str(_profile_value(profile, "presolve", presolve, unset=HIGHS_USE_DEFAULT))
                    parallel = str(_profile_value(profile, "parallel", parallel, unset=HIGHS_USE_DEFAULT))
                    run_crossover = str(_profile_value(profile, "run_crossover", run_crossover, unset=HIGHS_USE_DEFAULT))
                    use_direct = bool(_profile_value(profile, "use_direct", use_direct, unset=True))
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
                db_options_json = _read_db_setting(db, SOLVER_HIGHS_OPTIONS_JSON_KEY)
                if db_options_json is not None:
                    extra_options.update(_parse_options_json(db_options_json))
        except Exception:
            logger.exception("No fue posible leer solver settings desde BD; usando env defaults")

    return SolverHighsConfig(
        profile=profile,
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
        extra_options=extra_options,
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

    if config.extra_options:
        options.update(config.extra_options)

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
