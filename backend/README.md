# OSEMOSYS Backend Técnico (FastAPI + Pyomo + Celery)

Guía E2E complementaria: [README_E2E.md](../README_E2E.md).
Guía backend local sin Docker: [docs/LOCAL_BACKEND_SIN_DOCKER.md](../docs/LOCAL_BACKEND_SIN_DOCKER.md).
Arquitectura C4 y mapa de módulos: `docs/ARCHITECTURE.md`.
Post-procesamiento de factores de empleo: `docs/EMPLOYMENT_FACTORS.md`.

---

## Variables de entorno

El backend se ejecuta con `backend/.env` (no se usa `backend/.env.example`).

Si vienes de una versión anterior con `backend/.env.example`, elimínalo y deja únicamente `backend/.env`.

---

## Artefactos locales (no subir)

Durante ejecución local/simulaciones se generan archivos transitorios. No deben versionarse.

| Ruta | Contenido |
|------|-----------|
| `backend/tmp/local/` | SQLite local, `simulation_result.json`, `simulation_kpis.csv`, `simulation_events.csv`, `charts/*.png`, `tables/*.csv` |
| `backend/tmp/simulation-results/` | `simulation_job_<id>.json` |
| `backend/tmp/local/parity/` | salidas de paridad CLI vs Docker |
| `backend/tmp/local/comparison_csvs/` | CSV temporales de comparación |

Estos paths están protegidos por `.gitignore`.

---

## 1. Descripción General del Proyecto

Este backend implementa un sistema de ejecución de escenarios energéticos con enfoque **DB-first** para OSEMOSYS, donde los insumos del modelo se gestionan en PostgreSQL y las corridas se ejecutan asíncronamente vía cola.

- **Problema que resuelve**: ejecutar optimizaciones energéticas multiusuario sin bloquear la API, preservando trazabilidad y control operacional.
- **Qué hace el sistema**:
  - gestiona escenarios e insumos;
  - encola simulaciones;
  - ejecuta modelo de optimización;
  - persiste artefactos y progreso;
  - expone resultados por API.
- **Tipo de modelo**: formulación **LP** implementada en Pyomo, inspirada en estructura OSEMOSYS y extendida por bloques (core, emisiones, reserve margin, RE target, storage, UDC).
- **Público objetivo**: desarrolladores backend, modeladores energéticos, ingenieros de optimización y equipo de operación on-prem.

---

## 2. Arquitectura del Sistema

### Diagrama lógico (explicado en texto)

1. Cliente solicita `POST /api/v1/simulations`.
2. FastAPI valida permisos y límites de ejecución.
3. Se crea `simulation_job` en BD (`QUEUED`) y se envía tarea a Celery/Redis.
4. Worker consume tarea, ejecuta pipeline OSEMOSYS y escribe artefacto JSON.
5. API expone estado (`/simulations/{id}`), logs (`/logs`) y resultados (`/result`).

### Componentes

- **Backend API**: FastAPI (`app/main.py`, routers en `app/api/v1`).
- **Persistencia**: PostgreSQL con esquemas:
  - `osemosys` (modelo energético, jobs, parámetros);
  - `core` (usuarios/documentos).
- **Cola y ejecución concurrente**:
  - Redis como broker/backend Celery;
  - worker dedicado `simulation-worker`.
- **Motor de optimización**:
  - Pyomo + solver `appsi_highs` (HiGHS).

### Separación por capas

- **API**: validación HTTP, serialización y códigos de error.
- **Servicio**: reglas de negocio (permisos, límites por usuario, transición de estados).
- **Repositorio**: acceso a datos y consultas SQLAlchemy.
- **Motor de optimización**: `app/simulation/*` con bloques matemáticos.

---

## 3. Flujo de Ejecución de un Escenario

1. **Usuario crea escenario**
   - Endpoint: `app/api/v1/scenarios.py`
   - Regla negocio: `app/services/scenario_service.py`

