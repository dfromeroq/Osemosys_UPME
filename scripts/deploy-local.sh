#!/usr/bin/env bash
set -euo pipefail

# Despliegue del monorepo OSeMOSYS usando Docker Compose.
# - Expone el frontend por el puerto configurado
# - Mantiene API/DB/Redis locales por defecto
# - Ejecuta migraciones y seed
# - Crea/actualiza usuarios de aplicación

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-osemosys}"
export COMPOSE_PROJECT_NAME="${PROJECT_NAME}"

LAST_BACKUP_FILE=""
PREV_API_IMAGE_ID=""
PREV_WORKER_IMAGE_ID=""
PREV_FRONTEND_IMAGE_ID=""

capture_previous_images() {
  PREV_API_IMAGE_ID="$(docker compose images -q api 2>/dev/null || true)"
  PREV_WORKER_IMAGE_ID="$(docker compose images -q simulation-worker 2>/dev/null || true)"
  PREV_FRONTEND_IMAGE_ID="$(docker compose images -q frontend 2>/dev/null || true)"
}

rollback_previous_images() {
  if [[ -z "${PREV_API_IMAGE_ID}" && -z "${PREV_WORKER_IMAGE_ID}" && -z "${PREV_FRONTEND_IMAGE_ID}" ]]; then
    return 0
  fi

  log "Intentando rollback operativo a imágenes previas"
  [[ -n "${PREV_API_IMAGE_ID}" ]] && docker image tag "${PREV_API_IMAGE_ID}" "${PROJECT_NAME}-api" || true
  [[ -n "${PREV_WORKER_IMAGE_ID}" ]] && docker image tag "${PREV_WORKER_IMAGE_ID}" "${PROJECT_NAME}-simulation-worker" || true
  [[ -n "${PREV_FRONTEND_IMAGE_ID}" ]] && docker image tag "${PREV_FRONTEND_IMAGE_ID}" "${PROJECT_NAME}-frontend" || true

  docker compose up -d --no-build --scale "simulation-worker=${SIM_WORKER_REPLICAS:-2}" || true
}

log() {
  printf "\n[%s] %s\n" "$(date +'%H:%M:%S')" "$*"
}

log_git_revision() {
  if ! command -v git >/dev/null 2>&1; then
    return 0
  fi

  if ! git -C "${REPO_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 0
  fi

  local revision branch
  revision="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || true)"
  branch="$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"

  if [[ -n "${revision}" ]]; then
    log "Desplegando revisión git ${revision} (${branch:-detached})"
  fi
}

copy_env_template_if_missing() {
  local target_file="$1"
  shift

  if [[ -f "${target_file}" ]]; then
    return 0
  fi

  local candidate
  for candidate in "$@"; do
    if [[ -f "${candidate}" ]]; then
      cp "${candidate}" "${target_file}"
      return 0
    fi
  done

  echo "No encontré plantilla para crear ${target_file}" >&2
  return 1
}

on_error() {
  local exit_code=$?
  local api_container_id=""
  echo
  echo "ERROR: despliegue falló (exit=${exit_code})."
  echo "Logs recientes de API:"
  docker compose logs --tail=200 api || true
  echo "Estado de healthcheck de API:"
  api_container_id="$(docker compose ps -q api 2>/dev/null || true)"
  if [[ -n "${api_container_id}" ]]; then
    docker inspect --format='{{json .State.Health}}' "${api_container_id}" 2>/dev/null || true
  fi
  rollback_previous_images
  docker compose ps || true
  if [[ -n "${LAST_BACKUP_FILE}" ]]; then
    echo "Backup disponible: ${LAST_BACKUP_FILE}"
    echo "Restaurar (manual):"
    echo "  gunzip -c '${LAST_BACKUP_FILE}' | docker compose exec -T db psql -U \"\${POSTGRES_USER}\" -d \"\${POSTGRES_DB}\""
  fi
  exit "${exit_code}"
}

trap on_error ERR

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Falta comando requerido: $1" >&2
    exit 1
  fi
}

