#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"

POSTGRES_PORT="${POSTGRES_PORT:-55432}"
RUN_BACKEND_TESTS="${RUN_BACKEND_TESTS:-1}"
RUN_FRONTEND_TYPECHECK="${RUN_FRONTEND_TYPECHECK:-1}"

log() {
  printf '\n==> %s\n' "$*"
}

run_root_compose_config() {
  log "Validando docker-compose.yml raiz"
  (cd "${ROOT_DIR}" && docker compose config -q)
}

run_backend_compose_config() {
  log "Validando backend/docker-compose.yml"
  (cd "${BACKEND_DIR}" && POSTGRES_PORT="${POSTGRES_PORT}" docker compose config -q)
}

run_py_compile() {
  log "Compilando modulos Python modificados con py_compile"
  local files=(
    backend/app/api/v1/system_settings.py \
    backend/app/schemas/system_setting.py \
    backend/app/services/simulation_service.py \
    backend/app/simulation/core/solver.py \
    backend/app/simulation/core/solver_config.py \
    backend/tests/test_system_settings.py \
    backend/tests/test_solver_config.py \
    backend/tests/test_simulation_service_submit.py
  )
  local existing=()
  local file
  for file in "${files[@]}"; do
    if [[ -f "${ROOT_DIR}/${file}" ]]; then
      existing+=("${file}")
    fi
  done
  (cd "${ROOT_DIR}" && python3 -m py_compile "${existing[@]}")
}

run_highs_runtime_check() {
  log "Validando runtime Python de HiGHS"
  (cd "${BACKEND_DIR}" && python3 - <<'PY'
import highspy
import pyomo.environ as pyo

solver = pyo.SolverFactory("appsi_highs")
if solver is None or not solver.available(exception_flag=False):
    raise SystemExit("appsi_highs no esta disponible para Pyomo")

h = highspy.Highs()
status = h.setOptionValue("solver", "ipm")
text = str(status)
if "kError" in text or text.endswith("Error"):
    raise SystemExit(f"highspy rechazo solver=ipm: {status}")

print("highspy/appsi_highs OK")
PY
  )
}

run_frontend_typecheck() {
  if [[ "${RUN_FRONTEND_TYPECHECK}" != "1" ]]; then
    log "Saltando frontend typecheck (RUN_FRONTEND_TYPECHECK=${RUN_FRONTEND_TYPECHECK})"
    return
  fi
  log "Ejecutando frontend typecheck"
  (cd "${FRONTEND_DIR}" && npm run typecheck)
}

run_backend_tests() {
  if [[ "${RUN_BACKEND_TESTS}" != "1" ]]; then
    log "Saltando backend tests (RUN_BACKEND_TESTS=${RUN_BACKEND_TESTS})"
    return
  fi

  log "Levantando db/redis para tests backend"
  (cd "${BACKEND_DIR}" && POSTGRES_PORT="${POSTGRES_PORT}" docker compose up -d db redis)

  log "Ejecutando tests backend enfocados"
  local tests=(
    tests/test_system_settings.py
    tests/test_solver_config.py
    tests/test_simulation_service_submit.py
  )
  local existing_tests=()
  local test_file
  for test_file in "${tests[@]}"; do
    if [[ -f "${BACKEND_DIR}/${test_file}" ]]; then
      existing_tests+=("${test_file}")
    fi
  done
  (cd "${BACKEND_DIR}" && POSTGRES_PORT="${POSTGRES_PORT}" docker compose run --rm \
    -v "${BACKEND_DIR}:/app" \
    api python -m pytest "${existing_tests[@]}" -q)
}

run_root_compose_config
run_backend_compose_config
run_py_compile
run_highs_runtime_check
run_frontend_typecheck
run_backend_tests

log "Validaciones completadas"