2. **Se almacenan parámetros**
   - Base general: `osemosys.parameter_value`
   - Parámetros multidimensionales OSEMOSYS: `osemosys.osemosys_param_value`
   - Modelo ORM: `app/models/parameter_value.py`, `app/models/osemosys_param_value.py`

3. **Se construye dataset OSEMOSYS**
   - Loader: `app/simulation/core/parameters_loader.py`
   - Transforma registros SQL a estructuras normalizadas (`DemandRow`, `SupplyRow`, mapas de parámetros).

4. **Se genera estructura de modelo (en memoria)**
   - Contexto: `app/simulation/core/sets_and_indices.py`
   - Variables y sets Pyomo: `app/simulation/core/variables.py`

5. **Se ejecuta solver**
   - Runner: `app/simulation/core/model_runner.py`
   - Solver actual: `pyo.SolverFactory("appsi_highs")`

6. **Se parsean resultados**
   - Extracción de variables de decisión y KPIs en `model_runner.py`.

7. **Se almacenan outputs**
   - Artefacto JSON en `tmp/simulation-results/simulation_job_<id>.json`.
   - Referencia en `simulation_job.result_ref`.
   - Consulta pública vía `GET /api/v1/simulations/{job_id}/result`.

### Dónde modificar cada etapa

- Ingesta/transformación de datos: `app/simulation/core/parameters_loader.py`
- Sets e índices: `app/simulation/core/sets_and_indices.py`
- Variables: `app/simulation/core/variables.py`
- Restricciones: `app/simulation/core/constraints_*.py`
- Objetivo: `app/simulation/core/objective.py`
- Progreso/logs/artefactos: `app/simulation/pipeline.py`

---

## 4. Implementación de OSEMOSYS (SECCIÓN CRÍTICA Y DETALLADA)

### 4.1 Versión de OSEMOSYS utilizada

- **Base conceptual**: formulación OSEMOSYS adaptada a implementación Pyomo.
- **Implementación concreta**: Python + Pyomo (no GNU MathProg directo).
- **Adaptaciones realizadas**:
  - diseño modular por bloques de restricciones;
  - ingestión DB-first (sin CSV/Excel);
  - restricciones proxy en storage/UDC para mantener factibilidad y escalabilidad inicial.

> Supuesto explícito: no se replica 1:1 toda la formulación canónica OSEMOSYS; se prioriza una versión operacional y extensible en backend productivo.

### 4.2 Estructura del Modelo

#### Sets (actuales)

- `SUPPLY` (índices de filas de oferta)
- `DEMAND_KEY` (`region`, `year`)
- `TECH_KEY` (`region`, `technology`, `year`)

Definidos en `app/simulation/core/variables.py`.

#### Parameters

Se cargan desde:
- `parameter_value` (base legado y demanda/oferta);
- `osemosys_param_value` (multidimensional).

Parámetros usados actualmente incluyen (normalizados por nombre):
- `ResidualCapacity`
- `CapacityFactor`
- `AvailabilityFactor`
- `CapacityToActivityUnit`
- `TotalAnnualMaxCapacity`
- `TotalAnnualMaxCapacityInvestment`
- `VariableCost`
- `CapitalCost`
- `FixedCost`
- `EmissionActivityRatio`
- `AnnualEmissionLimit`
- `ReserveMargin`
- `REMinProductionTarget`
- `RETagTechnology`
- `TechnologyToStorage`
- `TechnologyFromStorage`
- `UDCConstant`

#### Variables de decisión

- `dispatch[s] >= 0`
- `unmet[d] >= 0`
- `new_capacity[t] >= 0`
- `annual_emissions[d] >= 0`
- `reserve_margin_gap[d] >= 0`
- `re_target_gap[d] >= 0`

#### Función objetivo

