#!/usr/bin/env bash
set -euo pipefail

# Despliegue rápido local/LAN del backend OSeMOSYS usando Docker Compose.
# - Expone el API por el puerto configurado
# - Ejecuta migraciones y seed
# - Crea/actualiza usuarios de aplicación
#
# Uso:
#   chmod +x backend/scripts/deploy-local.sh
#   ./backend/scripts/deploy-local.sh
#
# Variables opcionales:
#   API_BIND_HOST=127.0.0.1
#   API_PORT=18010
#   API_WORKERS=3
#   BACKEND_BRIDGE_NETWORK=osemosys_api_bridge
#   BACKEND_API_ALIAS=osemosys-backend-api
#   REDIS_BIND_HOST=127.0.0.1
#   REDIS_PORT=6380
#   POSTGRES_BIND_HOST=127.0.0.1
#   POSTGRES_PORT=5432 (si está ocupado, el script usa 5433 por defecto)
#   APP_USERS="lcardona,jchavez,dbedoya"
#   APP_PASSWORD="Cambio123!"
#   SECRET_KEY="valor-largo-y-aleatorio"
#   APP_ADMIN_USERS="lcardona,jchavez,dbedoya" (por defecto usa APP_USERS)
#   BACKUP_BEFORE_MIGRATIONS=1 (1=habilitado, 0=deshabilitado)
#   BACKUP_DIR=/ruta/backups
#   BACKUP_RETENTION_DAYS=7
#   RUN_SEED=1 (1=ejecuta seed, 0=omite seed)
#   SIM_WORKER_REPLICAS=2
#   SIM_MAX_CONCURRENCY=2
#   SIM_USER_ACTIVE_LIMIT=4

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${APP_ROOT}/.." && pwd)"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-osemosys-backend}"
export COMPOSE_PROJECT_NAME="${PROJECT_NAME}"
LAST_BACKUP_FILE=""
PREV_API_IMAGE_ID=""
PREV_WORKER_IMAGE_ID=""

capture_previous_images() {
  PREV_API_IMAGE_ID="$(docker compose images -q api 2>/dev/null || true)"
  PREV_WORKER_IMAGE_ID="$(docker compose images -q simulation-worker 2>/dev/null || true)"
}

rollback_previous_images() {
  if [[ -z "${PREV_API_IMAGE_ID}" && -z "${PREV_WORKER_IMAGE_ID}" ]]; then
    return 0
  fi

  log "Intentando rollback operativo a imágenes previas"
  [[ -n "${PREV_API_IMAGE_ID}" ]] && docker image tag "${PREV_API_IMAGE_ID}" "${PROJECT_NAME}-api" || true
  [[ -n "${PREV_WORKER_IMAGE_ID}" ]] && docker image tag "${PREV_WORKER_IMAGE_ID}" "${PROJECT_NAME}-simulation-worker" || true

  docker compose up -d --no-build --scale "simulation-worker=${SIM_WORKER_REPLICAS:-2}" || true
}

