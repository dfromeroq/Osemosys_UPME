# ADR — Diagnóstico progresivo de infactibilidad OSeMOSYS

- Estado: **Aceptado e implementado en primera versión; benchmark regional controlado completado**
- Fecha: 2026-07-17
- Aplica a: simulaciones `NATIONAL` y `REGIONAL`
- Evidencia experimental: `experiments/notes/infeasibility-diagnostics-lab-20260717.md`

## 1. Problema

El sistema debe responder, sin modificar el escenario:

1. ¿El solver demostró infactibilidad matemática?
2. ¿Qué regiones, años, timeslices, tecnologías, fuels o límites participan?
3. ¿Qué cambio cuantificado permitiría recuperar factibilidad?
4. ¿La conclusión es certificada o heurística?

Un listado de restricciones evaluadas en el punto inicial, una desviación frente al default o un único IIS no bastan para contestar estas preguntas.

## 2. Decisión

Implementar un pipeline progresivo con clasificación estricta y evidencia explícita:

```text
clasificación operacional
  → validación estructural
  → certificado de Farkas / dual ray
  → relajación de factibilidad por familias
  → focalización dimensional
  → IIS irreducible del subconjunto sospechoso
  → explicación y cambios sugeridos
```

Las fases costosas sólo se ejecutan cuando la anterior no es concluyente o cuando el usuario solicita mayor detalle.

## 3. Clasificación obligatoria

Antes de cualquier IIS, persistir una de estas clases:

| Clase | Evidencia requerida | ¿Ejecutar IIS? |
|---|---|---|
| `OPTIMAL` | estado óptimo certificado | No |
| `INFEASIBLE_CERTIFIED` | `HighsModelStatus.kInfeasible` o equivalente | Sí |
| `UNBOUNDED_CERTIFIED` | estado unbounded y, si existe, primal ray | No |
| `NUMERICAL_FAILURE` | `kNotset`, `unknown`, error o inestabilidad | No |
| `RESOURCE_LIMIT` | time/iteration/objective limit | No |
| `CANCELLED` | cancelación confirmada | No |
| `OOM_OR_WORKER_LOSS` | telemetría de proceso/cgroup/worker | No |
| `MODEL_BUILD_ERROR` | fallo de datos, DataPortal, Pyomo o escritura LP | No |

Regla: sólo `INFEASIBLE_CERTIFIED` habilita IIS, Farkas y relajación de factibilidad.

## 4. Niveles de certeza

Cada hallazgo debe declarar `evidence_level`:

- `CERTIFIED`: estado del solver, dual ray/Farkas validado o IIS irreducible.
- `QUANTIFIED`: solución de relajación de factibilidad con slack reproducible.
- `STRUCTURAL`: regla determinista sobre datos/grafo, sin resolver el LP completo.
- `HEURISTIC`: ranking, desviación frente al default o aislamiento aproximado.

La UI no debe presentar evidencia heurística como “causa demostrada”.

## 5. Fase A — validación estructural

Extender `data_validation.py` sin mutar los datos originales. Reglas prioritarias:

1. Bounds `lower > upper`, incluyendo parámetros y bounds materializados de variables.
2. Demanda positiva sin ruta de producción.
3. Ruta tecnológica existente pero anulada por capacidad, `CapacityFactor`, `AvailabilityFactor`, vida útil o activity upper limits.
4. TIMESLICE demandado sin oferta disponible.
5. Mínimos de capacidad/actividad incompatibles con máximos.
6. Emisiones mínimas implícitas superiores al límite.
7. Reserve margin imposible.
8. UDC contradictorias o constantes incompatibles con signos de multiplicadores.
9. Storage sin carga/descarga/ciclo o con mínimo superior a capacidad.
10. En regional: región aislada, dirección de transmisión incorrecta o capacidad insuficiente.

### Grafo estructural

Construir por `(REGION, YEAR[, TIMESLICE])` un grafo dirigido:

```text
fuel de entrada → tecnología/modo → fuel de salida
```

La transmisión regional se representa como aristas entre regiones. El análisis de reachability detecta ausencia de ruta; un análisis de capacidad agregada aporta una cota necesaria, pero debe etiquetarse `STRUCTURAL`, no como prueba LP general.

## 6. Fase B — dual ray / certificado de Farkas

Para un LP certificado infactible:

1. Consultar `getDualRayExist()` y `getDualRay()`.
2. Mapear coeficientes no nulos a nombres de filas LP.
3. Verificar numéricamente el certificado antes de persistirlo.
4. Reportar filas dominantes por contribución normalizada, no sólo por valor absoluto del multiplicador.
5. Usarlo como semilla para focalizar familias, años y regiones.

