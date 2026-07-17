# Configuración del Environment `production` en GitHub

Fecha de referencia: 2026-07-16  
Repositorio: `UPME-SubDemanda/Osemosys_UPME`  
Environment: `production`

Este documento define las variables y secretos que deben existir en **Settings → Environments → production**, los valores operativos certificados para el solver y la lista de verificaciones necesarias antes y después de desplegar `main`.

## 1. Capacidad prevista

La configuración parte de un host con **39 GiB de RAM y 24 núcleos lógicos**, compartido con staging.

- Staging: 1 réplica Celery × concurrencia 1.
- Producción: 2 réplicas Celery × concurrencia 1.
- Peso nacional: 1.
- Peso regional: 3.
- Límite ponderado de producción: 3.

Con esta combinación, producción puede ejecutar:

- una simulación regional; o
- hasta dos simulaciones nacionales simultáneas.

El límite ponderado evita admitir dos regionales simultáneas en producción. Staging puede ejecutar adicionalmente una simulación. Dos regionales, una por ambiente, consumen aproximadamente 22–25 GiB según las mediciones certificadas, dejando margen para PostgreSQL, Redis, API, frontend y sistema operativo.

HiGHS simplex no mostró una mejora material al aumentar los hilos; por eso `SIM_SOLVER_THREADS=0` deja el manejo de hilos en el default validado y evita reservar 24 hilos por proceso.

## 2. Variables de infraestructura

| Variable | Valor de producción | Acción / nota |
|---|---:|---|
| `COMPOSE_PROJECT_NAME` | `osemosys` | Validar. Identifica el stack productivo. |
| `FRONTEND_BIND_HOST` | `0.0.0.0` | Validar. |
| `FRONTEND_PORT` | `80` | Validar. |
| `FRONTEND_API_UPSTREAM` | `api:8000` | Validar. |
| `BACKEND_BRIDGE_NETWORK` | `osemosys_api_bridge` | Validar que la red externa exista. |
| `API_BIND_HOST` | `127.0.0.1` | Validar. |
| `API_PORT` | `8010` | Validar. |
| `API_WORKERS` | `2` | Valor recomendado para el host actual. |
| `POSTGRES_BIND_HOST` | `127.0.0.1` | Validar. |
| `POSTGRES_PORT` | `5433` | Validar. |
| `REDIS_BIND_HOST` | `127.0.0.1` | Validar. |
| `REDIS_PORT` | `6379` | Validar. |
| `RUN_SEED` | `0` | Evita ejecutar el seed en cada deploy productivo. |
| `SYNC_APP_USERS` | `0` | Conserva usuarios gestionados en la aplicación. |
| `VITE_API_BASE_URL` | `/api/v1` | Validar. |
| `VITE_APP_ENV` | `production` | Validar. |
| `VITE_SIMULATION_MODE` | `api` | Validar. |
| `SIMULATION_OPS_ENVIRONMENT_NAME` | `prod` | Validar. |

`APP_USERS` y `APP_ADMIN_USERS` pueden conservar sus listas actuales. Con `SYNC_APP_USERS=0` no se recrean usuarios durante cada despliegue.

`BACKEND_API_ALIAS` es una variable heredada; no es necesaria para el flujo Compose actual y no debe usarse como sustituto de `FRONTEND_API_UPSTREAM`.

## 3. Backup previo a migraciones

Crear y validar explícitamente:

| Variable | Valor recomendado | Acción / nota |
|---|---:|---|
| `BACKUP_BEFORE_MIGRATIONS` | `1` | Obliga a respaldar antes de Alembic. |
| `BACKUP_DIR` | `/home/procesa01/osemosys-backups/production` | El directorio debe existir y ser escribible por el runner. |
| `BACKUP_RETENTION_DAYS` | `14` | Retención operativa recomendada. |

Preparación en el host:

```bash
mkdir -p /home/procesa01/osemosys-backups/production
chmod 700 /home/procesa01/osemosys-backups/production
test -w /home/procesa01/osemosys-backups/production && echo BACKUP_DIR_OK
```

No desplegar si el log indica que no pudo usar ni `BACKUP_DIR` ni su fallback.

## 4. Capacidad de simulación