Minimiza:
- costo variable de despacho;
- costo de inversión;
- costo fijo;
- penalización por demanda no servida;
- penalización por brecha de reserve margin;
- penalización por brecha de RE target;
- penalización de emisiones.

Implementada en `app/simulation/core/objective.py`.

#### Restricciones principales

- **Core** (`constraints_core.py`)
  - cota por fila de despacho (`DispatchRowCap`);
  - capacidad por tecnología-año-región;
  - límite máximo de capacidad total y nueva;
  - balance demanda con variable de déficit.
- **Emisiones** (`constraints_emissions.py`)
  - definición de emisiones anuales;
  - tope anual de emisiones.
- **Reserve/RE** (`constraints_reserve_re.py`)
  - cumplimiento de reserva con variable de brecha;
  - cumplimiento de target renovable con variable de brecha.
- **Storage** (`constraints_storage.py`)
  - restricción proxy activada si existen parámetros de storage.
- **UDC** (`constraints_udc.py`)
  - restricción proxy por `UDCConstant`.

### 4.3 Cómo se construyen los datos de entrada

Origen:
- SQLAlchemy `select` sobre `parameter_value`, `osemosys_param_value`, catálogos (`parameter`, `technology`, `fuel`).

Transformación:
- normalización de nombres de parámetro (`lower` alfanumérico);
- agregación por claves multidimensionales;
- asignación de costos por fallback regional/anual cuando falta costo específico.

Validaciones actuales:
- coerción a `float`;
- truncado de valores negativos en demanda/oferta a no-negativos en loader.

Supuestos implícitos relevantes:
- parámetros faltantes usan defaults operativos (`1.0`, `0.0` o `inf` según caso);
- varias restricciones avanzadas están aproximadas (proxy), no completamente expandida la estructura temporal canónica.

### 4.4 Personalizaciones del Modelo

- **Penalizaciones explícitas**:
  - `unmet_penalty = 1000`
  - `reserve_gap_penalty = 500`
  - `re_gap_penalty = 500`
- **Simplificaciones**:
  - storage y UDC implementados como restricciones proxy;
  - emisiones agregadas por (`region`, `technology`, `year`) con simplificación sobre modos/emisiones.
- **Cotas numéricas de estabilidad**:
  - `dispatch <= 5 * base_value` para evitar explosión numérica.

### 4.5 Cómo modificar el modelo

#### Agregar una nueva tecnología

1. Crear registro en catálogo `technology`.
2. Cargar `parameter_value` y/o `osemosys_param_value` asociados.
3. Verificar que el loader mapea la nueva dimensión correctamente (`parameters_loader.py`).
4. Re-ejecutar corrida y validar resultados en `/simulations/{id}/result`.

#### Modificar una restricción

1. Ubicar bloque correspondiente en `app/simulation/core/constraints_*.py`.
2. Ajustar ecuación Pyomo y mantener nombres de constraints descriptivos.
3. Ejecutar benchmark de paridad (`scripts/validate_simulation_parity.py`).

#### Prueba final (notebook vs app)

Para comparar resultados con el notebook UPME (`osemosys_notebook_UPME_OPT_01.ipynb`) usando el escenario **"Escenario prueba final"**:

1. **Comprobar que todo da igual (dos corridas idénticas):**
   ```bash
   docker compose exec api python scripts/run_parity_test.py
   ```
   Ejecuta dos veces la simulación del escenario "Escenario prueba final" y compara; sale con 0 si los resultados son idénticos.

2. **Generar resultado para comparar con el notebook:**  
   `python scripts/run_prueba_final.py` (genera `tmp/prueba_final_result.json`).

3. **Comparar con referencia del notebook:**  
   `python scripts/compare_results.py --ref referencia_notebook.json --actual tmp/prueba_final_result.json`.

Detalle completo: [PRUEBA_FINAL.md](../docs/PRUEBA_FINAL.md).

#### Cambiar horizonte temporal

