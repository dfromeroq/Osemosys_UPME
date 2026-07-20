# Laboratorio de diagnóstico de infactibilidad — 2026-07-17

## Alcance y reglas

- Objetivo: investigar y diseñar un diagnóstico progresivo, explicable y escalable para modelos OSeMOSYS `NATIONAL` y `REGIONAL`.
- No ejecutar simulaciones regionales grandes durante esta fase.
- No modificar staging ni producción.
- No considerar `kNotset`, límites operativos, cancelación, OOM o fallos numéricos como prueba de infactibilidad matemática.
- Todos los experimentos iniciales usarán LPs sintéticos pequeños y artefactos locales.

## Estado inicial del repositorio

Comando:

```bash
git status --short --branch
git log -5 --oneline --decorate
git remote -v
```

Resultado relevante:

- Rama: `develop`, alineada con `origin/develop`.
- HEAD: `a3e2984 Merge PR #177: stabilize regional models and input parity`.
- Archivos no versionados preexistentes que no se tocarán: `AGENTS.md`, `HANDOFF.md`, `pi-session-2026-07-09T23-48-54-875Z_019f4948-c9db-70e2-94c1-5698cd70bef8.html`.

## Entorno local inicial

Comando ejecutado desde `backend` con el `python` disponible en PATH:

```bash
python - <<'PY'
import sys
print(sys.version)
import highspy
import pyomo
PY
```

Resultado:

- Python: `3.11.9`.
- `highspy`: no instalado en ese intérprete.
- `pyomo`: no instalado en ese intérprete.

Conclusión: antes de experimentar con APIs de HiGHS se debe localizar el entorno virtual/Docker del proyecto o crear un entorno aislado; no se instalarán dependencias globalmente sin necesidad.

## Próximas actividades

1. Auditar completamente la implementación actual de diagnóstico y clasificación de solver.
2. Inventariar constraints de Pyomo versus `CONSTRAINT_PARAM_MAP`.
3. Localizar un entorno reproducible con `highspy==1.15.1`.
4. Validar `getIis()` y `getDualRay()` en LPs pequeños factibles, infactibles y no acotados.
5. Documentar una propuesta de pipeline y garantías antes de integrar código productivo.

## Preparación del laboratorio aislado

Se creó `tmp/infeasibility-lab-venv` y se instalaron únicamente dependencias del laboratorio:

```bash
python -m venv tmp/infeasibility-lab-venv
tmp/infeasibility-lab-venv/Scripts/python -m pip install highspy==1.15.1 'pyomo>=6.7.0' pandas
```

Versiones resultantes: HiGHS/highspy 1.15.1, Pyomo 6.10.1, pandas 3.0.3. El entorno vive bajo `tmp/` y no modifica Python global.

## Experimento 1 — API de HiGHS 1.15.1

Script reproducible:

```text
experiments/scripts/probe_highs_infeasibility_apis.py
```

Artefactos:

```text
experiments/results/infeasibility-lab/*.lp
experiments/results/infeasibility-lab/highs-1.15.1-api-probe.json
experiments/results/infeasibility-lab/probe-console.log
experiments/results/infeasibility-lab/highs-options.txt
```

Se probaron LPs mínimos: infactible, infactible con fila redundante, dos conflictos independientes, conflicto de bounds de variable, factible y no acotado.

Hallazgos:

1. `getDualRay()` existe y en el caso `x >= 1`, `x <= 0` devuelve el certificado por filas `[1, -1]`.
2. `getPrimalRay()` existe y para el LP no acotado devuelve `[1]`.
3. `iis_strategy=2`, usado actualmente por la aplicación, **no garantiza irreducibilidad**. Con dos conflictos independientes devolvió las cuatro filas (`x_floor`, `x_ceiling`, `y_floor`, `y_ceiling`).
4. `iis_strategy=4` (`IisStrategy.kIisStrategyIrreducible` en el binding 1.15.1) redujo ese caso a un IIS verdadero: sólo `y_floor`, `y_ceiling` y la columna `y`.
5. El resultado `HighsIis` incluye `row_bound_`, `col_bound_`, `row_status_` y `col_status_`. La implementación actual descarta esa información y afirma incorrectamente que HiGHS no distingue conflictos de cotas.
6. Un conflicto directo `1 <= x <= 0` produjo `readModel() = kWarning`, estado `kInfeasible`, ninguna fila y columna `x` con `col_bound_=[4]` (`boxed`: conflicto LB/UB). La implementación actual informa sólo el nombre de variable y pierde que ambas cotas están en conflicto.
7. En un LP factible, `getIis()` puede devolver `valid_=True` pero listas vacías. Por tanto, antes de interpretar el payload hay que exigir `model_status == kInfeasible`.
8. En un LP no acotado no hay dual ray ni IIS, pero sí primal ray. Esto permite clasificar y explicar `unbounded` por una ruta separada.
9. `getIis()` no devuelve por sí mismo múltiples IIS. El ejemplo con dos conflictos muestra que un único IIS no representa todas las causas posibles.
10. HiGHS expone `iis_time_limit`; actualmente la aplicación no fija un budget para el IIS.

Incidentes del laboratorio también registrados:

- El primer intento de introspección falló porque `inspect.signature()` no soporta métodos pybind11; se repitió usando `__doc__`.
- El primer redirect del probe falló porque el directorio de resultados aún no existía; se creó explícitamente.
- La primera serialización falló porque `HighsIis.info_` es un objeto `HighsIisInfo`, no un iterable; el script ahora serializa sus métricas nominales.
- `writeOptions()` se invocó inicialmente con una firma antigua de dos argumentos; highspy 1.15.1 acepta sólo la ruta.

## Experimento 2 — comportamiento de la implementación actual

Comando conceptual:

```python
try_compute_iis(object(), 'highs', lp_path=<LP sintético>)
```

Resultados:

- En el caso de dos conflictos independientes, la implementación actual marcó como IIS las cuatro filas; confirma que su afirmación de “subsistema irreducible real” es incorrecta con `iis_strategy=2`.
- En el conflicto directo de bounds devolvió `variable_names=['x']`, pero `bound_conflicts=[]`.
- En modelos factible y no acotado devolvió un mensaje genérico de IIS vacío sin clasificar el estado real.
- No valida los retornos de `readModel()`/`run()` ni exige estado matemático `infeasible` antes de llamar `getIis()`.

## Inventario inicial de cobertura

Extracción AST sobre `model_definition.py`:

- Componentes `Constraint`: 73.
- Entradas en `CONSTRAINT_PARAM_MAP`: 20.
- Componentes sin mapeo: 53.

No todos los 53 necesitan aparecer como causa de negocio: muchos son ecuaciones contables/definicionales. Sin embargo, faltan familias relevantes para explicar IIS, especialmente:

- `PlannedMaintenance`;
- `TotalNewCapacity_2`;
- ecuaciones intermedias de reserve margin;
- ecuaciones de contabilidad de emisiones;
- **todas las restricciones de storage**.

Además, `LU3_TechnologyActivityIncreaseByMode` y `LU4_TechnologyActivityDecreaseByMode` tienen cinco índices en el modelo (`REGION, TECHNOLOGY, MODE, YEAR, YEAR`) pero el mapa declara cuatro. El parser cae al fallback y pierde la relación temporal correcta.

## Riesgos de arquitectura observados

- El diagnóstico básico evalúa constraints en valores iniciales, normalmente cero; sus “violaciones” no son prueba causal y pueden tener muchos falsos positivos.
- El ranking por `abs(diff_abs)` compara unidades incompatibles y una desviación respecto al default no demuestra causalidad.
- La cancelación se revisa entre construcción e IIS, pero no puede interrumpir cooperativamente una llamada larga a `getIis()` dentro del mismo proceso.
- La tarea reconstruye el modelo, pero no vuelve a resolverlo antes del IIS; HiGHS sí resuelve el LP internamente en `try_compute_iis()`.
- Falta telemetría por fase interna del IIS y no hay límite explícito de memoria/tiempo del diagnóstico.

## Experimento 3 — feasibility relaxation de HiGHS

Script:

```text
experiments/scripts/probe_highs_feasibility_relaxation.py
```

Artefactos:

```text
experiments/results/infeasibility-lab/highs-1.15.1-feasibility-relaxation.json
experiments/results/infeasibility-lab/feasibility-relaxation-console.log
```

Resultados:

- Penalizaciones uniformes sobre `x >= 1`, `x <= 0`: objetivo de relajación 1 y slack superior 1 en `capacity_ceiling`.
- Dos conflictos independientes: objetivo 2 y dos slacks de magnitud 1.
- Penalizaciones RHS `[100, 1]`: protege demanda y relaja capacidad.
- Penalizaciones RHS `[1, 100]`: protege capacidad y relaja demanda.
- `feasibilityRelaxation()` devuelve `kOk` y `solution.value_valid=True`, pero deja `model_status=kNotset`. La integración no debe interpretar ese `kNotset` como fallo de la simulación original ni usar el model status como validación de la relajación; debe recomputar slacks contra los bounds originales.
- Un conflicto directo de bounds debe detectarse estructuralmente antes: en la prueba informal la relajación retornó objetivo 0 pese al bound boxed inconsistente.

Conclusión: la API nativa sirve para cuantificar cambios mínimos, pero requiere política de penalizaciones, normalización de unidades y validación independiente.

## Corrección inicial implementada

Archivos modificados:

```text
backend/app/simulation/core/infeasibility_analysis.py
backend/app/schemas/simulation.py
backend/tests/test_infeasibility_highs_apis.py
```

Cambios:

1. HiGHS usa `IisStrategy.kIisStrategyIrreducible` en vez de `iis_strategy=2`.
2. Se validan `setOptionValue`, `readModel`, `run` y `model_status`.
3. Sólo se ejecuta/acepta IIS con `HighsModelStatus.kInfeasible`.
4. El método queda etiquetado `highs.getIis.irreducible`.
5. Se preservan conflictos LB/UB de `HighsIis.col_bound_`, incluyendo boxed.
6. El schema público del IIS expone `bound_conflicts`, `irreducible`, timeout y telemetría temporal.
7. Se fija un budget por defecto de 300 s, configurable mediante `OSEMOSYS_IIS_TIME_LIMIT_SECONDS`.
8. Un `getIis()` que termina con warning/timeout puede conservar un subsystem parcial, pero ya no se etiqueta como IIS irreducible.
9. Se agregaron pruebas para irreducibilidad, timeout parcial, bounds boxed, factible y no acotado.
10. Se corrigió el mapeo LU3/LU4 para conservar `YEAR` y `PREVIOUS_YEAR`; el parámetro de cambio se consulta en el año previo, como define la regla del modelo.
11. El nuevo budget se documentó en `.env.example`, `backend/.env.example` y `backend/.env.local.example`, y se propagó a API/worker en `docker-compose.yml`.

Validación:

```text
6 passed in 0.50s (última repetición)
py_compile: PASS
git diff --check: PASS
docker compose config --quiet: PASS
```

El primer intento de pytest falló porque el venv aislado no tenía SQLAlchemy, requerida por `backend/tests/conftest.py`. Se instalaron `sqlalchemy` y `psycopg[binary]` sólo en el venv de laboratorio y se repitió exitosamente.

## Diseño

Se creó la propuesta:

```text
backend/docs/INFEASIBILITY_DIAGNOSTICS_ADR.md
```

Define clasificación operacional, niveles de certeza, análisis estructural, dual ray, relajación jerárquica, focalización regional, IIS irreducible, contrato JSON, cancelación/budgets y fixtures de aceptación.

## Implementación del pipeline progresivo

### Delegación/auditoría

El primer intento de delegar tres auditorías al agente `scout` falló porque ese agente no existe en este entorno. Agentes disponibles reportados: `codex-worker`, `deepseek-probe`. Se repitió con tres `codex-worker` en paralelo y las tres auditorías terminaron correctamente (backend matemático, frontend y validación estructural).

### Clasificación operacional

Se agregó `classify_solver_outcome()` con clases explícitas:

```text
OPTIMAL
INFEASIBLE_CERTIFIED
UNBOUNDED_CERTIFIED
NUMERICAL_FAILURE
RESOURCE_LIMIT
CANCELLED
UNCLASSIFIED
```

`infeasibleOrUnbounded` queda `UNCLASSIFIED`; nunca se trata como infactibilidad certificada. IIS, dual ray y relajación sólo se ejecutan para `INFEASIBLE_CERTIFIED`. Para `UNBOUNDED_CERTIFIED` se obtiene un primal ray y no se ejecuta IIS.

### Certificados matemáticos

Se implementaron:

- `try_compute_dual_ray()` mediante `Highs.getDualRay()`;
- validación independiente del certificado Farkas usando bounds de filas, matriz sparse y bounds de columnas;
- `try_compute_primal_ray()` mediante `Highs.getPrimalRay()` para no acotación;
- mapeo de filas del certificado a nombres Pyomo, familia e índices.

Pruebas sintéticas:

- contradicción por dos filas: certificado validado, margen 1;
- contradicción entre fila y bound de variable: certificado validado, margen 1;
- LP no acotado: primal ray `x → +1` recuperado.

### Relajación de factibilidad productiva

Se implementó `try_feasibility_relaxation()` en una instancia HiGHS separada. Nunca muta la instancia usada por IIS ni el escenario.

- Budget: `OSEMOSYS_RELAXATION_TIME_LIMIT_SECONDS=300`.
- Valida retorno y `solution.value_valid`; no usa el `model_status=kNotset` posterior.
- Recalcula slacks contra bounds originales.
- Normalización `row_scale_v1`.
- Penalización alta para ecuaciones físicas/contables, demanda protegida y límites de negocio relajables.
- Retorna actividad, bound, lado LB/UB, slack físico, slack normalizado, costo ponderado y sugerencia humana.
- Máximo público: 200 filas ordenadas por costo ponderado.

### Análisis estructural

Nuevo módulo:

```text
backend/app/simulation/core/structural_infeasibility.py
```

Reglas implementadas:

- `PARAMETER_BOUND_CONFLICT`;
- `DEMAND_WITHOUT_LOCAL_PRODUCER`;
- `DEMAND_WITH_ONLY_BLOCKED_PRODUCERS` por capacidad máxima cero, availability cero o todos los capacity factors cero;
- `TRADE_ROUTE_NOT_MODELED`: advierte que TradeRoute positivo no entra al modelo actual;
- `INVALID_MIN_STORAGE_CHARGE` fuera de [0,1];
- `NEGATIVE_STORAGE_RATE_LIMIT`.

La detección es conservadora: no declara bloqueada una tecnología sólo por inversión cero en un año, porque podría existir capacidad previa dentro de su vida útil.

### Cobertura constraint → parámetro

El mapa aumentó de 20 a 50 familias. Se agregaron:

- `TotalNewCapacity_2` y `PlannedMaintenance`;
- contabilidad intermedia de emisiones;
- ecuaciones intermedias de reserve margin;
- principales ecuaciones de storage: carga/descarga, niveles, límites, tasas e inversión;
- corrección temporal LU3/LU4.

También se agregó el par de bounds del horizonte completo a `data_validation.BOUND_PAIRS`.

### Progreso y cancelación

`analyze()` / `enrich_solution_dict()` aceptan `on_phase`. La tarea Celery ahora:

1. revisa cancelación antes de cada fase;
2. persiste un evento por `classify`, `dual_ray`, `feasibility_relaxation`, `iis` y `structural`;
3. conserva los timeouts nativos para IIS y relajación.

Una llamada nativa en curso no es cooperativamente interrumpible, pero queda acotada por timeout; la cancelación se aplica antes de la siguiente fase.

### API y frontend

El contrato público ahora incluye:

- clasificación y nivel de evidencia;
- dual/primal ray;
- relajación cuantificada;
- hallazgos estructurales;
- telemetría/timeout e irreducibilidad del IIS.

`InfeasibilityReportPage.tsx` muestra:

- clasificación certificada u operacional;
- certificado Farkas con pesos y dimensiones;
- primal ray para no acotación;
- hallazgos estructurales;
- tabla de cambios mínimos sugeridos;
- explicación corregida: un IIS es una causa mínima, no necesariamente la única.

### Fixtures OSeMOSYS pequeños

Se construyen instancias Pyomo reales desde CSV y se diagnostican end-to-end:

1. capacidad máxima cero con demanda 10 → recomienda aumentar capacidad máxima en 10;
2. emisiones mínimas 10 con límite cero → recomienda aumentar límite anual en 10;
3. reserve margin 1.2 con capacidad máxima 10 y demanda 10 → identifica faltante de capacidad 2;
4. UDC que obliga capacidad <= 0 con demanda 10 → recomienda relajar UDC en 10.

Fixtures estructurales adicionales cubren demanda sin productor, región dependiente de TradeRoute ignorado, min>max y storage inválido.

## Validación acumulada

Último bloque backend focalizado:

```text
30 passed, 1 skipped
```

Además:

```text
ruff (archivos nuevos/modificados salvo tasks.py): PASS
frontend InfeasibilityReportPage/domain eslint: PASS
frontend npm run typecheck: PASS después de npm install
docker compose config --quiet: PASS
git diff --check: PASS
```

Incidencias no causadas por este cambio:

- `npm run lint` completo falla por errores preexistentes en componentes de reportes, charts y filtros; los dos archivos tocados pasan ESLint aisladamente.
- El primer `npm run typecheck` falló porque `node_modules` no tenía dependencias declaradas (`lucide-react`, `@tailwindcss/vite`) y tenía tipos Highcharts desalineados. `npm install` restauró dependencias sin modificar package manifests/lock y luego typecheck pasó.
- `test_simulation_task_failure_metadata.py` no puede recolectarse en Windows porque `runtime_observability.py` importa el módulo Unix `resource`. Antes de eso faltaba Celery en el venv aislado; se instaló allí. Esta incompatibilidad es preexistente.
- Ruff sobre `tasks.py` reporta E402 preexistente porque el `from __future__` está antes del docstring del módulo. Los demás archivos pasan.

No se ejecutó ninguna simulación regional grande ni se tocó staging/producción.

## Revisión cruzada posterior

Se delegaron tres revisiones del working tree (matemática/backend, frontend/contrato y code review general). Hallazgos corregidos:

- el task on-demand ya no hardcodea `solver_status='infactible'`; usa el estado real persistido en `model_timings_json`;
- un reintento limpia resultados enriquecidos anteriores para no mostrarlos como actuales;
- `DiagnosticStatus` incorpora `CANCELLED`; cancelación ya no se presenta como fallo;
- al cancelar RUNNING se persiste `CANCELLED` antes de enviar SIGTERM, evitando jobs pegados;
- el handler `task_failure` ahora cierra diagnósticos RUNNING ante `WorkerLostError`;
- el schema de resultado expone status/error/timestamps/duración del diagnóstico que la UI ya consumía;
- el parser conserva compatibilidad con payloads IIS legacy sin status explícito;
- se implementó validación algebraica del primal ray (dirección de recesión, bounds y mejora del objetivo);
- se agregó `RESIDUAL_CAPACITY_EXCEEDS_MAXIMUM`.

Un reviewer sugirió que el sexto argumento de `feasibilityRelaxation` era penalización de columnas. Se verificó contra el docstring real de highspy 1.15.1 instalado:

```text
(global_lower_penalty, global_upper_penalty, global_rhs_penalty,
 local_lower_penalty, local_upper_penalty, local_rhs_penalty)
```

Por tanto, el sexto argumento usado por la implementación sí corresponde a penalizaciones locales de filas/RHS; además el comportamiento fue validado experimentalmente cambiando preferencias entre demanda y capacidad.

La observación sobre `TotalModelHorizonTechnologyActivity` tampoco era un bug: esa igualdad contable se mantiene rígida, mientras sus límites Upper/Lower son deliberadamente relajables para poder sugerir cuánto modificar los parámetros de negocio.

Validación posterior a correcciones:

```text
31 passed, 1 skipped
frontend npm run typecheck: PASS
frontend ESLint focalizado: PASS
docker compose config --quiet: PASS
py_compile: PASS
git diff --check: PASS
```

Ruff sobre `simulation_service.py` señala dos problemas preexistentes no relacionados (`Scenario` sin usar y `sync_mode` sin usar). Ruff sobre `simulations.py` también encuentra imports/E402 preexistentes. Los módulos nuevos y el core de diagnóstico pasan Ruff.

Ajustes finales de contrato/seguridad:

- el JSON descargable incluye clasificación, certificado, relajación y hallazgos estructurales;
- se eliminan `csv_dir` e `ilp_path` del contrato público/descarga para no exponer rutas absolutas internas;
- el `.ilp` continúa descargándose únicamente mediante su endpoint autenticado;
- Gurobi propaga `IISMinimal` a `irreducible`; la UI no llama IIS mínimo a un subsystem no certificado;
- validación Pydantic directa confirmó `CANCELLED` y los nuevos bloques, sin `csv_dir` público.

Última validación focalizada:

```text
31 passed, 1 skipped
frontend typecheck: PASS
frontend ESLint focalizado: PASS
Pydantic contract smoke test: PASS
```

## Benchmark regional autorizado — 2026-07-18 UTC

El usuario autorizó el benchmark local de `scenario_37_Parameters_SAND.xlsx` y,
si todo iba bien, `scenario_36_Parameters_SAND.xlsx`, ambos en Downloads. Se
impuso watchdog de 12 GiB RSS dentro del máximo autorizado de 14 GiB. No se
modificaron los Excel ni la BD; los artefactos completos son temporales en
`tmp/infeasibility-benchmarks/` y el resultado reproducible está en
`experiments/results/infeasibility-regional-benchmark-20260718.md`.

Resultados principales:

- Ambos casos fueron `HighsModelStatus.kInfeasible` con IPM+crossover.
- Caso 37: validación estructural detectó 274 pares reales de límites anuales
  de actividad. El Farkas ray validado aisló `RE1/OR_MINBAG/2050`: mínimo
  117.066115414 contra máximo 2.457698130, brecha 114.608417284. Un LP reducido
  confirmó dual ray, IIS irreducible y relaxation mínima iguales a esa brecha.
- Caso 36: no tuvo hallazgos estructurales ni dual ray/IIS disponible dentro de
  los budgets. Presolve certificó infactibilidad en 5.72 s; simplex sin
  presolve agotó 90 s sin certificado. Se registró como infactibilidad
  certificada sin causa atribuible, no como una recomendación de cambio.
- La relaxation global del caso 37 llegó a 9.368 GiB y devolvió `kError` sin
  solución válida; no se mostraron slacks parciales.
- Se agregó límite explícito para dual rays, y el IIS ahora limita también su
  solve previo. Esto evita que estas fases se queden abiertas en LPs regionales.

### Continuación: auditoría pandas directa del escenario 36

La primera conclusión “sin causa atribuible” se revisó con dos análisis de sólo
lectura sobre los CSV ya generados, sin solver ni LP:

1. `audit_csv_fuel_reachability.py` terminó en 0.674 s y no encontró demanda
   sin ruta primaria de input/output.
2. `audit_csv_feasibility_bounds.py` terminó en 0.507 s. Tras excluir ruido
   sub-tolerancia, detectó 772 mínimos anuales de actividad mayores que la
   actividad máxima físicamente posible desde residual + inversiones vivas.

Se validó una causa concreta con LP reducido:

```text
RE1 / AN_DEMRESNGSCKN_LOW_URB / 2025
mínimo anual:                         4.259750097640
residual:                             3.938600997713
máximo inversión 2022..2024:          0
máximo inversión 2025:                0.069692200000
actividad máxima disponible:          4.008293197713
brecha:                               0.251456899927
```

El LP reducido devolvió Farkas ray validado, IIS irreducible de seis filas y
relajación mínima igual a `0.251456899927`. Esto convierte el caso 36 en una
causa cuantificada y reparable; el informe de benchmark contiene alternativas
concretas y advierte que aún quedan 771 cotas similares por revisar.