| Variable | Valor | Motivo |
|---|---:|---|
| `SIM_WORKER_REPLICAS` | `2` | Dos slots productivos independientes. |
| `SIM_MAX_CONCURRENCY` | `1` | Un proceso de solver por réplica Celery. |
| `SIM_USER_ACTIVE_LIMIT` | `3` | Permite cola controlada por usuario. |
| `SIM_TOTAL_WEIGHT_LIMIT` | `3` | Una regional o hasta tres nacionales admitidas; sólo dos ejecutan por los dos workers. |
| `SIM_WEIGHT_NATIONAL` | `1` | Peso operativo validado. |
| `SIM_WEIGHT_REGIONAL` | `3` | Impide dos regionales simultáneas en el mismo ambiente. |

El límite ponderado es por ambiente. Staging y producción usan bases/colas separadas y no coordinan entre sí; el margen global depende de mantener staging en una sola réplica con concurrencia 1.

## 5. Solver

### 5.1 HiGHS

| Variable | Valor |
|---|---:|
| `SIM_SOLVER_THREADS` | `0` |
| `SIM_SOLVER_PROFILE` | `default` |
| `SIM_SOLVER_HIGHS_DIRECT` | `true` |
| `SIM_SOLVER_HIGHS_TIME_LIMIT` | `0` |
| `SIM_SOLVER_HIGHS_IPM_TOL` | `1e-7` |
| `SIM_SOLVER_HIGHS_PRIMAL_TOL` | `1e-7` |
| `SIM_SOLVER_HIGHS_DUAL_TOL` | `1e-7` |

Las siguientes variables deben permanecer **ausentes** en GitHub, para no forzar opciones experimentales:

- `SIM_SOLVER_HIGHS_METHOD`
- `SIM_SOLVER_HIGHS_PRESOLVE`
- `SIM_SOLVER_HIGHS_PARALLEL`
- `SIM_SOLVER_HIGHS_HIPO_PARALLEL_TYPE`
- `SIM_SOLVER_HIGHS_CROSSOVER`
- `SIM_SOLVER_HIGHS_OPTIONS_JSON`

No configurar `method=ipm`, `parallel=on`, HiPO ni crossover. El perfil certificado usa `default` con esos campos vacíos.

### 5.2 GLPK

| Variable | Valor |
|---|---:|
| `SIM_SOLVER_GLPK_PROFILE` | `fast` |
| `SIM_SOLVER_GLPK_TIME_LIMIT` | `0` |

`SIM_SOLVER_GLPK_OPTIONS_JSON` debe permanecer ausente salvo una prueba controlada. `strict` se conserva únicamente como perfil diagnóstico; no es el perfil operativo.

### 5.3 Construcción de HiGHS y BLAS

| Variable | Valor |
|---|---:|
| `HIGHS_BUILD_FROM_SOURCE` | `0` |
| `HIGHS_GIT_REF` | `master` |
| `HIGHS_ENABLE_HIPO` | `0` |
| `OMP_NUM_THREADS` | `4` |
| `OPENBLAS_NUM_THREADS` | `4` |
| `MKL_NUM_THREADS` | `4` |

`HIGHS_GIT_REF` queda registrado por trazabilidad, aunque no se usa mientras `HIGHS_BUILD_FROM_SOURCE=0`.

## 6. Preprocesamiento y memoria

| Variable | Valor | Motivo |
|---|---:|---|
| `OSEMOSYS_FAST_DATAPORTAL` | `1` | Carga optimizada de CSV a Pyomo. |
| `OSEMOSYS_ACTIVITY_LOWER_PRUNE_TOL` | `0.001` | Paridad certificada con notebook; elimina mínimos históricos numéricamente pequeños. |
| `OSEMOSYS_SPARSE_MATRIX_PREPROCESS` | `1` | Evita materializar matrices densas regionales. |
| `OSEMOSYS_SPARSE_HIGH_DIM_PARAMS` | `1` | Mantiene parámetros de alta dimensión en forma dispersa. |
| `OSEMOSYS_SPARSE_EMISSION_PENALTIES` | `1` | Evita penalizaciones de emisiones densas. |
| `OSEMOSYS_PYOMO_REPORT_TIMING` | `0` | Desactiva reporte detallado salvo diagnóstico. |

Cambiar `OSEMOSYS_ACTIVITY_LOWER_PRUNE_TOL` modifica semántica numérica del modelo. El valor `0.001` es el certificado para igualdad Excel/CSV y paridad con la referencia; no debe cambiarse sin repetir la certificación.