HiGHS 1.15.1 devolvió un dual ray válido en el caso sintético `x >= 1`, `x <= 0` y en el conflicto regional real `OR_MINBAG/2050` del escenario 37. `solver=choose` puede resolver con IPM/presolve y dejar `has_ray=False`; para solicitar Farkas se usa simplex con `OSEMOSYS_DUAL_RAY_TIME_LIMIT_SECONDS`. Si no hay ray dentro del budget, se reporta como no disponible, nunca como certificado.

## 7. Fase C — relajación de factibilidad

Crear una copia diagnóstica o usar `Highs.feasibilityRelaxation`; nunca persistirla como solución del escenario.

Objetivo conceptual:

```text
min Σ penalización_i × slack_normalizado_i
```

### Relajaciones permitidas

No todas las ecuaciones deben relajarse. Relajar principalmente restricciones de negocio:

- demanda/balance;
- capacidad e inversión;
- actividad anual y de horizonte;
- emisiones;
- reserve margin;
- UDC;
- transmisión;
- storage bounds/rates.

Las ecuaciones contables o definicionales deben tener penalización prohibitiva o permanecer rígidas; relajarlas puede ocultar el dato causal.

### Escalamiento

No sumar directamente PJ, GW, MtCO2 y valores adimensionales. Para cada fila usar una escala reproducible, por ejemplo:

```text
scale_i = max(1, |lower_i|, |upper_i|, norma_relevante_de_coeficientes)
slack_normalizado_i = slack_i / scale_i
```

Guardar siempre tanto slack físico como normalizado.

### Optimización jerárquica

1. Minimizar violación ponderada total.
2. Fijar el óptimo de fase 1 dentro de tolerancia.
3. Minimizar número de familias activas o una aproximación L1 ponderada.
4. Opcionalmente minimizar número de filas dentro de las familias seleccionadas.

Esto evita proponer pequeñas relajaciones dispersas en miles de constraints cuando una corrección comprensible basta.

### Evidencia experimental

`Highs.feasibilityRelaxation()` en 1.15.1:

- cuantificó slack 1 para `x >= 1`, `x <= 0`;
- cuantificó slack total 2 para dos conflictos independientes;
- respetó penalizaciones locales y permitió elegir entre relajar demanda o capacidad;
- dejó `model_status=kNotset` aunque `solution.value_valid=True`.

Por ello, la validez de la relajación debe comprobarse por retorno, `solution.value_valid` y recomputación explícita de slacks; no por `model_status` posterior.

## 8. Fase D — IIS

Usar `IisStrategy.kIisStrategyIrreducible` en highspy 1.15.1. No llamar IIS al resultado de `iis_strategy=2`: experimentalmente puede contener conflictos independientes.

Requisitos:

- validar `readModel()` y `run()`;
- exigir `HighsModelStatus.kInfeasible`;
- conservar `row_bound_`, `col_bound_` y status asociados;
- fijar `iis_time_limit`;
- registrar número de LPs auxiliares, tiempo e iteraciones;
- distinguir IIS completo, timeout e IIS no disponible;
- explicar que un IIS es una causa mínima, no necesariamente la única.

Para múltiples causas, repetir sobre copias con exclusiones controladas sólo bajo budget. No prometer enumeración exhaustiva.

## 9. Focalización para modelos regionales

No ejecutar de entrada un IIS sobre ~2.2 millones de filas. El benchmark confirmó que el IIS global del escenario 37 excedió el budget aun con LP de 758 MB; el IIS sobre el LP focalizado de dos filas fue irreducible en menos de 1 ms.

Orden recomendado:

1. Validación estructural global.
2. Dual ray y agregación por familia/región/año.
3. Relajación con penalizaciones por familia.
4. Seleccionar regiones/años/familias con slack o contribución.
5. Construir un LP diagnóstico focalizado que preserve las conexiones necesarias.
6. Ejecutar IIS irreducible sobre ese subconjunto.

La búsqueda por desactivación de familias es heurística y debe operar sobre una copia. Debe registrar exactamente qué familias se retiraron.

## 10. Mapeo constraint → parámetros

El mapa debe distinguir:

- `business_constraint`: candidato a relajación y explicación directa;
- `accounting_constraint`: ecuación intermedia que debe rastrearse hasta su upstream;
- `cost_constraint`: normalmente no causal, salvo dominios/signos incompatibles;
- `storage_constraint`;
- `udc_constraint`.

