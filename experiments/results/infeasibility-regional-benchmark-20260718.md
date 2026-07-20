# Benchmark local de infactibilidad regional — 2026-07-18 UTC

## Autorización y controles

- Autorizado por el usuario para usar los Excel de `C:/Users/Usuario/Downloads` y hasta 14 GB de RAM.
- Se usó un watchdog con corte duro de **12 GiB RSS**, timeout externo por comando y límites HiGHS por fase.
- No se modificó ningún Excel, escenario de BD, staging ni producción. Los CSV y LP temporales viven en `tmp/infeasibility-benchmarks/` (ignorado por Git).
- Servicios Docker estaban ya levantados al iniciar; no se reiniciaron ni se utilizaron para estos solves.
- Entorno: Python aislado `tmp/infeasibility-lab-venv`, HiGHS/highspy 1.15.1. Se instaló `psutil` únicamente en ese entorno para el watchdog.

## Entradas reproducibles

| Caso | Archivo | SHA-256 | Tamaño |
|---|---|---|---:|
| 37 | `scenario_37_Parameters_SAND.xlsx` | `f516cc5a5ff87449c5536f382f75d6c630db4d8fbacf0f6b72e25bbce9051537` | 3,022,573 B |
| 36 | `scenario_36_Parameters_SAND.xlsx` | `a25feddb67319a332222220836cf15269908d57163612bfe6435d02f957a5aea` | 2,917,520 B |

Ambos contienen una hoja `Parameters`, 31 parámetros, 33 años, un timeslice y dos modos de operación. No tienen storage ni UDC en esta ruta SAND.

## Resultado del escenario 37: causa explícita y recuperación cuantificada

### Fases

| Fase | Resultado | Tiempo | Pico RSS |
|---|---|---:|---:|
| Excel → 38 CSV canónicos | PASS | 73.951 s | 0.174 GiB |
| Validación estructural | 274 conflictos reales | 79.336 s | incluido arriba |
| Construcción Pyomo + LP | 2,116,983 variables; 2,187,798 restricciones; LP 758,234,228 B | 112.699 s | 2.902 GiB total baseline |
| HiGHS IPM+crossover | `HighsModelStatus.kInfeasible` | solve 4.551 s (fase 41.883 s) | 2.902 GiB |
| Dual ray Farkas | **validado** | 48.463 s | 4.700 GiB |
| Relaxation global | no concluyente: `kError`, sin solución válida | 114.123 s dentro de fase 177.043 s | 9.368 GiB |
| IIS global irreducible | detenido: timeout externo; sin payload persistido | — | no excedió watchdog |

Los 274 hallazgos son todos conflictos reales, no de precisión:
`TotalTechnologyAnnualActivityLowerLimit > TotalTechnologyAnnualActivityUpperLimit`.

### Conflicto certificado seleccionado

El dual ray Farkas validó dos filas del LP original:

```text
c_l_TotalAnnualTechnologyActivityLowerlimit(RE1_OR_MINBAG_2050)_  peso +1
c_u_TotalAnnualTechnologyActivityUpperlimit(RE1_OR_MINBAG_2050)_  peso -1
```

La tecnología completa es `OR_MINBAG` (el tokenizador LP experimental la separó visualmente como `OR` + `MINBAG`; los CSV fuente confirman el código completo).

| Parámetro | Valor |
|---|---:|
| `REGION` / tecnología / año | `RE1` / `OR_MINBAG` / `2050` |
| `TotalTechnologyAnnualActivityLowerLimit` | 117.066115414 |
| `TotalTechnologyAnnualActivityUpperLimit` | 2.457698130 |
| Brecha y margen Farkas validado | **114.608417284** |

El LP reducido de una variable conservó exactamente esas dos filas. HiGHS devolvió:

- dual ray válido, margen `114.608417284`;
- **IIS irreducible** de exactamente esas dos restricciones (`0.0009215 s`);
- feasibility relaxation válida (`0.0002954 s`), slack de límite inferior `114.608417284`.

### Cómo hacerlo factible

Para ese conflicto particular basta una de estas correcciones de negocio (no aplicar ambas sin revisar intención):

1. bajar `TotalTechnologyAnnualActivityLowerLimit[RE1, OR_MINBAG, 2050]` por al menos `114.608417284`, hasta `2.457698130` o menos; **o**
2. subir `TotalTechnologyAnnualActivityUpperLimit[RE1, OR_MINBAG, 2050]` por al menos `114.608417284`, hasta `117.066115414` o más.

Esto certifica la reparación de **una causa mínima**. Hay otros 273 pares estructuralmente contradictorios: se deben revisar todos antes de afirmar que el escenario completo queda factible. El listado reproducible está en:

`tmp/infeasibility-benchmarks/scenario-37-20260717/artifacts/baseline_structural_findings.json`.

## Resultado del escenario 36: causa estructural localizada por auditoría pandas

### Fases

| Fase | Resultado | Tiempo | Pico RSS |
|---|---|---:|---:|
| Excel → 38 CSV canónicos | PASS | 66.407 s | 0.180 GiB |
| Validación estructural v1/v2 | 0 hallazgos | 75.252 / 80.483 s | — |
| Auditoría pandas de capacidad física | 772 cotas anuales imposibles | **0.507 s** | despreciable |
| Auditoría pandas de grafo de fuels | 0 demands sin fuente primaria | **0.674 s** | despreciable |
| Construcción Pyomo + LP | 2,092,007 variables; 2,155,572 restricciones; LP 748,696,252 B | 113.274 s | 2.970 GiB total baseline |
| HiGHS IPM+crossover | `HighsModelStatus.kInfeasible` | solve 6.291 s (fase 44.109 s) | 2.970 GiB |