## 7. Secrets requeridos

Deben existir como **Environment secrets** en `production`, pero sus valores nunca se documentan ni se imprimen:

- `APP_PASSWORD`
- `SECRET_KEY`
- `SIMULATION_OPS_REMOTE_ENVIRONMENTS`
- `SIMULATION_OPS_SHARED_TOKEN`

No guardar estos valores como variables normales, en `.env.example`, documentación, logs o argumentos de shell.

Las credenciales actuales de PostgreSQL son administradas por los archivos protegidos del host. No migrarlas a GitHub ni rotarlas durante este despliegue sin un procedimiento específico de respaldo y rotación.

## 8. Creación idempotente con GitHub CLI

Ejecutar desde una sesión `gh` autenticada con permisos administrativos. Los comandos no incluyen secrets:

```bash
REPO=UPME-SubDemanda/Osemosys_UPME
ENV=production

# Necesario al ejecutar gh.exe desde Git Bash en Windows. Evita que valores
# como /api/v1 o /home/... sean convertidos automáticamente a rutas C:/...
export MSYS_NO_PATHCONV=1

gh variable set COMPOSE_PROJECT_NAME --env "$ENV" -R "$REPO" --body osemosys
gh variable set FRONTEND_BIND_HOST --env "$ENV" -R "$REPO" --body 0.0.0.0
gh variable set FRONTEND_PORT --env "$ENV" -R "$REPO" --body 80
gh variable set FRONTEND_API_UPSTREAM --env "$ENV" -R "$REPO" --body api:8000
gh variable set BACKEND_BRIDGE_NETWORK --env "$ENV" -R "$REPO" --body osemosys_api_bridge
gh variable set API_BIND_HOST --env "$ENV" -R "$REPO" --body 127.0.0.1
gh variable set API_PORT --env "$ENV" -R "$REPO" --body 8010
gh variable set API_WORKERS --env "$ENV" -R "$REPO" --body 2
gh variable set POSTGRES_BIND_HOST --env "$ENV" -R "$REPO" --body 127.0.0.1
gh variable set POSTGRES_PORT --env "$ENV" -R "$REPO" --body 5433
gh variable set REDIS_BIND_HOST --env "$ENV" -R "$REPO" --body 127.0.0.1
gh variable set REDIS_PORT --env "$ENV" -R "$REPO" --body 6379
gh variable set RUN_SEED --env "$ENV" -R "$REPO" --body 0
gh variable set SYNC_APP_USERS --env "$ENV" -R "$REPO" --body 0
gh variable set BACKUP_BEFORE_MIGRATIONS --env "$ENV" -R "$REPO" --body 1
gh variable set BACKUP_DIR --env "$ENV" -R "$REPO" --body /home/procesa01/osemosys-backups/production
gh variable set BACKUP_RETENTION_DAYS --env "$ENV" -R "$REPO" --body 14

gh variable set SIM_WORKER_REPLICAS --env "$ENV" -R "$REPO" --body 2
gh variable set SIM_MAX_CONCURRENCY --env "$ENV" -R "$REPO" --body 1
gh variable set SIM_USER_ACTIVE_LIMIT --env "$ENV" -R "$REPO" --body 3
gh variable set SIM_TOTAL_WEIGHT_LIMIT --env "$ENV" -R "$REPO" --body 3
gh variable set SIM_WEIGHT_NATIONAL --env "$ENV" -R "$REPO" --body 1
gh variable set SIM_WEIGHT_REGIONAL --env "$ENV" -R "$REPO" --body 3

gh variable set SIM_SOLVER_THREADS --env "$ENV" -R "$REPO" --body 0
gh variable set SIM_SOLVER_PROFILE --env "$ENV" -R "$REPO" --body default
gh variable set SIM_SOLVER_HIGHS_DIRECT --env "$ENV" -R "$REPO" --body true
gh variable set SIM_SOLVER_HIGHS_TIME_LIMIT --env "$ENV" -R "$REPO" --body 0
gh variable set SIM_SOLVER_HIGHS_IPM_TOL --env "$ENV" -R "$REPO" --body 1e-7
gh variable set SIM_SOLVER_HIGHS_PRIMAL_TOL --env "$ENV" -R "$REPO" --body 1e-7
gh variable set SIM_SOLVER_HIGHS_DUAL_TOL --env "$ENV" -R "$REPO" --body 1e-7
gh variable set SIM_SOLVER_GLPK_PROFILE --env "$ENV" -R "$REPO" --body fast
gh variable set SIM_SOLVER_GLPK_TIME_LIMIT --env "$ENV" -R "$REPO" --body 0

gh variable set OSEMOSYS_FAST_DATAPORTAL --env "$ENV" -R "$REPO" --body 1
gh variable set OSEMOSYS_ACTIVITY_LOWER_PRUNE_TOL --env "$ENV" -R "$REPO" --body 0.001
gh variable set OSEMOSYS_SPARSE_MATRIX_PREPROCESS --env "$ENV" -R "$REPO" --body 1
gh variable set OSEMOSYS_SPARSE_HIGH_DIM_PARAMS --env "$ENV" -R "$REPO" --body 1
gh variable set OSEMOSYS_SPARSE_EMISSION_PENALTIES --env "$ENV" -R "$REPO" --body 1
gh variable set OSEMOSYS_PYOMO_REPORT_TIMING --env "$ENV" -R "$REPO" --body 0

gh variable set HIGHS_BUILD_FROM_SOURCE --env "$ENV" -R "$REPO" --body 0
gh variable set HIGHS_GIT_REF --env "$ENV" -R "$REPO" --body master
gh variable set HIGHS_ENABLE_HIPO --env "$ENV" -R "$REPO" --body 0
gh variable set OMP_NUM_THREADS --env "$ENV" -R "$REPO" --body 4
gh variable set OPENBLAS_NUM_THREADS --env "$ENV" -R "$REPO" --body 4
gh variable set MKL_NUM_THREADS --env "$ENV" -R "$REPO" --body 4

gh variable set VITE_API_BASE_URL --env "$ENV" -R "$REPO" --body /api/v1
gh variable set VITE_APP_ENV --env "$ENV" -R "$REPO" --body production
gh variable set VITE_SIMULATION_MODE --env "$ENV" -R "$REPO" --body api
gh variable set SIMULATION_OPS_ENVIRONMENT_NAME --env "$ENV" -R "$REPO" --body prod
```