require_non_default_secret_key() {
  local secret_key="$1"

  if [[ -z "${secret_key}" ]]; then
    echo "SECRET_KEY es obligatorio para despliegue." >&2
    exit 1
  fi

  if [[ "${secret_key}" == "change-me" || "${secret_key}" == "change-me-local" || "${secret_key}" == "replace-me-before-deploy" ]]; then
    echo "SECRET_KEY no puede usar el valor por defecto del ejemplo." >&2
    exit 1
  fi
}

is_port_in_use() {
  local port="$1"
  ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)${port}$"
}

upsert_env_key() {
  local file="$1"
  local key="$2"
  local value="$3"

  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf "%s=%s\n" "$key" "$value" >>"$file"
  fi
}

wait_http_ok() {
  local url="$1"
  local retries="$2"
  local sleep_seconds="$3"
  for _ in $(seq 1 "${retries}"); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${sleep_seconds}"
  done
  return 1
}

wait_celery_ping() {
  local retries="$1"
  local sleep_seconds="$2"

  for _ in $(seq 1 "${retries}"); do
    if docker compose exec -T simulation-worker sh -lc \
      'celery -A app.simulation.celery_app:celery_app inspect ping --timeout=5 >/dev/null 2>&1'; then
      return 0
    fi
    sleep "${sleep_seconds}"
  done
  return 1
}

wait_db_healthy() {
  local retries="$1"
  local sleep_seconds="$2"

  for _ in $(seq 1 "${retries}"); do
    if docker compose exec -T db sh -lc 'pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"' >/dev/null 2>&1; then
      return 0
    fi
    sleep "${sleep_seconds}"
  done
  return 1
}

ensure_writable_backup_dir() {
  local desired_dir="$1"
  local fallback_dir="${REPO_ROOT}/backups"
  local probe_file=""

  if mkdir -p "${desired_dir}" 2>/dev/null; then
    probe_file="${desired_dir}/.write_test_$$"
    if touch "${probe_file}" 2>/dev/null; then
      rm -f "${probe_file}" || true
      echo "${desired_dir}"
      return 0
    fi
  fi

  echo "WARN: BACKUP_DIR '${desired_dir}' no es escribible; usando fallback '${fallback_dir}'." >&2
  mkdir -p "${fallback_dir}"
  probe_file="${fallback_dir}/.write_test_$$"
  if ! touch "${probe_file}" 2>/dev/null; then
    echo "No se pudo usar ni BACKUP_DIR ni fallback '${fallback_dir}'." >&2
    return 1
  fi
  rm -f "${probe_file}" || true
  echo "${fallback_dir}"
}

ensure_external_network() {
  local network_name="$1"

  if [[ -z "${network_name}" ]]; then
    return 0
  fi

  if docker network inspect "${network_name}" >/dev/null 2>&1; then
    return 0
  fi

  log "Creando red Docker externa '${network_name}'"
  docker network create "${network_name}" >/dev/null
}

has_frontend_service() {
  grep -Eq '^  frontend:$' "${REPO_ROOT}/docker-compose.yml"
}

normalize_unified_monorepo_env() {
  if ! has_frontend_service; then
    return 0
  fi

  if [[ "${PROJECT_NAME}" != "osemosys-backend" ]]; then
    return 0
  fi

  log "Detectadas variables heredadas del despliegue backend-only; usando defaults del monorepo unificado"
  PROJECT_NAME="osemosys"
  export COMPOSE_PROJECT_NAME="${PROJECT_NAME}"
  FRONTEND_PORT=80
  FRONTEND_BIND_HOST=0.0.0.0
  FRONTEND_API_UPSTREAM=api:8000
  API_PORT=8010
  API_BIND_HOST=127.0.0.1
  POSTGRES_PORT=5433
  POSTGRES_BIND_HOST=127.0.0.1
  REDIS_PORT=6379
  REDIS_BIND_HOST=127.0.0.1
  BACKEND_BRIDGE_NETWORK="${BACKEND_BRIDGE_NETWORK:-osemosys_api_bridge}"
}

