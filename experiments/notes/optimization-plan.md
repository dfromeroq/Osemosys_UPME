# Plan de optimización

## Cambios implementados

1. Perfiles HiGHS configurables por env/BD:
   - `SIM_SOLVER_PROFILE=default|balanced|fast|memory`
   - BD: `core.system_setting` key `solver.profile`
   - Endpoint admin `/api/v1/admin/system-settings/solver` expone `solver_profile`.

2. Runner SAND corregido:
   - `backend/scripts/run_sand_excel_test.py` ya no aplica preprocess notebook adicional por defecto.
   - Usar `--extra-notebook-preprocess` solo para diagnóstico.

3. Scripts de experimentos:
   - `backend/scripts/experiments/run_benchmark.py`
   - `backend/scripts/experiments/resource_sampler.py`
   - `backend/scripts/experiments/compare_results_tolerant.py`
   - `backend/scripts/experiments/validate_solution_residuals.py`

4. Limpieza y memoria:
   - `OSEMOSYS_ACTIVITY_LOWER_PRUNE_TOL=0.001` para paridad notebook/GLPK;
     `0` conserva estrictamente todos los mínimos.
   - `OSEMOSYS_SPARSE_MATRIX_PREPROCESS=1` evita productos cartesianos
     temporales Excel→CSV.
   - `OSEMOSYS_SPARSE_HIGH_DIM_PARAMS=1` usa defaults sparse en parámetros de
     4–5 dimensiones.
   - `OSEMOSYS_PYOMO_REPORT_TIMING=0` implícito: los timings estructurados
     propios permanecen activos.

5. GLPK independiente de HiGHS:
   - `SIM_SOLVER_GLPK_PROFILE=fast|strict|default`.
   - `fast` (A): defaults robustos primal+presolve con modelo sparse.
   - `strict` (B): simplex exacto; sólo diagnóstico, no operativo en este LP.
   - `SIM_SOLVER_GLPK_TIME_LIMIT` y `SIM_SOLVER_GLPK_OPTIONS_JSON`.
   - La reducción sparse de penalizaciones bajó 129,360 filas/columnas en
     nacional y mejoró GLPK ~6% sin cambiar el objetivo.

6. Observabilidad:
   - `/api/v1/simulation-ops/dashboard` incluye CPU/cores, RAM actual/límite/pico,
     PID, procesos, reinicios, `OOMKilled`, cola y eventos recientes.
   - `runtime_resource_samples` registra RSS/peak, cgroup RAM/swap, conteos OOM,
     CPU, threads, PID y etapa.
   - La UI `/app/simulation-ops` muestra tarjetas por servicio y timeline por job.
   - Rediseño inspirado en Open Design `mission-control` (Apache-2.0), conservando
     la paleta slate/sky actual y sin usar marca/assets de terceros.

## Perfiles

- `default`: conserva comportamiento remoto/default de HiGHS.
- `balanced`: `presolve=on`, `parallel=choose`, `run_crossover=off`, `use_direct=true`.
- `fast`: `method=ipm`, `presolve=on`, `parallel=on`, `run_crossover=off`, `use_direct=true`.
- `memory`: `method=simplex`, `presolve=on`, `parallel=off`, `run_crossover=off`, `use_direct=true`.

Los perfiles no fijan threads. Para probar multi-core usar `SIM_SOLVER_THREADS=N` o `solver.threads=N` en BD. En las pruebas simplex nacional/regional no superó ~1.3 cores, por lo que más threads no aporta velocidad relevante.

## Configuración Docker

Al ejecutar `docker compose` desde la raíz, la fuente de interpolación es
`./.env` (o variables del shell). `backend/.env` se carga dentro del contenedor,
pero las claves declaradas en `docker-compose.yml` quedan sobrescritas por la
interpolación raíz. Para stage/local Docker, editar `./.env`.

Mantener `API_WORKERS=1` y una sola corrida regional activa en hosts de 16 GiB.

## Comandos base

Nacional CSV pipeline ya generado:

```bash
docker compose exec -T -e SIMULATION_MODE=sync api sh -lc '
  python scripts/experiments/run_benchmark.py \
    --mode csv-dir \
    --csv-dir /app/tmp/experiments/national_csv_final3 \
    --solver highs \
    --label national-highs-default \
    --repetitions 1
'
```

Fast profile:

```bash
SIM_SOLVER_PROFILE=fast SIM_SOLVER_THREADS=4 FRONTEND_PORT=8091 docker compose up -d --force-recreate api simulation-worker
```

Memory profile:

```bash
SIM_SOLVER_PROFILE=memory SIM_SOLVER_THREADS=1 FRONTEND_PORT=8091 docker compose up -d --force-recreate api simulation-worker
```

Comparar resultados:

```bash
docker compose exec -T api sh -lc '
  python scripts/experiments/compare_results_tolerant.py \
    --ref /app/tmp/validation_sand_v10/csv_pipeline_result.json \
    --actual /app/tmp/validation_sand_v10/app_service_no_manual_preprocess_result.json \
    --out /app/tmp/validation_sand_v10/parity_tolerant_report.json
'
```