Inventario inicial: 73 componentes `Constraint`, 20 mapeados y 53 sin mapa. Prioridades:

1. Corregir índices de LU3/LU4: el modelo usa dos índices YEAR.
2. Mapear `PlannedMaintenance`.
3. Mapear las ecuaciones intermedias de reserve margin.
4. Mapear contabilidad de emisiones para atravesarlas hasta ratios/límites.
5. Mapear todas las restricciones de storage.
6. Mantener coste/contabilidad con una clasificación explícita aunque no sean relajables.

Cada parámetro enlazado debe incluir archivo, dimensiones, valor, default efectivo versionado y, cuando sea posible, fila/origen de importación.

## 11. Contrato JSON propuesto

```json
{
  "classification": {
    "code": "INFEASIBLE_CERTIFIED",
    "evidence_level": "CERTIFIED",
    "solver_status": "kInfeasible"
  },
  "budgets": {
    "elapsed_seconds": 0,
    "time_limit_seconds": 300,
    "memory_limit_bytes": null,
    "timed_out": false,
    "cancelled": false
  },
  "structural_findings": [],
  "certificate": {
    "type": "dual_ray",
    "validated": true,
    "rows": []
  },
  "feasibility_relaxation": {
    "objective": 0,
    "normalization": "row_scale_v1",
    "relaxations": []
  },
  "iis": {
    "available": true,
    "irreducible": true,
    "constraints": [],
    "variable_bounds": []
  },
  "explanations": [],
  "reproducibility": {
    "highs_version": "1.15.1",
    "lp_sha256": "...",
    "defaults_version_id": null
  }
}
```

No guardar rutas absolutas internas ni credenciales en el JSON público.

## 12. Progreso, cancelación y budgets

Fases de progreso separadas:

```text
classify → structural → dual_ray → elastic → focus → iis → explain → persist
```

- Comprobar cancelación entre fases.
- Para interrumpir una llamada nativa larga, ejecutar el análisis costoso en un proceso hijo con timeout y terminación explícita; la bandera cooperativa de Celery no basta.
- Presupuesto inicial propuesto para pruebas: 300 s IIS y 300 s relajación; ajustar con benchmarks.
- Registrar RSS antes/después y tamaño LP.
- Nunca ejecutar dos diagnósticos regionales simultáneamente en el mismo ambiente.

## 13. Pruebas de aceptación

Fixtures mínimos:

1. Demanda sin productor.
2. Capacidad máxima cero con demanda positiva.
3. Mínimo de actividad mayor al máximo.
4. Límite de emisiones incompatible.
5. Reserve margin imposible.
6. UDC contradictorias.
7. Región aislada.
8. Transmisión insuficiente.
9. Storage incompatible.
10. Modelo factible sin falsos positivos.
11. Modelo no acotado con primal ray.
12. `kNotset`/fallo numérico sin ejecución de IIS.
13. Dos conflictos independientes para comprobar que un IIS no se presenta como explicación exhaustiva.
14. Conflicto directo de bounds para preservar lados LB/UB.

Cada fixture debe declarar la causa esperada, magnitud de relajación y nivel de evidencia.

## 14. Estado de implementación

Implementado:

- clasificación estricta del resultado;
- dual ray/Farkas con validación independiente;
- primal ray para no acotación;
- relajación de factibilidad normalizada y ponderada;
- IIS irreducible con timeout y detección de resultado parcial;
- análisis estructural de demanda/productores, bounds, TradeRoute y storage;
- progreso/cancelación entre fases;
- contrato API y visualización frontend;
- fixtures pequeños de capacidad, emisiones, reserve margin, UDC y regional estructural.

Pendiente de operación, no de diseño:

- benchmark autorizado sobre una copia regional grande;
- calibrar budgets y penalizaciones con datos reales;
- ejecutar el pipeline nativo en proceso hijo si se requiere cancelación dura durante una llamada C++;
- incorporar TradeRoute al modelo de optimización si se decide activar comercio/transmisión explícita.

## 15. Consecuencias

### Positivas

- Separa fallos operativos de infactibilidad matemática.
- Produce cambios cuantificados y reproducibles.
- Escala mejor al focalizar antes del IIS.
- Comunica la incertidumbre y evita falsas afirmaciones causales.

### Costes/riesgos

- Requiere catálogo completo de constraints y unidades.
- La relajación ponderada depende de una política de penalizaciones versionada.
- Un IIS irreducible puede seguir siendo costoso en regional.
- Enumerar todas las causas puede ser combinatorio; no será garantía del sistema.