require_cmd docker
require_cmd ss
require_cmd sed
require_cmd grep
require_cmd awk
require_cmd curl
require_cmd gzip
require_cmd seq

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose no está disponible (docker compose)." >&2
  exit 1
fi

cd "${REPO_ROOT}"

log_git_revision
log "Preparando archivos .env"
copy_env_template_if_missing .env .env.example
copy_env_template_if_missing backend/.env backend/.env.example backend/.env.local.example

FRONTEND_PORT="${FRONTEND_PORT:-80}"
API_PORT="${API_PORT:-8010}"
API_WORKERS="${API_WORKERS:-3}"
REDIS_PORT="${REDIS_PORT:-6379}"
POSTGRES_PORT="${POSTGRES_PORT:-}"
API_BIND_HOST="${API_BIND_HOST:-127.0.0.1}"
FRONTEND_BIND_HOST="${FRONTEND_BIND_HOST:-0.0.0.0}"
POSTGRES_BIND_HOST="${POSTGRES_BIND_HOST:-127.0.0.1}"
REDIS_BIND_HOST="${REDIS_BIND_HOST:-127.0.0.1}"
BACKEND_BRIDGE_NETWORK="${BACKEND_BRIDGE_NETWORK:-osemosys_api_bridge}"
FRONTEND_API_UPSTREAM="${FRONTEND_API_UPSTREAM:-api:8000}"
APP_USERS="${APP_USERS:-lcardona,jchavez,dbedoya}"
APP_PASSWORD="${APP_PASSWORD:-Cambio123!}"
SECRET_KEY="${SECRET_KEY:-}"
APP_ADMIN_USERS="${APP_ADMIN_USERS:-$APP_USERS}"
BACKUP_BEFORE_MIGRATIONS="${BACKUP_BEFORE_MIGRATIONS:-1}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
RUN_SEED="${RUN_SEED:-1}"
SYNC_APP_USERS="${SYNC_APP_USERS:-1}"
SIM_WORKER_REPLICAS="${SIM_WORKER_REPLICAS:-1}"
SIM_MAX_CONCURRENCY="${SIM_MAX_CONCURRENCY:-1}"
SIM_USER_ACTIVE_LIMIT="${SIM_USER_ACTIVE_LIMIT:-3}"
SIM_TOTAL_WEIGHT_LIMIT="${SIM_TOTAL_WEIGHT_LIMIT:-8}"
SIM_WEIGHT_NATIONAL="${SIM_WEIGHT_NATIONAL:-1}"
SIM_WEIGHT_REGIONAL="${SIM_WEIGHT_REGIONAL:-3}"
SIM_SOLVER_THREADS="${SIM_SOLVER_THREADS:-0}"
SIM_SOLVER_HIGHS_DIRECT="${SIM_SOLVER_HIGHS_DIRECT:-true}"
HIGHS_BUILD_FROM_SOURCE="${HIGHS_BUILD_FROM_SOURCE:-0}"
HIGHS_GIT_REF="${HIGHS_GIT_REF:-master}"
HIGHS_ENABLE_HIPO="${HIGHS_ENABLE_HIPO:-0}"
OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-4}"
MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"
VITE_API_BASE_URL="${VITE_API_BASE_URL:-/api/v1}"
VITE_APP_ENV="${VITE_APP_ENV:-production}"
VITE_SIMULATION_MODE="${VITE_SIMULATION_MODE:-api}"
APP_GIT_SHA="${APP_GIT_SHA:-$(git rev-parse HEAD 2>/dev/null || true)}"
APP_GIT_BRANCH="${APP_GIT_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)}"
APP_DEPLOY_ENV="${APP_DEPLOY_ENV:-${VITE_APP_ENV}}"

if [[ -z "${POSTGRES_PORT}" ]]; then
  if is_port_in_use 5432; then
    POSTGRES_PORT=5433
  else
    POSTGRES_PORT=5432
  fi
