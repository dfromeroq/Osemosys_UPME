# Validación publicada en frontend — Excel vs CSV

Fecha: 2026-07-11. Usuario propietario: `seed`. Todos los escenarios tienen
`edit_policy=OPEN` y todos los jobs son públicos.

## Escenarios visibles

| ID | Escenario | Tipo | Modo |
|---:|---|---|---|
| 6 | VALIDACIÓN Nacional · Excel | NATIONAL | STANDARD |
| 8 | VALIDACIÓN Regional · Excel | REGIONAL | STANDARD |
| 10 | VALIDACIÓN Nacional · 4 estaciones | NATIONAL | PREPROCESSED_CSV |
| 11 | VALIDACIÓN Nacional · CSV | NATIONAL | PREPROCESSED_CSV |
| 12 | VALIDACIÓN Regional · CSV | REGIONAL | PREPROCESSED_CSV |

Los escenarios CSV 11/12 se generaron exportando los inputs efectivos de los
escenarios Excel 6/8 desde la propia aplicación y reimportándolos. Esto prueba
el roundtrip real de la aplicación, no un conversor externo.

## Jobs públicos canónicos

| Job | Resultado | Solver | Estado | Objetivo |
|---:|---|---|---|---:|
| 17 | Nacional Excel · HiGHS canónico | HiGHS | SUCCEEDED | 1117470.2926387503 |
| 21 | Nacional CSV · HiGHS canónico | HiGHS | SUCCEEDED | 1117470.2926387503 |
| 19 | Regional Excel · HiGHS canónico | HiGHS | SUCCEEDED | 1828936.3163885893 |
| 22 | Regional CSV · HiGHS canónico | HiGHS | SUCCEEDED | 1828936.3163885893 |
| 23 | Nacional Excel · GLPK A canónico | GLPK | SUCCEEDED | 1117470.292646065 |
| 24 | Nacional CSV · GLPK A canónico | GLPK | SUCCEEDED | 1117470.292646065 |
| 9 | Nacional 4 estaciones · HiGHS | HiGHS | SUCCEEDED | 1117959.7702730515 |
| 12 | Regional Excel · GLPK A (cancelado tras 2 h 48 min) | GLPK | CANCELLED por UI | sin solución |

Los jobs anteriores permanecen identificados como `[Histórico pre-canónico]`.

## Paridad canónica

Los CSV finales entregados a Pyomo son idénticos byte por byte:

- nacional: 44/44 archivos;
- regional: 28/28 archivos.

La comparación multiconjunto incluye todas las dimensiones tipadas,
`index_json`, `value` y `value2` de cada resultado persistido:

| Par | Filas Excel | Filas CSV | Sólo Excel | Sólo CSV |
|---|---:|---:|---:|---:|
| Nacional HiGHS (17 vs 21) | 171365 | 171365 | 0 | 0 |
| Regional HiGHS (19 vs 22) | 398539 | 398539 | 0 | 0 |
| Nacional GLPK (23 vs 24) | 171005 | 171005 | 0 | 0 |

Por tanto, objetivo, dispatch, capacidad, emisiones y el resto de variables son
idénticos dentro de cada par, no sólo equivalentes dentro de una tolerancia.

La implementación conserva el orden SAND durante las reglas heredadas del
notebook —algunas usan `groupby().first()`— y aplica orden canónico únicamente
al resultado procesado. También conserva en escenarios CSV los IDs reales de
catálogo; antes se reemplazaban accidentalmente por posiciones 1..N.

## Timeslices

El Excel contiene 96 segmentos organizados como 4 estaciones × 24 segmentos:
`S101…S124`, `S201…S224`, `S301…S324`, `S401…S424`.

El escenario 10 agrega cada bloque de 24 a `ESTACION_1…ESTACION_4`:

- `YearSplit`: suma los 24 pesos y queda 0.25 por estación/año.
- parámetros energéticos: se agregan por bloque.
- `CapacityFactor`: se promedia por bloque.

La corrida de cuatro estaciones es intencionalmente distinta del caso anual de
un solo timeslice y obtuvo objetivo `1117959.7702730515`.

## GLPK

Perfil A validado:

- conserva defaults robustos de GLPK (primal, scaling, advanced basis,
  presolve);
- usa el modelo reducido de penalizaciones de emisiones;
- nacional: solver `104.93 → 98.48 s`, peak RSS `1740 → 1467 MiB`;
- HiGHS también mejora: wall `83.6 → 72.5 s`, peak `3408 → 2850 MiB`.

Perfil B:

- `xcheck` reclasificó el LP como unbounded;
- simplex exacto tardó 620–919 s y declaró infactibilidad, incluso después de
  corregir el bound conflict de `2.01e-11`;
- el modelo decimal/redondeado no es resoluble por GLPK en aritmética racional
  exacta. La certificación estricta queda en HiGHS (`0` violaciones >1e-9 en
  regional).

GLPK regional fue cancelado explícitamente desde el frontend mediante
`POST /simulations/{id}/cancel`: el intento principal llevaba ~2 h 48 min. El
reintento corto se eliminó del catálogo para no duplicar resultados. No hubo
OOM ni watchdog. No es operativo para este tamaño con simplex GLPK 5.0.
