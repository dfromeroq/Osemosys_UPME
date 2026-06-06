from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración central de la aplicación.

    Las variables se leen desde entorno (y `.env` en desarrollo) para facilitar
    despliegues Docker/on-prem sin cambios de código. Incluye: API, BD, Redis,
    simulación (concurrencia, límites), autenticación (JWT, secret_key).
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="local", alias="ENVIRONMENT")
    project_name: str = Field(default="OSeMOSYS API", alias="PROJECT_NAME")
    api_v1_str: str = Field(default="/api/v1", alias="API_V1_STR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Coma-separado en .env.
    # Default para desarrollo local con Vite.
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://osemosys:osemosys@localhost:5432/osemosys",
        alias="DATABASE_URL",
    )
    db_schema_osemosys: str = Field(default="osemosys", alias="DB_SCHEMA_OSEMOSYS")

    # Queue / simulation
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    simulation_mode: str = Field(default="async", alias="SIMULATION_MODE")
    sim_max_concurrency: int = Field(default=3, alias="SIM_MAX_CONCURRENCY")
    sim_user_active_limit: int = Field(default=1, alias="SIM_USER_ACTIVE_LIMIT")
    sim_total_weight_limit: int = Field(default=8, alias="SIM_TOTAL_WEIGHT_LIMIT")
    sim_weight_national: int = Field(default=1, alias="SIM_WEIGHT_NATIONAL")
    sim_weight_regional: int = Field(default=3, alias="SIM_WEIGHT_REGIONAL")
    sim_stale_task_minutes: int = Field(default=30, alias="SIM_STALE_TASK_MINUTES")
    sim_solver_tee: bool = Field(default=False, alias="SIM_SOLVER_TEE")
    sim_solver_keepfiles: bool = Field(default=False, alias="SIM_SOLVER_KEEPFILES")
    sim_solver_threads: int = Field(default=0, alias="SIM_SOLVER_THREADS")
    sim_solver_highs_method: str = Field(default="", alias="SIM_SOLVER_HIGHS_METHOD")
    sim_solver_highs_presolve: str = Field(default="", alias="SIM_SOLVER_HIGHS_PRESOLVE")
    sim_solver_highs_parallel: str = Field(default="", alias="SIM_SOLVER_HIGHS_PARALLEL")
    sim_solver_highs_hipo_parallel_type: str = Field(
        default="",
        alias="SIM_SOLVER_HIGHS_HIPO_PARALLEL_TYPE",
    )
    sim_solver_highs_crossover: str = Field(default="", alias="SIM_SOLVER_HIGHS_CROSSOVER")
    sim_solver_highs_direct: bool = Field(default=True, alias="SIM_SOLVER_HIGHS_DIRECT")
    sim_solver_highs_time_limit: float = Field(default=0.0, alias="SIM_SOLVER_HIGHS_TIME_LIMIT")
    sim_solver_highs_ipm_tol: float = Field(default=1e-7, alias="SIM_SOLVER_HIGHS_IPM_TOL")
    sim_solver_highs_primal_tol: float = Field(default=1e-7, alias="SIM_SOLVER_HIGHS_PRIMAL_TOL")
    simulation_artifacts_dir: str = Field(default="/app/tmp", alias="SIMULATION_ARTIFACTS_DIR")
    docker_socket_path: str = Field(default="/var/run/docker.sock", alias="DOCKER_SOCKET_PATH")
    docker_metrics_services: str = Field(
        default="api,simulation-worker,db,redis,frontend",
        alias="DOCKER_METRICS_SERVICES",
    )
    docker_metrics_timeout_seconds: float = Field(
        default=3.0,
        alias="DOCKER_METRICS_TIMEOUT_SECONDS",
    )
    docker_metrics_cache_ttl_seconds: float = Field(
        default=5.0,
        alias="DOCKER_METRICS_CACHE_TTL_SECONDS",
    )
    # Proyecto Compose a considerar. Si está vacío, se auto-detecta a partir
    # de la etiqueta `com.docker.compose.project` del propio contenedor (via
    # /containers/{hostname}/json). Fallback: todos los proyectos.
    docker_metrics_project: str = Field(default="", alias="DOCKER_METRICS_PROJECT")
    simulation_ops_environment_name: str = Field(
        default="",
        alias="SIMULATION_OPS_ENVIRONMENT_NAME",
    )
    simulation_ops_remote_environments: str = Field(
        default="",
        alias="SIMULATION_OPS_REMOTE_ENVIRONMENTS",
    )

    # Auth
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    def cors_origins_list(self) -> list[str]:
        """Convierte `CORS_ORIGINS` coma-separado a lista normalizada."""
        if not self.cors_origins:
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def is_sqlite(self) -> bool:
        """Indica si `DATABASE_URL` apunta a SQLite."""
        normalized = (self.database_url or "").strip().lower()
        return normalized.startswith("sqlite:///") or normalized.startswith("sqlite+pysqlite:///")

    def is_sync_simulation_mode(self) -> bool:
        """Indica si la simulación debe ejecutarse en modo síncrono local."""
        return (self.simulation_mode or "").strip().lower() == "sync"

    def docker_metrics_services_list(self) -> list[str]:
        """Servicios Docker considerados al sumar uso de RAM."""
        if not self.docker_metrics_services:
            return []
        return [service.strip() for service in self.docker_metrics_services.split(",") if service.strip()]

    def simulation_ops_remote_environments_list(self) -> list[dict]:
        """Ambientes remotos configurados para el tablero operacional.

        Formato esperado en env:
        ``[{"name":"prod","base_url":"https://.../api/v1","token":"..."}]``.
        """
        import json

        raw = (self.simulation_ops_remote_environments or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]


@lru_cache
def get_settings() -> Settings:
    """Retorna settings cacheados por proceso.

    Evita recalcular/parsear configuración en cada request.
    """
    return Settings()


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Concentrar configuración runtime para API, seguridad y simulación.
#
# Posibles mejoras:
# - Separar settings por dominio (API, DB, worker) con sub-modelos.
#
# Riesgos en producción:
# - Valores inseguros por defecto (e.g., `SECRET_KEY`) requieren override obligatorio.
#
# Escalabilidad:
# - Lectura cacheada O(1), sin impacto en hot path.