log() {
  printf "\n[%s] %s\n" "$(date +'%H:%M:%S')" "$*"
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

cd "$APP_ROOT"

log "Preparando archivo .env"
copy_env_template_if_missing .env .env.example .env.local.example

API_PORT="${API_PORT:-18010}"
API_WORKERS="${API_WORKERS:-3}"
REDIS_PORT="${REDIS_PORT:-6380}"
POSTGRES_PORT="${POSTGRES_PORT:-}"
API_BIND_HOST="${API_BIND_HOST:-127.0.0.1}"
POSTGRES_BIND_HOST="${POSTGRES_BIND_HOST:-127.0.0.1}"
REDIS_BIND_HOST="${REDIS_BIND_HOST:-127.0.0.1}"
BACKEND_BRIDGE_NETWORK="${BACKEND_BRIDGE_NETWORK:-osemosys_api_bridge}"
APP_USERS="${APP_USERS:-lcardona,jchavez,dbedoya}"
APP_PASSWORD="${APP_PASSWORD:-Cambio123!}"
SECRET_KEY="${SECRET_KEY:-}"
APP_ADMIN_USERS="${APP_ADMIN_USERS:-$APP_USERS}"
BACKUP_BEFORE_MIGRATIONS="${BACKUP_BEFORE_MIGRATIONS:-1}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
RUN_SEED="${RUN_SEED:-1}"
SIM_WORKER_REPLICAS="${SIM_WORKER_REPLICAS:-2}"
SIM_MAX_CONCURRENCY="${SIM_MAX_CONCURRENCY:-2}"
SIM_USER_ACTIVE_LIMIT="${SIM_USER_ACTIVE_LIMIT:-4}"
SIM_TOTAL_WEIGHT_LIMIT="${SIM_TOTAL_WEIGHT_LIMIT:-8}"
SIM_WEIGHT_NATIONAL="${SIM_WEIGHT_NATIONAL:-1}"
SIM_WEIGHT_REGIONAL="${SIM_WEIGHT_REGIONAL:-3}"
SIM_SOLVER_THREADS="${SIM_SOLVER_THREADS:-12}"
SIM_SOLVER_HIGHS_METHOD="${SIM_SOLVER_HIGHS_METHOD:-ipm}"
SIM_SOLVER_HIGHS_PRESOLVE="${SIM_SOLVER_HIGHS_PRESOLVE:-on}"
SIM_SOLVER_HIGHS_PARALLEL="${SIM_SOLVER_HIGHS_PARALLEL:-on}"
SIM_SOLVER_HIGHS_HIPO_PARALLEL_TYPE="${SIM_SOLVER_HIGHS_HIPO_PARALLEL_TYPE:-}"
SIM_SOLVER_HIGHS_CROSSOVER="${SIM_SOLVER_HIGHS_CROSSOVER:-choose}"
SIM_SOLVER_HIGHS_DIRECT="${SIM_SOLVER_HIGHS_DIRECT:-true}"
SIM_SOLVER_HIGHS_TIME_LIMIT="${SIM_SOLVER_HIGHS_TIME_LIMIT:-0}"
SIM_SOLVER_HIGHS_IPM_TOL="${SIM_SOLVER_HIGHS_IPM_TOL:-1e-7}"
SIM_SOLVER_HIGHS_PRIMAL_TOL="${SIM_SOLVER_HIGHS_PRIMAL_TOL:-1e-7}"
HIGHS_BUILD_FROM_SOURCE="${HIGHS_BUILD_FROM_SOURCE:-0}"
HIGHS_GIT_REF="${HIGHS_GIT_REF:-master}"
HIGHS_ENABLE_HIPO="${HIGHS_ENABLE_HIPO:-0}"

if [[ -z "${POSTGRES_PORT}" ]]; then
  if is_port_in_use 5432; then
    POSTGRES_PORT=5433
  else
    POSTGRES_PORT=5432
  fi
fi

require_non_default_secret_key "${SECRET_KEY}"
ensure_external_network "${BACKEND_BRIDGE_NETWORK}"

upsert_env_key .env API_PORT "${API_PORT}"
upsert_env_key .env API_WORKERS "${API_WORKERS}"
upsert_env_key .env REDIS_PORT "${REDIS_PORT}"
upsert_env_key .env POSTGRES_PORT "${POSTGRES_PORT}"
upsert_env_key .env API_BIND_HOST "${API_BIND_HOST}"
upsert_env_key .env POSTGRES_BIND_HOST "${POSTGRES_BIND_HOST}"
upsert_env_key .env REDIS_BIND_HOST "${REDIS_BIND_HOST}"
upsert_env_key .env SECRET_KEY "${SECRET_KEY}"
upsert_env_key .env SIM_WORKER_REPLICAS "${SIM_WORKER_REPLICAS}"
upsert_env_key .env SIM_MAX_CONCURRENCY "${SIM_MAX_CONCURRENCY}"
upsert_env_key .env SIM_USER_ACTIVE_LIMIT "${SIM_USER_ACTIVE_LIMIT}"
upsert_env_key .env SIM_TOTAL_WEIGHT_LIMIT "${SIM_TOTAL_WEIGHT_LIMIT}"
upsert_env_key .env SIM_WEIGHT_NATIONAL "${SIM_WEIGHT_NATIONAL}"
upsert_env_key .env SIM_WEIGHT_REGIONAL "${SIM_WEIGHT_REGIONAL}"
upsert_env_key .env SIM_SOLVER_THREADS "${SIM_SOLVER_THREADS}"
upsert_env_key .env SIM_SOLVER_HIGHS_METHOD "${SIM_SOLVER_HIGHS_METHOD}"
upsert_env_key .env SIM_SOLVER_HIGHS_PRESOLVE "${SIM_SOLVER_HIGHS_PRESOLVE}"
upsert_env_key .env SIM_SOLVER_HIGHS_PARALLEL "${SIM_SOLVER_HIGHS_PARALLEL}"
upsert_env_key .env SIM_SOLVER_HIGHS_HIPO_PARALLEL_TYPE "${SIM_SOLVER_HIGHS_HIPO_PARALLEL_TYPE}"
upsert_env_key .env SIM_SOLVER_HIGHS_CROSSOVER "${SIM_SOLVER_HIGHS_CROSSOVER}"
upsert_env_key .env SIM_SOLVER_HIGHS_DIRECT "${SIM_SOLVER_HIGHS_DIRECT}"
upsert_env_key .env SIM_SOLVER_HIGHS_TIME_LIMIT "${SIM_SOLVER_HIGHS_TIME_LIMIT}"
upsert_env_key .env SIM_SOLVER_HIGHS_IPM_TOL "${SIM_SOLVER_HIGHS_IPM_TOL}"
upsert_env_key .env SIM_SOLVER_HIGHS_PRIMAL_TOL "${SIM_SOLVER_HIGHS_PRIMAL_TOL}"
upsert_env_key .env HIGHS_BUILD_FROM_SOURCE "${HIGHS_BUILD_FROM_SOURCE}"
upsert_env_key .env HIGHS_GIT_REF "${HIGHS_GIT_REF}"
upsert_env_key .env HIGHS_ENABLE_HIPO "${HIGHS_ENABLE_HIPO}"

capture_previous_images

log "Levantando stack con Docker Compose (build + up, workers=${SIM_WORKER_REPLICAS})"
docker compose up -d --build --scale "simulation-worker=${SIM_WORKER_REPLICAS}"

log "Esperando a que API esté disponible (/api/v1/health)"
if ! wait_http_ok "http://127.0.0.1:${API_PORT}/api/v1/health" 60 2; then
  echo "La API no respondió en el tiempo esperado." >&2
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

log "Ejecutando migraciones y seed"
docker compose exec -T api alembic upgrade head
if [[ "${RUN_SEED}" == "1" ]]; then
  docker compose exec -T api python scripts/seed.py
fi

log "Creando/actualizando usuarios de aplicación"
docker compose exec -T \
  -e APP_USERS="$APP_USERS" \
  -e APP_PASSWORD="$APP_PASSWORD" \
  -e APP_ADMIN_USERS="$APP_ADMIN_USERS" \
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

print(f"admin_users={','.join(admin_users) if admin_users else '(ninguno)'}")
PY

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -z "${HOST_IP}" ]]; then
  HOST_IP="$(ip route get 1 2>/dev/null | awk '{print $7; exit}')"