El presolve redujo el modelo a 385,938 filas, 424,315 columnas y 3,627,378 no-ceros antes de declarar `kInfeasible`. No preservó un dual ray (`getDualRayExist=False`) y el modelo presuelto escrito por HiGHS quedó vacío/inviable (56 B), sin nombres de filas atribuibles.

### Causa mínima verificable

La auditoría vectorizada compara para cada actividad mínima:

```text
máxima actividad = (residual + inversiones vivas máximas)
                   × CapacityToActivityUnit × CapacityFactor × AvailabilityFactor
                   × YearSplit
```

Un conflicto representativo es:

| Dato | Valor |
|---|---:|
| región / tecnología / año | `RE1` / `AN_DEMRESNGSCKN_LOW_URB` / `2025` |
| actividad anual mínima | 4.259750097640 |
| capacidad residual | 3.938600997713 |
| máximos de nueva capacidad 2022, 2023, 2024 | 0, 0, 0 |
| máximo de nueva capacidad 2025 | 0.069692200000 |
| vida útil / C2A / CapacityFactor / YearSplit | 20 / 1 / 1 / 1 |
| máxima actividad físicamente disponible | 4.008293197713 |
| brecha necesaria | **0.251456899927** |

Un LP reducido que mantiene la actividad mínima, `ConstraintCapacity` y los cuatro máximos anuales de nueva capacidad confirmó:

- dual ray/Farkas válido, margen `0.251456899927`;
- IIS **irreducible** de seis filas: actividad mínima, capacidad y los máximos de inversión 2022–2025;
- relaxation válida que propone bajar el mínimo en `0.251456899927`.

No hay `CapacityOfOneTechnologyUnit` explícito; el default es 0, por lo que esta tecnología no tiene granularidad discreta que redondear.

### Cómo reparar este conflicto del escenario 36

Una de estas opciones basta para este núcleo, pero no para los otros 771 hallazgos:

1. reducir `TotalTechnologyAnnualActivityLowerLimit[RE1, AN_DEMRESNGSCKN_LOW_URB, 2025]` desde `4.259750097640` hasta `4.008293197713` o menos; **o**
2. aumentar en conjunto los máximos de inversión vivos 2022–2025 en al menos `0.251456899927`; por ejemplo, elevar el máximo 2025 de `0.069692200000` a `0.321149099927`; **o**
3. aumentar `ResidualCapacity[RE1, AN_DEMRESNGSCKN_LOW_URB, 2025]` en al menos `0.251456899927`.

Las opciones 2 y 3 deben revisarse con el significado físico de la tecnología. La auditoría no afirma que modificar una sola fila haga factible todo el escenario: identifica **772** cotas necesarias incompatibles en **188** tecnologías, con brecha agregada de 8.502044687034. La mayor concentración inicial está en 2023–2024 (147 y 160 hallazgos); el resumen priorizado está en `pandas_capacity_audit_summary.json` dentro del directorio temporal del benchmark.

### Intentos globales correctamente degradados

| Intento | Resultado | Interpretación |
|---|---|---|
| dual ray automático y simplex con presolve | `has_ray=False` | no se afirma certificado Farkas global |
| simplex sin presolve, 90 s | `kTimeLimit`; 44,486 violaciones primales, suma 23,294.1 | no es certificado ni fuente de filas |
| `getIis()` `FromLp`, 90 s | `HighsStatus.kError`, 0 filas | no se presenta como IIS/subsistema |

El máximo observado en simplex sin presolve fue ~3.72 GiB, bajo el corte de 12 GiB. No quedó ningún proceso Python/HiGHS residente después de cada prueba.

## Cambios de producto derivados del benchmark

- El dual ray productivo ahora usa simplex y `OSEMOSYS_DUAL_RAY_TIME_LIMIT_SECONDS` (default 300 s), porque `solver=choose` puede seleccionar IPM y dejar `has_ray=False`.
- IIS configura también `time_limit` para su solve previo; antes sólo se limitaba la búsqueda IIS y el solve previo podía quedarse abierto.
- Un LP existente permite calcular IIS sin retener/reconstruir la instancia Pyomo, reduciendo presión de memoria en diagnósticos posteriores.
- Se añadió el detector estructural `DEMAND_WITHOUT_USABLE_CAPACITY_PATH`, con vida útil, residual, inversión máxima, disponibilidad, factor de capacidad y conversión capacidad→actividad.
- Se añadieron auditorías pandas de sólo lectura para cotas de actividad-capacidad y reachability de fuels; el caso 36 mostró que las cotas deben extenderse desde demanda hacia mínimos de actividad obligatorios.

## Artefactos temporales

- Escenario 37: `tmp/infeasibility-benchmarks/scenario-37-20260717/`.
- Escenario 36: `tmp/infeasibility-benchmarks/scenario-36-20260717/`.
- Runner reproducible: `experiments/scripts/run_regional_infeasibility_benchmark.py`.
- Probes acotados: `experiments/scripts/probe_reduced_regional_conflict.py`, `probe_reduced_activity_capacity_conflict.py`, `probe_dual_ray_without_presolve.py`, `probe_fast_conflict_subsystem.py`.
- Auditorías pandas: `experiments/scripts/audit_csv_feasibility_bounds.py` y `audit_csv_fuel_reachability.py`.
