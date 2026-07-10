# Resultados HiGHS/GLPK — nacional, regional y timeslices

Referencia notebook/GLPK nacional: `1117470.289211735`.

## Hallazgo numérico

La diferencia inicial de HiGHS (~`1.27`) no era un error de optimización. GLPK
reportaba óptimo mientras ignoraba mínimos positivos pequeños en
`TotalTechnologyAnnualActivityLowerLimit`:

- GLPK: 44 restricciones con violación `>1e-4`; máxima ~`9.9e-4`.
- HiGHS estricto sin poda: 0 violaciones `>1e-9`; objetivo
  `1117471.5592456092`.
- Al podar explícitamente mínimos `<=0.001`, HiGHS recupera la referencia
  notebook. La poda es configurable con
  `OSEMOSYS_ACTIVITY_LOWER_PRUNE_TOL` y está desactivada por defecto en el
  ejemplo; el `.env` experimental local usa `0.001`.

También se normalizaron placeholders de límites de emisiones extremos a
`9,999,999`, sentinel que las restricciones interpretan como no acotado.

## Resultados finales

| Caso | Solver/configuración | Estado | Objetivo | Solver s | Wall s | Peak RSS MiB | Validación |
|---|---|---:|---:|---:|---:|---:|---|
| Nacional final 1 TS | HiGHS simplex, tol `1e-7` | optimal | `1117470.2892099898` | 15.08 | 83.56 | 3407.98 | Dif. notebook `1.75e-6` |
| Nacional final 1 TS | GLPK | optimal | `1117470.2892168164` | 104.93 | 134.44 | 1740.40 | Dif. notebook `5.08e-6` |
| Nacional sintético 2 TS | HiGHS simplex, tol `1e-9` | optimal | `1117470.2892116222` | 185.57 | 260.86 | 3770.14 | Antes terminaba `kNotset`; dif. `1.13e-7` |
| Regional final | HiGHS perfil memory, tol `1e-9` | optimal | `1829148.0336643092` | 181.23 | ~415 | ~11,448 cgroup | 2,593,551 restricciones; 0 violaciones `>1e-9`; máxima `6.88e-10` |

La primera corrida regional con tolerancia `1e-7` obtuvo
`1829148.0335948786`; la diferencia contra la certificación estricta es
`6.94e-5` (relativa `3.8e-11`). Ambas tuvieron cobertura `1.0` y unmet `0`.

## Optimización Excel regional

El preproceso legacy materializaba productos cartesianos y luego descartaba
las filas sin valor. En regional generaba temporalmente decenas de millones de
filas para escribir sólo ~550 mil.

| Pipeline regional Excel→CSV | Tiempo | Peak proceso |
|---|---:|---:|
| Legacy | 494 s | ~13.85 GiB |
| Sparse + single-pass | 65.7 s | 183 MiB |

Mejora: ~`7.5x` en tiempo y ~`75x` en memoria del proceso. La ruta sparse
preserva el orden categórico de los sets para reproducir exactamente el
`groupby().first()` del notebook en emisiones. En nacional, el
`EmissionActivityRatio.csv` final tuvo 0 diferencias `>1e-12` contra la salida
de referencia.

## Escala regional observada

- 2,343 tecnologías, 541 combustibles, 34 años, 2 modos, 1 timeslice.
- Build Pyomo: 66.7 s, peak proceso 1.97 GiB.
- 2,551,802 variables y 2,593,551 restricciones.
- LP: 9,110,252 nonzeros.
- Peak del solve: ~11.2 GiB de cgroup; `OOMKilled=false`.
- Dual simplex no mostró paralelismo significativo: ~1.2–1.3 cores aun con 2
  threads configurados.

## Decisiones

- HiGHS queda validado como solver principal para nacional y regional.
- GLPK se conserva como opción compatible y referencia histórica.
- No usar el perfil IPM `fast` en estos datos: las pruebas anteriores terminaron
  `Unknown`/no certificadas.
- Ejecutar regional de forma aislada con límite ponderado; requiere ~11–12 GiB.
- Para paridad notebook usar poda `0.001`; para factibilidad estricta sin alterar
  mínimos usar `0` y aceptar que el objetivo correcto será mayor que el GLPK
  histórico.