1. Ajustar datos `year` en insumos del escenario.
2. Verificar cobertura de parámetros por año requerido.
3. Validar crecimiento de cardinalidad y tiempo de solve.

#### Agregar nueva variable

1. Declarar variable en `variables.py`.
2. Integrarla en constraints y en objetivo (si aplica).
3. Exportarla en `model_runner.py` para observabilidad y artefacto.

#### Ajustar función objetivo

1. Modificar `objective.py`.
2. Documentar unidades y signo de nuevos términos.
3. Actualizar benchmarks y tolerancias.

### 4.6 Solver

- **Solver actual**: HiGHS vía `appsi_highs`.
- **Motivación**: rendimiento robusto para LP/MILP grandes y despliegue sencillo en contenedor Python.
- **Parámetros actuales**: ejecución default (sin tuning avanzado explícito en código).
- **Naturaleza de carga**: fuertemente **CPU-bound** durante `solve`; I/O-bound principalmente en carga/escritura de datos y artefactos.

Cómo cambiar de solver:
1. Reemplazar `pyo.SolverFactory("appsi_highs")` en `model_runner.py`.
2. Agregar dependencia/binario del nuevo solver al contenedor.
3. Revalidar factibilidad, tiempos y tolerancias numéricas.

### 4.7 Consideraciones de rendimiento

- Complejidad crece con:
  - número de filas de oferta (`SUPPLY`);
  - años activos;
  - tecnologías por región;
  - bloques adicionales activados (emisiones, reserve/RE, storage, UDC).
- Cuellos de botella típicos:
  - solve LP;
  - cardinalidad de constraints al aumentar granularidad temporal.
- Impacto esperado:
  - más tecnologías y periodos incrementan tamaño del problema casi lineal/superlineal según combinaciones dimensionales;
  - constraints proxy actuales evitan crecimiento explosivo en storage/UDC, pero reducen fidelidad teórica.

### 4.8 Riesgos y limitaciones actuales

- No toda la formulación OSEMOSYS canónica está implementada 1:1.
- Storage y UDC están en versión proxy (riesgo de desviación conceptual).
- Defaults operativos pueden ocultar faltantes de data.
- Resultado depende de consistencia semántica de `param_name` en `osemosys_param_value`.
- Tuning de solver aún básico (sin estrategia avanzada por tamaño de instancia).

---

## 5. Base de Datos

### Tablas relevantes para modelado y ejecución

- **Escenarios e insumos**:
  - `osemosys.scenario`
  - `osemosys.parameter_value`
  - `osemosys.osemosys_param_value`
- **Catálogos**:
  - `parameter`, `region`, `technology`, `fuel`, `emission`, `solver`
  - sets OSEMOSYS: `timeslice`, `mode_of_operation`, `season`, `daytype`, `dailytimebracket`, `storage_set`, `udc_set`
- **Ejecución**:
  - `osemosys.simulation_job`
  - `osemosys.simulation_job_event`
- **Paridad/benchmark**:
  - `osemosys.simulation_benchmark`

### Mapeo al modelo

- `parameter_value` alimenta demanda/oferta base.
- `osemosys_param_value` alimenta parámetros multidimensionales por `param_name` + dimensiones + año.
- `simulation_job*` soporta orquestación y observabilidad operacional.

---

## 6. Concurrencia y Control de Ejecución

- Límite por usuario: `SIM_USER_ACTIVE_LIMIT` (default `1`) validado en servicio.
- Concurrencia global de workers: `SIM_MAX_CONCURRENCY` (default `3`) aplicada en comando Celery del contenedor worker.
- Estados de job: `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`.
- Cancelación cooperativa:
  - bandera `cancel_requested`;
  - chequeos explícitos entre etapas y sub-etapas del pipeline.

Protección del servidor:
- desacoplar API de carga pesada mediante cola;
- evitar ejecución síncrona en request thread;
- persistir progreso para visibilidad del frontend.

---