Eliminar opciones experimentales si existen:

```bash
for name in \
  SIM_SOLVER_HIGHS_METHOD \
  SIM_SOLVER_HIGHS_PRESOLVE \
  SIM_SOLVER_HIGHS_PARALLEL \
  SIM_SOLVER_HIGHS_HIPO_PARALLEL_TYPE \
  SIM_SOLVER_HIGHS_CROSSOVER \
  SIM_SOLVER_HIGHS_OPTIONS_JSON \
  SIM_SOLVER_GLPK_OPTIONS_JSON
do
  gh variable delete "$name" --env production -R UPME-SubDemanda/Osemosys_UPME 2>/dev/null || true
done
```

Los secrets deben introducirse de forma interactiva, nunca mediante `--body`:

```bash
gh secret set APP_PASSWORD --env production -R UPME-SubDemanda/Osemosys_UPME
gh secret set SECRET_KEY --env production -R UPME-SubDemanda/Osemosys_UPME
gh secret set SIMULATION_OPS_REMOTE_ENVIRONMENTS --env production -R UPME-SubDemanda/Osemosys_UPME
gh secret set SIMULATION_OPS_SHARED_TOKEN --env production -R UPME-SubDemanda/Osemosys_UPME
```

## 9. Auditoría en GitHub antes del merge a `main`

```bash
gh variable list --env production -R UPME-SubDemanda/Osemosys_UPME | sort
gh secret list --env production -R UPME-SubDemanda/Osemosys_UPME | sort
```

Confirmar especialmente:

```text
API_WORKERS=2
SIM_WORKER_REPLICAS=2
SIM_MAX_CONCURRENCY=1
SIM_TOTAL_WEIGHT_LIMIT=3
SIM_SOLVER_THREADS=0
SIM_SOLVER_PROFILE=default
SIM_SOLVER_HIGHS_DIRECT=true
SIM_SOLVER_GLPK_PROFILE=fast
OSEMOSYS_ACTIVITY_LOWER_PRUNE_TOL=0.001
```

## 10. Precedencia y overrides de PostgreSQL

