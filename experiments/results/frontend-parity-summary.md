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

## Jobs públicos

| Job | Resultado | Solver | Estado | Objetivo |
|---:|---|---|---|---:|
| 5 | Nacional Excel · HiGHS | HiGHS | SUCCEEDED | 1117470.2926387491 |
| 13 | Nacional CSV · HiGHS | HiGHS | SUCCEEDED | 1117470.2926387491 |
| 7 | Regional Excel · HiGHS | HiGHS | SUCCEEDED | 1828936.3163885893 |
| 14 | Regional CSV · HiGHS | HiGHS | SUCCEEDED | 1828936.3163885896 |
| 9 | Nacional 4 estaciones · HiGHS | HiGHS | SUCCEEDED | 1117959.7702730515 |
| 10 | Nacional Excel · GLPK A | GLPK | SUCCEEDED | 1117470.2926460647 |
| 15 | Nacional CSV · GLPK A | GLPK | SUCCEEDED | 1117470.2926460651 |
| 12 | Regional Excel · GLPK A (cancelado tras 2 h 48 min) | GLPK | CANCELLED por UI | sin solución |

## Paridad

### Nacional HiGHS Excel vs CSV

- Objetivo: diferencia 0.
- Demanda: diferencia 0.
- Unmet: diferencia 0.
- Dispatch anual: máximo `9.09e-13`.
- NewCapacity anual: máximo `5.40e-13`.
- AnnualEmissions anual: máximo `7.28e-12`.

### Regional HiGHS Excel vs CSV

- Objetivo: diferencia absoluta `2.33e-10`, relativa `1.27e-16`.
- Demanda: diferencia 0.
- Unmet: diferencia 0.
- Hay redistribución de dispatch/capacidad/emisiones entre soluciones óptimas
  degeneradas; no cambia objetivo ni cobertura.

### Nacional GLPK Excel vs CSV

- Objetivo: diferencia absoluta `4.66e-10`, relativa `4.17e-16`.
- Demanda/unmet: idénticos.
- GLPK puede seleccionar bases óptimas distintas y redistribuir dispatch y
  capacidad, igual que se documentó en la validación inicial.

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