## 7. Manejo de Errores

- Si falla solver o pipeline:
  - `simulation_job.status = FAILED`
  - se persiste `error_message`
  - se agrega evento `ERROR` en `simulation_job_event`.
- Si modelo infactible:
  - se reporta en `solver_status` (terminación solver) y debe tratarse como resultado inválido para negocio.
- Si artefacto no existe:
  - `GET /simulations/{job_id}/result` devuelve error controlado (`404`).
- Si usuario no tiene acceso al escenario/job:
  - `403` o `404` según contexto.

---

## 8. Extensibilidad

- Para nuevas funcionalidades:
  - mantener separación API/Service/Repository/SimulationCore;
  - agregar bloque de modelo en `app/simulation/core` en lugar de monolito.
- Para escalar horizontalmente:
  - escalar `simulation-worker` por réplicas;
  - usar Redis gestionado y ajustar `SIM_MAX_CONCURRENCY`.
- Para desacoplar motor:
  - extraer `app/simulation` a microservicio de optimización;
  - mantener contrato por `simulation_job` + artefactos + eventos.

---

## 9. Buenas Prácticas para el Equipo Futuro

- No modificar directamente contratos API sin versionar schemas.
- Antes de cambiar restricciones:
  - validar unidades;
  - revisar impacto en factibilidad;
  - correr benchmark de paridad numérica.
- No introducir defaults silenciosos adicionales sin documentarlos.
- Mantener trazabilidad de cambios de formulación en documentación técnica.
- Revisar impacto de cambios sobre:
  - tiempos de solve;
  - consumo de memoria;
  - estabilidad numérica.

---

## 10. Roadmap Técnico Sugerido

1. **Paridad matemática completa OSEMOSYS**
   - reemplazar restricciones proxy de storage/UDC por formulación completa.
2. **Validación robusta**
   - ampliar benchmarks (2-3 escenarios de referencia adicionales).
3. **Tuning solver**
   - parametrizar tolerancias, time limits y estrategias por tamaño de instancia.
4. **Observabilidad**
   - métricas Prometheus (tiempo cola, tiempo solve, fallas por tipo).
5. **Microservicio de optimización**
   - separar motor del API para despliegue y escalado independientes.
6. **Gobernanza de datos de entrada**
   - validadores semánticos por `param_name` y cardinalidad esperada.

---

## Operación rápida (Docker)

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed.py
```

Health:

```bash
curl http://localhost:8010/api/v1/health
```

## Operación rápida (sin Docker, SQLite local)

Desde la raíz del repo:

```powershell
.\scripts\setup-local.ps1
.\scripts\init-local-db.ps1
.\scripts\run-local-api.ps1
```

Variables y archivos clave para este modo:
- `backend/.env.local` (se crea desde `backend/.env.local.example`).
- `DATABASE_URL=sqlite:///./tmp/local/osemosys_local.db`
- `SIMULATION_MODE=sync` (ejecución local sin Redis/worker).

Health:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
```

### Ejecutar modelo local desde `../CSV` (sin BD/UPME)

Este flujo no requiere conexión al servidor UPME ni escenarios en base de datos.
Toma directamente los CSV en la carpeta `../CSV`, construye la instancia Pyomo y ejecuta el solver.

1. Activar entorno virtual e instalar dependencias (desde la raíz del repo):

```powershell
cd backend
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Ejecutar la simulación con HiGHS y guardar el resultado JSON:

```powershell
@'
import json
from pathlib import Path
from app.simulation.osemosys_core import run_osemosys_from_csv_dir

csv_dir = Path("../CSV").resolve()
result = run_osemosys_from_csv_dir(csv_dir, solver_name="highs")

out = Path("tmp/prueba_final_from_csv_result.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

print("solver_status:", result.get("solver_status"))
print("objective_value:", result.get("objective_value"))
print("coverage_ratio:", result.get("coverage_ratio"))
print("saved:", out.resolve())
'@ | python -
```