fi

normalize_unified_monorepo_env

require_non_default_secret_key "${SECRET_KEY}"
ensure_external_network "${BACKEND_BRIDGE_NETWORK}"

upsert_env_key .env FRONTEND_PORT "${FRONTEND_PORT}"
upsert_env_key .env API_PORT "${API_PORT}"
upsert_env_key .env API_WORKERS "${API_WORKERS}"
upsert_env_key .env REDIS_PORT "${REDIS_PORT}"
upsert_env_key .env POSTGRES_PORT "${POSTGRES_PORT}"
upsert_env_key .env API_BIND_HOST "${API_BIND_HOST}"
upsert_env_key .env FRONTEND_BIND_HOST "${FRONTEND_BIND_HOST}"
upsert_env_key .env POSTGRES_BIND_HOST "${POSTGRES_BIND_HOST}"
upsert_env_key .env REDIS_BIND_HOST "${REDIS_BIND_HOST}"
upsert_env_key .env BACKEND_BRIDGE_NETWORK "${BACKEND_BRIDGE_NETWORK}"
upsert_env_key .env FRONTEND_API_UPSTREAM "${FRONTEND_API_UPSTREAM}"
upsert_env_key .env SIM_WORKER_REPLICAS "${SIM_WORKER_REPLICAS}"
upsert_env_key .env SIM_MAX_CONCURRENCY "${SIM_MAX_CONCURRENCY}"
upsert_env_key .env SIM_USER_ACTIVE_LIMIT "${SIM_USER_ACTIVE_LIMIT}"
upsert_env_key .env SIM_TOTAL_WEIGHT_LIMIT "${SIM_TOTAL_WEIGHT_LIMIT}"
upsert_env_key .env SIM_WEIGHT_NATIONAL "${SIM_WEIGHT_NATIONAL}"
upsert_env_key .env SIM_WEIGHT_REGIONAL "${SIM_WEIGHT_REGIONAL}"
upsert_env_key .env SIM_SOLVER_THREADS "${SIM_SOLVER_THREADS}"
upsert_env_key .env SIM_SOLVER_HIGHS_DIRECT "${SIM_SOLVER_HIGHS_DIRECT}"
upsert_env_key .env HIGHS_BUILD_FROM_SOURCE "${HIGHS_BUILD_FROM_SOURCE}"
upsert_env_key .env HIGHS_GIT_REF "${HIGHS_GIT_REF}"
upsert_env_key .env HIGHS_ENABLE_HIPO "${HIGHS_ENABLE_HIPO}"
upsert_env_key .env OMP_NUM_THREADS "${OMP_NUM_THREADS}"
upsert_env_key .env OPENBLAS_NUM_THREADS "${OPENBLAS_NUM_THREADS}"
upsert_env_key .env MKL_NUM_THREADS "${MKL_NUM_THREADS}"
upsert_env_key .env APP_GIT_SHA "${APP_GIT_SHA}"
upsert_env_key .env APP_GIT_BRANCH "${APP_GIT_BRANCH}"
upsert_env_key .env APP_DEPLOY_ENV "${APP_DEPLOY_ENV}"
upsert_env_key .env VITE_API_BASE_URL "${VITE_API_BASE_URL}"
upsert_env_key .env VITE_APP_ENV "${VITE_APP_ENV}"
upsert_env_key .env VITE_SIMULATION_MODE "${VITE_SIMULATION_MODE}"
upsert_env_key backend/.env SECRET_KEY "${SECRET_KEY}"
upsert_env_key backend/.env SIM_WORKER_REPLICAS "${SIM_WORKER_REPLICAS}"
upsert_env_key backend/.env SIM_MAX_CONCURRENCY "${SIM_MAX_CONCURRENCY}"
upsert_env_key backend/.env SIM_USER_ACTIVE_LIMIT "${SIM_USER_ACTIVE_LIMIT}"
upsert_env_key backend/.env SIM_TOTAL_WEIGHT_LIMIT "${SIM_TOTAL_WEIGHT_LIMIT}"
upsert_env_key backend/.env SIM_WEIGHT_NATIONAL "${SIM_WEIGHT_NATIONAL}"
upsert_env_key backend/.env SIM_WEIGHT_REGIONAL "${SIM_WEIGHT_REGIONAL}"
upsert_env_key backend/.env SIM_SOLVER_THREADS "${SIM_SOLVER_THREADS}"
upsert_env_key backend/.env SIM_SOLVER_HIGHS_DIRECT "${SIM_SOLVER_HIGHS_DIRECT}"
upsert_env_key backend/.env HIGHS_BUILD_FROM_SOURCE "${HIGHS_BUILD_FROM_SOURCE}"
upsert_env_key backend/.env HIGHS_GIT_REF "${HIGHS_GIT_REF}"
upsert_env_key backend/.env HIGHS_ENABLE_HIPO "${HIGHS_ENABLE_HIPO}"
upsert_env_key backend/.env OMP_NUM_THREADS "${OMP_NUM_THREADS}"
upsert_env_key backend/.env OPENBLAS_NUM_THREADS "${OPENBLAS_NUM_THREADS}"
upsert_env_key backend/.env MKL_NUM_THREADS "${MKL_NUM_THREADS}"
upsert_env_key backend/.env APP_GIT_SHA "${APP_GIT_SHA}"
upsert_env_key backend/.env APP_GIT_BRANCH "${APP_GIT_BRANCH}"
upsert_env_key backend/.env APP_DEPLOY_ENV "${APP_DEPLOY_ENV}"