La configuración efectiva se resuelve en este orden:

1. `core.system_setting` en PostgreSQL.
2. Variables del contenedor generadas desde GitHub Environment.
3. Defaults del código.

Por lo tanto, una fila antigua en `core.system_setting` puede anular una variable correcta de GitHub. Después del deploy, listar todos los overrides:

```bash
docker exec osemosys-api-1 python -c 'from app.db.session import SessionLocal; from sqlalchemy import select; from app.models import SystemSetting; db=SessionLocal(); rows=db.execute(select(SystemSetting).where(SystemSetting.key.like("solver.%")).order_by(SystemSetting.key)).scalars().all(); [print(f"{r.key}={r.value}") for r in rows]; db.close()'
```

Los overrides deben estar ausentes o coincidir exactamente con esta guía. En particular, eliminar valores históricos como:

```text
solver.highs.method=ipm
solver.highs.parallel=on
solver.highs.hipo_parallel_type=both
solver.highs.primal_feasibility_tolerance=1e-5
solver.highs.dual_feasibility_tolerance=1e-5
```

La configuración efectiva debe mostrar `method=""`, tolerancias `1e-7` y sin opciones HiPO.

## 11. Validación posterior al deploy productivo

### 11.1 Revisión y contenedores

```bash
docker compose -p osemosys ps
docker inspect osemosys-api-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^APP_GIT_'
```

Esperado:

- API y frontend saludables.
- Dos contenedores `simulation-worker`.
- Revisión igual al merge desplegado en `main`.
- Fechas de creación recientes para API, frontend y workers.

### 11.2 Variables efectivas

```bash
docker exec osemosys-api-1 env | grep -E '^(SIM_|OSEMOSYS_|HIGHS_|OMP_|OPENBLAS_|MKL_)' | sort
docker exec osemosys-simulation-worker-1 env | grep -E '^(SIM_|OSEMOSYS_|HIGHS_|OMP_|OPENBLAS_|MKL_)' | sort
```

### 11.3 Resolución efectiva del solver

```bash
docker exec osemosys-api-1 python -c 'from dataclasses import asdict; from app.core.config import get_settings; from app.simulation.core.solver_config import resolve_highs_config,resolve_glpk_config; s=get_settings(); print("HIGHS",asdict(resolve_highs_config(s))); print("GLPK",asdict(resolve_glpk_config(s)))'
```

Esperado:

```text
profile=default
threads=0
method=""
presolve=""
parallel=""
hipo_parallel_type=""
run_crossover=""
use_direct=True
time_limit=0.0
ipm_optimality_tolerance=1e-7
primal_feasibility_tolerance=1e-7
dual_feasibility_tolerance=1e-7
GLPK profile=fast
```

### 11.4 Base de datos, Celery y recursos

```bash
docker exec osemosys-api-1 alembic current
docker exec osemosys-simulation-worker-1 celery -A app.simulation.celery_app inspect ping
docker inspect osemosys-api-1 --format 'oom={{.State.OOMKilled}} restarts={{.RestartCount}} status={{.State.Status}}'
docker inspect osemosys-simulation-worker-1 --format 'oom={{.State.OOMKilled}} restarts={{.RestartCount}} status={{.State.Status}}'
free -h
```

Validar que Alembic esté en `head`, ambos workers respondan, no haya OOM/restarts y el host conserve margen suficiente.

### 11.5 Smoke y certificación funcional

```bash
curl -fsS http://127.0.0.1:8010/api/v1/health
curl -fsS http://127.0.0.1/api/v1/health/ready
```

Antes de habilitar carga completa:

1. ejecutar una simulación nacional HiGHS;
2. comprobar objetivo, unmet demand y ausencia de errores numéricos;
3. ejecutar una regional HiGHS en una ventana controlada;
4. observar `/app/simulation-ops`, RAM, OOM, reinicios y tiempos;
5. confirmar que una segunda regional productiva no sea admitida mientras la primera está activa.

## 12. Rollback

Si el despliegue falla, el script restaura las imágenes previas. Verificar en los logs que el rollback corresponda al proyecto `osemosys`, no a `osemosys-public-stg`.

No corregir un fallo reconstruyendo manualmente desde un checkout antiguo. Conservar el backup previo a migraciones y desplegar únicamente una revisión identificada de `main` mediante CI/CD.