fi

log "Estado final del stack"
docker compose ps

log "Smoke test de salud API"
if ! wait_http_ok "http://127.0.0.1:${API_PORT}/api/v1/health" 30 2; then
  echo "Smoke test falló: /api/v1/health no respondió OK." >&2
  exit 1
fi

log "Smoke test de readiness API"
if ! wait_http_ok "http://127.0.0.1:${API_PORT}/api/v1/health/ready" 30 2; then
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
echo "API LAN: http://${HOST_IP:-<IP_MAQUINA>}:${API_PORT}"
echo "Health API: http://${HOST_IP:-<IP_MAQUINA>}:${API_PORT}/api/v1/health"
echo "Readiness API: http://${HOST_IP:-<IP_MAQUINA>}:${API_PORT}/api/v1/health/ready"
echo "Swagger API: http://${HOST_IP:-<IP_MAQUINA>}:${API_PORT}/docs"
echo "Usuarios: ${APP_USERS}"
echo "Usuarios admin: ${APP_ADMIN_USERS}"
echo "Password inicial: configurado por variable segura"
echo "Workers simulación: ${SIM_WORKER_REPLICAS} (concurrency=${SIM_MAX_CONCURRENCY})"
echo
echo "Si usas firewall, permite puerto ${API_PORT}/tcp (ej: sudo ufw allow ${API_PORT}/tcp)."