capture_previous_images

log "Construyendo imágenes Docker"
docker compose build api simulation-worker frontend

log "Levantando dependencias base (db + redis)"
docker compose up -d db redis

log "Esperando PostgreSQL"
if ! wait_db_healthy 60 2; then
  echo "PostgreSQL no quedó listo en el tiempo esperado." >&2
  exit 1
fi

if [[ "${BACKUP_BEFORE_MIGRATIONS}" == "1" ]]; then
  BACKUP_DIR="$(ensure_writable_backup_dir "${BACKUP_DIR}")"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  LAST_BACKUP_FILE="${BACKUP_DIR}/osemosys_${timestamp}.sql.gz"
  log "Generando backup de base de datos en ${LAST_BACKUP_FILE}"
  docker compose exec -T db sh -lc 'pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"' | gzip -c > "${LAST_BACKUP_FILE}"
  if [[ "${BACKUP_RETENTION_DAYS}" =~ ^[0-9]+$ ]]; then
    find "${BACKUP_DIR}" -type f -name 'osemosys_*.sql.gz' -mtime +"${BACKUP_RETENTION_DAYS}" -delete || true
  fi
fi

log "Ejecutando migraciones Alembic (antes de levantar API)"
docker compose run --rm --no-deps api alembic upgrade head

log "Levantando stack completo (workers=${SIM_WORKER_REPLICAS})"
docker compose up -d --scale "simulation-worker=${SIM_WORKER_REPLICAS}"

# Forzar recreación de simulation-worker para evitar mounts stale del bind
# secrets/gurobi.lic. Si el contenedor anterior arrancó cuando ese path era
# un directorio fantasma (autocreado por Docker), `compose up` no recrearía
# el contenedor porque el yaml no cambió y compose no audita el tipo del
# source. Esto garantiza que el mount de la licencia siempre refleje el
# estado actual del host.
log "Forzando recreación de simulation-worker para refrescar bind mounts"
docker compose up -d --force-recreate --no-deps \
  --scale "simulation-worker=${SIM_WORKER_REPLICAS}" simulation-worker

log "Esperando a que API esté disponible (/api/v1/health)"
if ! wait_http_ok "http://127.0.0.1:${API_PORT}/api/v1/health" 60 2; then
  echo "La API no respondió en el tiempo esperado." >&2
  exit 1
fi

if [[ "${RUN_SEED}" == "1" ]]; then
  log "Ejecutando seed"
  docker compose exec -T api python scripts/seed.py