3. Verificar salida:
- Archivo: `backend/tmp/prueba_final_from_csv_result.json`
- Esperado: `solver_status: optimal`

Notas:
- Este flujo usa el pipeline `CSV -> DataPortal -> Pyomo -> HiGHS`.
- Los sets y parámetros en `../CSV` deben ser consistentes entre sí (por ejemplo, `YEAR.csv` vs `DaySplit.csv`, `TIMESLICE.csv` vs `Conversionl*.csv`).

Usuario seed:
- `seed / seed123`

Permisos del usuario seed:
- `can_manage_catalogs = true`
- `can_import_official_data = true`

Importación oficial de Excel (requiere `can_import_official_data`):

```bash
curl -X POST "http://localhost:8010/api/v1/official-import/xlsm/sheets" \
  -H "Authorization: Bearer <TOKEN>" \
  -F "file=@C:\Users\SGI SAS\OneDrive - SGI SAS\Documentos\UPME\SAND_04_02_2026.xlsm"
```

Luego importa una hoja específica:

```bash
curl -X POST "http://localhost:8010/api/v1/official-import/xlsm" \
  -H "Authorization: Bearer <TOKEN>" \
  -F "file=@C:\Users\SGI SAS\OneDrive - SGI SAS\Documentos\UPME\SAND_04_02_2026.xlsm" \
  -F "sheet_name=Parameters"
```

Crear escenario desde Excel (sin depender de seed):

```bash
curl -X POST "http://localhost:8010/api/v1/scenarios/import-excel" \
  -H "Authorization: Bearer <TOKEN>" \
  -F "file=@C:\Users\SGI SAS\OneDrive - SGI SAS\Documentos\UPME\SAND_04_02_2026.xlsm" \
  -F "sheet_name=Parameters" \
  -F "scenario_name=Escenario 2026 (Excel)" \
  -F "edit_policy=OWNER_ONLY"
```

### Formato esperado del Excel (SAND matriz por año)

El importador soporta hojas tipo **matriz** (por ejemplo `Parameters` / `Hoja1`) donde cada fila describe un parámetro y las columnas de años contienen los valores.

- **Encabezados mínimos**:
  - `Parameter` (obligatorio)
  - Columnas de **años** (ej. `2018`, `2019`, `2020`...)
- **Dimensiones opcionales** (pueden estar vacías según aplique):
  - `REGION`, `TECHNOLOGY`, `FUEL`, `EMISSION`
  - `TIMESLICE`, `MODE_OF_OPERATION`, `STORAGE`
  - `Time indipendent variables` (valor “sin año”)
- **Normalización**:
  - Se ignoran mayúsculas/minúsculas, acentos y espacios (ej. `Región`, `REGION`, `region` funcionan).
- **Reglas importantes**:
  - Celdas vacías se interpretan como **0**.
  - Para performance, valores **0** se omiten (no se insertan en BD).
  - Si existen catálogos faltantes (Regiones/Tecnologías/Combustibles/Emisiones/Timeslices/etc.) se crean automáticamente al importar.

Ejemplo mínimo (5–10 filas):

| Parameter | REGION | TECHNOLOGY | FUEL | EMISSION | TIMESLICE | MODE_OF_OPERATION | Time indipendent variables | 2020 | 2021 |
|---|---|---|---|---|---|---|---:|---:|---:|
| Demand | R1 |  |  |  |  |  |  | 100 | 105 |
| CapitalCost | R1 | TECH_A |  |  |  |  |  | 1200 | 1180 |
| VariableCost | R1 | TECH_A |  |  |  |  |  | 12.5 | 12.7 |
| EmissionActivityRatio | R1 | TECH_A |  | CO2 |  |  |  | 0.25 | 0.25 |
| AnnualEmissionLimit | R1 |  |  | CO2 |  |  |  | 5000 | 5000 |
