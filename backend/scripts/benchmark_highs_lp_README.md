# Benchmark HiGHS — mismo `.lp`, distintos entornos

Diagnóstico del gap notebook (~95 s) vs worker Docker (~207 s) usando **el mismo archivo LP** y tolerancias `1e-5`.

## Archivos

| Script | Uso |
|--------|-----|
| `generate_lp_from_csv_zip.py` | Genera `model.lp` desde `CSV.zip` (flujo notebook, `has_storage=True`) |
| `benchmark_highs_lp.py` | Resuelve un `.lp` con flujo notebook celda 8 + log opcional |
| `parse_benchmark_logs.py` | Agrega presolve/simplex/postsolve desde logs |

LP de referencia: `backend/tmp/benchmark/model.lp` (~1056 MB, 3.39M filas).

## Comandos ejecutados (2026-06-08)

```powershell
# Generar LP (Docker worker)
docker exec osemosys-simulation-worker-1 python scripts/generate_lp_from_csv_zip.py \
  --csv-zip /app/tmp/benchmark/CSV.zip --out /app/tmp/benchmark/model.lp

# A — Windows local
python scripts/benchmark_highs_lp.py --lp tmp/benchmark/model.lp --run-label local \
  --log-file tmp/benchmark/logs/local.txt --json-out tmp/benchmark/results/local.json

# B — Docker worker (OMP=4, default compose)
docker exec osemosys-simulation-worker-1 python scripts/benchmark_highs_lp.py \
  --lp /app/tmp/benchmark/model.lp --run-label docker \
  --log-file /app/tmp/benchmark/logs/docker.txt

# C — Docker worker OMP=1
docker exec -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  osemosys-simulation-worker-1 python scripts/benchmark_highs_lp.py \
  --lp /app/tmp/benchmark/model.lp --run-label docker-omp1 \
  --log-file /app/tmp/benchmark/logs/docker-omp1.txt --json-out /app/tmp/benchmark/results/docker-omp1.json
```

Tolerancias en los tres runs: `primal_feasibility_tolerance=1e-5`, `dual_feasibility_tolerance=1e-5`.

## Resultados

| Run | Entorno | HiGHS | OMP | LP rows | presolve_s | simplex_s | postsolve_s | total_s | iter |
|-----|---------|-------|-----|---------|------------|-----------|-------------|---------|------|
| **A** | Windows local | 1.13.1 | (default) | 3 390 685 | **14.8** | 61.1 | 38.7 | **120.2** | 97 087 |
| **B** | Docker worker | 1.14.0 | 4 | 3 390 685 | **114.4** | 43.0 | 23.5 | **186.5** | 97 087 |
| **C** | Docker OMP=1 | 1.14.0 | 1 | 3 390 685 | **145.9** | 44.1 | 22.5 | **218.5** | 97 087 |

Objetivo óptimo en los tres: **1 722 773.7086** (idéntico).

Referencia notebook (`notebooks/log_highs.txt`, mismo LP conceptual): total **94.8 s**, presolve ~**12.6 s**.

## Conclusión

1. **No es el tamaño del LP.** Con el **mismo** `model.lp`, Docker tarda **1.55×** (B) a **1.82×** (C) que Windows local. Misma filas, mismo objetivo, mismas iteraciones.

2. **El cuello de botella es presolve dentro de `h.run()`.** En Docker, presolve consume **~114–146 s** vs **~15 s** en Windows (**7–10×**). Simplex y postsolve son del mismo orden en ambos entornos.

3. **Es un problema de entorno, no de pipeline de datos** (para este experimento). La comparación notebook vs job mezclaba además LPs distintos (`has_storage` on/off); este benchmark aísla entorno con LP idéntico y confirma que **WSL2/Docker/Linux penaliza fuertemente el presolve de HiGHS**.

4. **Reducir OMP a 1 empeora el tiempo** (C > B). No es la palanca correcta sin más tuning.

5. **Versión HiGHS:** local 1.13.1 vs Docker 1.14.0 — diferencia menor frente al gap de presolve; conviene alinear versiones en follow-up.

## Interpretación vs jobs de producción

| Comparación | Qué explica |
|-------------|-------------|
| Job 38 (~207 s) vs notebook (~95 s) | ~95% del gap = presolve lento en Docker; además el job usaba LP distinto (sin storage) |
| Benchmark B (~186 s) vs A (~120 s) | Mismo LP → gap puro de entorno (~66 s, casi todo presolve) |
| Benchmark A (~120 s) vs notebook (~95 s) | Mismo OS, LP equivalente; delta ~25 s (versión HiGHS, I/O OneDrive, carga del sistema) |

## Fuera de alcance (diagnose_only)

- Paridad `has_storage` CSV↔BD
- Cambios en `docker-compose.yml` (cpus, memoria, OMP)
- Cambios en admin/solver_config

## Reproducir parseo de fases

```powershell
cd backend
python scripts/parse_benchmark_logs.py
# → tmp/benchmark/results/summary.json
```