fi

if [[ "${SYNC_APP_USERS}" == "1" ]]; then
  log "Creando/actualizando usuarios de aplicación"
  docker compose exec -T \
    -e APP_USERS="${APP_USERS}" \
    -e APP_PASSWORD="${APP_PASSWORD}" \
    -e APP_ADMIN_USERS="${APP_ADMIN_USERS}" \
    api python - <<'PY'
import os
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import User
from app.core.security import get_password_hash

users = [u.strip() for u in os.getenv("APP_USERS", "").split(",") if u.strip()]
password = os.getenv("APP_PASSWORD", "Cambio123!")
admin_users = [u.strip() for u in os.getenv("APP_ADMIN_USERS", "").split(",") if u.strip()]
admin_set = set(admin_users)

if not users:
    raise SystemExit("APP_USERS está vacío")

with SessionLocal() as s:
    for username in users:
        is_admin = username in admin_set
        user = s.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user is None:
            user = User(
                email=f"{username}@local",
                username=username,
                hashed_password=get_password_hash(password),
                is_active=True,
                can_manage_catalogs=is_admin,
                can_import_official_data=is_admin,
                can_manage_users=is_admin,
            )
            s.add(user)
            print(f"creado: {username} (admin={is_admin})")
        else:
            user.email = f"{username}@local"
            user.hashed_password = get_password_hash(password)
            user.is_active = True
            user.can_manage_catalogs = is_admin
            user.can_import_official_data = is_admin
            user.can_manage_users = is_admin
            print(f"actualizado: {username} (admin={is_admin})")

    for username in sorted(admin_set - set(users)):
        user = s.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user is None:
            print(f"admin_no_encontrado: {username}")
            continue
        user.is_active = True
        user.can_manage_catalogs = True
        user.can_import_official_data = True
        user.can_manage_users = True
        print(f"admin_promovido: {username}")
    s.commit()

print("password_default=configured via secure variable")
print(f"admin_users={','.join(admin_users) if admin_users else '(ninguno)'}")
PY
else
  log "Omitiendo sincronización de usuarios de aplicación (SYNC_APP_USERS=0)"
fi

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -z "${HOST_IP}" ]]; then
  HOST_IP="$(ip route get 1 2>/dev/null | awk '{print $7; exit}')"
fi

log "Estado final del stack"
docker compose ps

log "Smoke test de salud API"
if ! wait_http_ok "http://127.0.0.1:${FRONTEND_PORT}/api/v1/health" 30 2; then
  echo "Smoke test falló: /api/v1/health no respondió OK." >&2
  exit 1
fi

log "Smoke test de readiness API"
if ! wait_http_ok "http://127.0.0.1:${FRONTEND_PORT}/api/v1/health/ready" 30 2; then
  echo "Smoke test falló: /api/v1/health/ready no respondió OK." >&2
  exit 1
fi

log "Smoke test de conectividad Celery"
if ! wait_celery_ping 30 2; then
  echo "Smoke test falló: celery inspect ping no respondió." >&2
  exit 1
fi

echo
echo "Despliegue listo."
echo "Frontend LAN: http://${HOST_IP:-<IP_MAQUINA>}:${FRONTEND_PORT}"
echo "Health API via frontend: http://${HOST_IP:-<IP_MAQUINA>}:${FRONTEND_PORT}/api/v1/health"
echo "Readiness API via frontend: http://${HOST_IP:-<IP_MAQUINA>}:${FRONTEND_PORT}/api/v1/health/ready"
echo "Swagger local API: http://127.0.0.1:${API_PORT}/docs"
echo "Usuarios: ${APP_USERS}"
echo "Usuarios admin: ${APP_ADMIN_USERS}"
echo "Workers simulación: ${SIM_WORKER_REPLICAS} (concurrency=${SIM_MAX_CONCURRENCY})"
echo
echo "Si usas firewall para staging, habilita solo ${FRONTEND_PORT}/tcp."
