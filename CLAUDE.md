# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

OSeMOSYS UPME is a web application for running energy scenario optimizations (LP via Pyomo + HiGHS solver) and visualizing results as interactive charts. There are two simulation modes:

- **DB mode** (default): inputs and outputs live in PostgreSQL; no CSV/Excel files are used at runtime.
- **SAND/Excel mode**: simulation launched from an uploaded Excel file, without DB scenario data.

**Stack:**
- Backend: FastAPI + SQLAlchemy + Celery/Redis + Pyomo (`appsi_highs` solver)
- Frontend: React 19 + TypeScript + Vite + Highcharts v11
- DB: PostgreSQL (schemas: `osemosys`, `core`)

---

## Running the Project

### Docker (full stack)

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed.py
# Seed user: seed / seed123
curl http://localhost:8010/api/v1/health
```

### Local without Docker (SQLite, sync mode)

```powershell
.\scripts\setup-local.ps1
.\scripts\init-local-db.ps1
.\scripts\run-local-api.ps1
# Uses backend/.env.local — DATABASE_URL=sqlite:///./tmp/local/osemosys_local.db, SIMULATION_MODE=sync
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend tests

```bash
cd backend
pytest                            # all tests
pytest tests/test_visualization_configs.py   # single file
```

### Frontend checks

```bash
cd frontend
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
```

---

## Architecture

### High-level flow

```
User → React frontend
         → FastAPI (app/api/v1/)
              → Celery worker (simulation pipeline)
                   → Pyomo + HiGHS solver
                        → osemosys_output_param_value (PostgreSQL)
              → chart_service.py (reads DB, returns JSON)
         ← Highcharts (renders in browser)
```

### Backend layers

| Layer | Location |
|-------|----------|
| HTTP / routing | `backend/app/api/v1/` |
| Business rules | `backend/app/services/` |
| DB access | `backend/app/models/`, SQLAlchemy ORM |
| Optimization model | `backend/app/simulation/core/` |
| Visualization | `backend/app/visualization/` |

### Simulation pipeline

Entry: `POST /api/v1/simulations` → Celery task → `app/simulation/tasks.py` → `app/simulation/pipeline.py`

**Key modules in `app/simulation/core/`:**

| Module | Role |
|--------|------|
| `data_processing.py` | BD → CSVs (sets + params) OR Excel → CSVs; full pipeline including UDC setup |
| `model_definition.py` | `create_abstract_model(has_storage, has_udc)` — all sets, params, vars, constraints, objective |
| `instance_builder.py` | `build_instance()` — loads CSVs via Pyomo DataPortal, creates ConcreteModel |
| `solver.py` | `solve_model()` — runs HiGHS solver, returns results; `_run_infeasibility_diagnostics()` — basic constraint/bound checks on infeasible result |
| `results_processing.py` | Extracts solver output → writes to `osemosys_output_param_value` + JSON artefact |
| `excel_to_csv.py` | `generate_csvs_from_excel()` — converts Excel SAND file to CSVs |
| `mode_of_operation_normalize.py` | Normalizes MODE_OF_OPERATION values (scalar + series) |
| `osemosys_defaults.py` | OSeMOSYS default parameter values used by infeasibility analysis to compute deviations |
| `infeasibility_analysis.py` | IIS computation via HiGHS, constraint→parameter mapping, enriched diagnostics pipeline (`enrich_solution_dict`) |
| `data_validation.py` | Detects and reports data quality issues (bound conflicts, dead years). `DataQualityReport`, `BoundConflict`, `YearExclusion` dataclasses. `detect_bound_conflicts`, `detect_dead_years`, `validate_and_persist`, `apply_dead_year_exclusion`, `apply_bound_fix_numeric_precision`. Two entry paths: CSV-based (post-processing) and DB-based (`_db` suffix). |
| `constraint_diagnostics.py` | `diagnose_model_constraints(instance)` — pre-solve analysis of redundant/trivial constraints (EnergyBalanceEachTS5, etc.). Activated via env var `OSEMOSYS_CONSTRAINT_DIAGNOSTICS=1`. Emits structured report via logger. |

**Two simulation entry paths in `data_processing.py`:**
- `run_data_processing(db, scenario_id, csv_dir)` — DB path (main flow)
- `run_data_processing_from_excel(excel_path, csv_dir)` — Excel/SAND path (no DB required)

Both paths produce identical CSV structure consumed by `build_instance()`.

Outputs: `osemosys_output_param_value` (PostgreSQL) + JSON artefact at `tmp/simulation-results/simulation_job_<id>.json`.

---

## Chart / Visualization Architecture

This is where most active development happens. See also `backend/app/visualization/README.md`.

### Data flow

```
osemosys_output_param_value (PostgreSQL)
    → chart_service.py  (load → filter → aggregate → convert units → color)
    → FastAPI /visualizations endpoints  (Pydantic JSON)
    → frontend (HighchartsChart.tsx / CompareChart.tsx / CompareChartFacet.tsx / LineChart.tsx)
    → Highcharts charts (stacked bar or line)
```

### Backend visualization module (`backend/app/visualization/`)

| File | Role |
|------|------|
| `chart_service.py` | Core: `build_chart_data`, `build_comparison_data` (`group_by="year"`), `build_comparison_data_by_year_alt` (`group_by="scenario"`), `build_comparison_facet_data`, `build_comparison_line_data` (líneas totales), `build_pareto_data`, `build_recursos_vs_demanda_data`, `get_result_summary`; export helpers: `render_chart_visualization_bytes`, `render_comparison_facet_figure_bytes`, `render_comparison_by_year_bytes`, `render_pareto_chart_bytes`, `_render_table_image`, `chart_data_to_csv_bytes`, `chart_data_to_xlsx_bytes`, `export_raw_data_excel`, `export_all_charts_zip`. Also helpers consumed by the table view: `apply_period_years`, `apply_cumulative_series`, `filter_chart_series`, `filter_chart_categories`, `filter_chart_by_year_range`, `reorder_chart_series` |
| `configs.py` | Single-scenario chart registry (`CONFIGS` dict, ~60 entries): `variable_default`, `filtro`, `agrupar_por`, `color_fn`, title, flags. Also exports `TITULOS_VARIABLES_CAPACIDAD`, `NOMBRES_COMBUSTIBLES`, `PWR_TECH_ALIASES` (consolidation of PWR variants into a parent tech for the three main electric charts) and `CONFIGS_CON_ALIAS_PWR` |
| `configs_comparacion.py` | Multi-scenario comparison registry (`CONFIGS_COMPARACION`): `prefijo`, `agrupacion_*`, `año_historico_unico`. Also exports `MAPA_SECTOR` (prefix → sector name) and `COLORES_SECTOR` (sector color palette) |
| `colors.py` | Color logic: `COLORES_GRUPOS`, `COLORES_EMISIONES`, `FAMILIAS_TEC`, `COLOR_MAP_PWR`, `generar_colores_tecnologias`, `_color_electricidad`, `_color_por_grupo_fijo`, `_color_por_sector`, `_color_por_region`, `_color_transporte_grupo`, `_color_por_emision`, `asignar_grupo` |
| `labels.py` | `get_label(code)` — single technology/fuel display name; `get_labels_batch(codes)` — batch variant. 740+ entries in `DISPLAY_NAMES`; `_dynamic_label()` generates labels from code segments as fallback |
| `regional.py` | Adaptación al modo REGIONAL (7 regiones SIN: AN/CA/IN/NE/OR/SE/SO). `transform_regional_df` aplica 3 vistas (acumulado nacional, filtrar por región, agrupar por región); detecta transmisión interregional `TRN*_XX_YY` y la excluye; expone `REGION_LABELS`, `REGION_COLORS`, `REGIONAL_PREFIXES`, `extract_region`, `strip_region` |
| `chart_menu.py` | `MENU` structure (modules → subsectors → chart items) used by catalog sync and frontend |
| `catalog_sync.py` | Sync `MENU` / `CONFIGS` into the DB chart catalog table |
| `catalog_reader.py` | Read chart catalog from DB for API responses |
| `data_explorer_filters.py` | Filter-option queries for the Result Data Explorer wide-table endpoint |

### Related services (outside `visualization/`)

| File | Role |
|------|------|
| `app/services/chart_series_config_service.py` | CRUD + populate de `chart_series_config` (orden global, colores, alias, oculto). `apply_global_series_config()` se llama desde `build_chart_data` para inyectar la configuración admin en el render |
| `app/services/result_table_template_service.py` | CRUD de plantillas globales de tablas que aparecen en `ResultDetailPage` |
| `app/services/result_table_presentation_options.py` | Deriva candidatos de series/categorías a partir del catálogo OSeMOSYS (sin job concreto) para el editor admin de tablas |
| `app/result_table_seeds.py` | Filas semilla con `seed_key` (upsert idempotente vía Alembic) |

### API endpoints (`backend/app/api/v1/visualizations.py`)

| Endpoint | Purpose |
|----------|---------|
| `GET /visualizations/chart-catalog` | Available chart types (incluye `soporta_pareto` y `data_explorer_filters`) |
| `GET /visualizations/{job_id}/chart-data?tipo=&un=&region=&timeslice=` | Single-scenario chart. `region` solo aplica a jobs REGIONAL; `timeslice` filtra a un TS específico (default = agregación anual) |
| `GET /visualizations/{job_id}/timeslices` | Códigos de TS presentes en el job (alimenta el selector de timeslice) |
| `GET /visualizations/chart-data/compare?job_ids=&tipo=&years_to_plot=&group_by=` | Multi-scenario por año (`group_by="year"`, default) o por escenario (`group_by="scenario"` → modo "alt") |
| `GET /visualizations/chart-data/compare-facet?job_ids=&tipo=&region=` | Multi-scenario facets |
| `GET /visualizations/chart-data/compare-line?job_ids=&tipo=` | Comparación "líneas totales" (una línea por escenario, sin desglose por serie) |
| `GET /visualizations/{job_id}/pareto-data?tipo=` | Datos Pareto (barras + % acumulado) |
| `GET /visualizations/{job_id}/result-summary` | KPI header (incluye `reserve_margin_dual`, `scenario_tag`, `is_infeasible_result`) |
| `GET /visualizations/{job_id}/export-chart?tipo=&formato=&view_mode=` | Export individual server-side; soporta `view_mode` en {`column`, `line`, `area`, `pareto`, `table`} y `formato` en {`png`, `svg`, `csv`, `xlsx`} |
| `GET /visualizations/{job_id}/export-all` | ZIP de SVG/PNG (Matplotlib headless) |
| `GET /visualizations/{job_id}/export-raw` | Excel dump de filas crudas |
| `GET /visualizations/{job_id}/export-csv-bundle` | Bundle de CSVs por chart |
| `GET /visualizations/export-compare-facet?job_ids=&tipo=&formato=` | Export facet comparison (PNG/SVG) |

All endpoints require authentication; chart-data endpoints require `SUCCEEDED` job status. Comparison is capped at **10 jobs**. Si el job es REGIONAL (`simulation_job.simulation_type='REGIONAL'`), `chart_service` llama a `regional.transform_regional_df` antes del groupby.

### chart_service internals

`_load_variable_data` has two paths:
- **Typed variables** (`Dispatch`, `NewCapacity`, `UnmetDemand`, `AnnualEmissions`): use typed DB columns directly.
- **Intermediate variables** (everything else): parse `index_json` using position heuristics for 3/4/5-element indices. Malformed indices produce empty/partial charts.
- `Dispatch` ahora preserva la dimensión TIMESLICE (columna `TIMESLICE`) — necesaria para el filtro por TS en el chart-data.

Unit conversion (`_convertir_unidades`): PJ is the baseline. GW, MW, TWh, Gpc apply fixed multipliers.

After computing colors and series, `build_chart_data` invoca `apply_global_series_config(db, tipo, agrupar_por, …)` (en `chart_series_config_service`) para **filtrar series ocultas, reordenar y aplicar colores/aliases admin** definidos en la tabla `chart_series_config`.

### Frontend chart components (`frontend/src/shared/charts/`)

| Component | Mode |
|-----------|------|
| `HighchartsChart.tsx` | Single scenario — stacked bar, all years on X-axis |
| `LineChart.tsx` | Single scenario — line/area mode; soporta synthetic series y `chart_type` por serie |
| `CompareChart.tsx` | Multi-scenario por año (`by-year` / `by-year-alt`). En `by-year-alt` los subplots son los escenarios y las barras son los años seleccionados |
| `CompareChartFacet.tsx` | Multi-scenario facets — un chart completo por escenario |
| `ParetoChart.tsx` | Single/compare — bars by category + cumulative % line (dual Y-axis) |
| `ChartDataTable.tsx` | View mode `table` — renderiza el `ChartDataResponse` como tabla HTML; espeja `apply_period_years`, `apply_cumulative_series`, `filter_chart_categories`, `reorder_chart_series` del backend para que el download server-side genere el mismo contenido |
| `SeriesOrderModal.tsx` | Modal para reordenar series manualmente (`customSeriesOrder` se persiste por chart/template) |
| `ChartSelector.tsx` | Controles: tipo, unidad, sub-filter, location, view mode (column/line/area/pareto/table), grouping (`AGRUPACION_OPTIONS`), bar orientation; soporta dropdown de Región (jobs REGIONAL) y selector de Timeslice cuando el job tiene 2+ TS |
| `ScenarioComparer.tsx` | Modo de comparación: `facet`, `by-year`, `by-year-alt`, `line-total` + selección de años |
| `SyntheticSeriesEditor.tsx` | UI para crear/editar series sintéticas (overlays) sobre line/area |
| `highchartsSetup.ts` | Highcharts global initialization (modules, options) |
| `chartExportingShared.ts` | Shared export utilities (PNG/SVG/CSV) for all chart types |
| `serverChartExport.ts` | Server-side export: llama `/export-chart` con `view_mode`, `period_years`, `cumulative`, etc. |
| `mergeFacetChartsSvg.ts` | Une SVGs de facets en un SVG combinado client-side |
| `chartLayoutPreferences.ts` | Persiste bar orientation / facet placement / facet legend mode en localStorage |
| `chartShareLink.ts` | Codifica/decodifica el estado de la gráfica en query string compartible |
| `defaultChartSelection.ts` | Selección por defecto al cargar la página |
| `techFamilies.ts` | Familias de tecnologías y mapping prefijo → familia |
| `chartLegendInteractions.ts` | Plotly-style: click = toggle, double-click = isolate/restore |
| `chartTooltips.ts` | Tooltip builders: `buildStackedTooltipOptions`, `buildLineTooltipOptions`, `buildStackedSinglePointTooltipOptions` |
| `syntheticSeriesStorage.ts` | localStorage persistence for synthetic series (clave = tipo+un+filtros+viewMode) |
| `numberFormat.ts` | `formatAxis3Sig` — formato uniforme de valores en ejes/tooltips/tablas |

The page component `ResultDetailPage.tsx` orchestrates API calls and routes to the correct chart component based on comparison mode and selected view mode (column/line/area/pareto/table). También obtiene las plantillas globales de tablas (`resultTableTemplatesApi`) y, si el usuario es Admin reportes, ofrece la pestaña de configuración de series.

### View modes and chart types

`ChartSelection.viewMode` controls the render path:
- `"column"` → `HighchartsChart` (stacked bars; soporta orientación vertical/horizontal)
- `"line"` / `"area"` → `LineChart` (line or area, supports synthetic series)
- `"pareto"` → `ParetoChart` (bars + cumulative % line); requires `soportaPareto: true` on the chart item in `MENU`
- `"table"` → `ChartDataTable` (matriz categorías × años; soporta `tablePeriodYears`, `tableCumulative`, `customSeriesOrder`, `yAxisMin`/`yAxisMax`)

Special chart ID sets in `ChartSelector.tsx` control unit/grouping behavior:
- `GEI_CHART_IDS` (`emisiones_total`, `emisiones_sectorial`, `emisiones_gei`) — emisión GEI con unidad intercambiable (MtCO₂eq ↔ ktCO₂eq)
- `CONTAMINANTES_CHART_IDS` (`emisiones_contaminantes`) — unidad fija `kt`, agrupación fija EMISION
- `PORCENTAJE_CHART_IDS` (`factor_planta`) — unidad fija %, sin selector de agrupación
- `CHARTS_SIN_AGRUPACION` — gráficos sin selector de agrupación (incluye `factor_planta`, `emisiones_*`, `h2_produccion_verde`)

Grouping options (`AGRUPACION_OPTIONS`): `TECNOLOGIA`, `FUEL`, `SECTOR`, `TRANSPORTE_GRUPO`, `REGION`. Además, `chart_service` soporta internamente `GROUP`, `EMISION`, `H2_PRODUCCION` y `YEAR` para configs específicas.

Cada `ChartItem` puede declarar `allowedGroupings` (subconjunto permitido) y `defaultGrouping`.

### Modos de comparación (multi-scenario)

`CompareViewMode` (`ScenarioComparer`):
- `facet` → un chart completo por escenario (`/compare-facet`)
- `by-year` → un subplot por año, escenarios en X (`/compare?group_by=year`, default)
- `by-year-alt` → un subplot por escenario, años en X (`/compare?group_by=scenario`)
- `line-total` → una línea por escenario (totales anuales, `/compare-line`)

### Synthetic series

Manual data overlays that appear on top of line charts. Defined via `SyntheticSeriesEditor.tsx`, stored in localStorage via `syntheticSeriesStorage.ts`. Each series has: name, color, data `[year, value][]`, lineStyle, markerSymbol, markerRadius, lineWidth, active flag, optional `chart_type` (`line`/`area`/`column`). Inactive series are hidden. Excel paste supported (single value, row, column, or 2-column matrix).

### Regional mode (`simulation_type='REGIONAL'`)

Cuando el job se ejecutó en modo REGIONAL, la columna `TECHNOLOGY` lleva un prefijo geográfico de 2 letras (p. ej. `AN_PWRDIST`). `chart_service` detecta esto vía `_is_regional_job(db, job_id)` y delega a `regional.transform_regional_df`, que aplica una de las 3 vistas:
1. **Acumulado nacional** (sin `region` y `agrupar_por != 'REGION'`) — quita prefijos para que el groupby colapse las 7 regiones.
2. **Filtro por región** (`region in {AN, CA, …, SO}`) — solo deja la región y quita el prefijo.
3. **Agrupar por región** (`agrupar_por='REGION'`) — la columna `REGION` se convierte en `COLOR`.

Las tecnologías interregionales (`TRN*_XX_YY`) se excluyen en las 3 vistas. El Result Data Explorer **no** transforma; muestra los códigos crudos.

### Adding a new single-scenario chart type

1. Add a filter function in `configs.py` (or reuse existing).
2. Add entry to `CONFIGS` with: `variable_default`, `filtro`, `agrupar_por`, `color_fn`, `titulo_base`, `figura_base`, `es_capacidad`, `es_porcentaje`.
3. If the chart supports sub-filters, register in `_config_has_sub_filtro` / `_config_sub_filtros` in `chart_service.py`.
4. Add a `ChartItem` entry to the correct `Module` or `Subsector` in `MENU` inside `ChartSelector.tsx` with the same `id`. Mark `soportaPareto: true` y/o `soportaTabla: false` cuando aplique. Declara `allowedGroupings`/`defaultGrouping` si corresponde.

### Adding a new comparison chart type

Add entry to `CONFIGS_COMPARACION` in `configs_comparacion.py` with `prefijo`, `agrupacion_default` or `agrupacion_fija`, `año_historico_unico`, `variable_default`. La agrupación acepta `FUEL` además de `COMBUSTIBLE` como sinónimo.

### Color rules

Colors are deterministic, keyed by technology family/group. To change a color, edit `colors.py` (`COLORES_GRUPOS` for fuel/sector groups, `COLOR_MAP_PWR` for electricity technologies, `COLORES_EMISIONES` for emission charts). Las regiones del SIN viven en `regional.REGION_COLORS`. Color changes affect all charts using that group; también se pueden sobreescribir admin-side vía `chart_series_config`.

---

## Series Configs y Plantillas de Tabla (admin reportes)

Dos sistemas globales que afectan cómo se rinde cada gráfica para **todos** los usuarios. Editables solo por usuarios con `is_admin_reports` o `can_manage_scenarios`. Se administran desde `ReportsPage` (pestañas "Series por gráfica" y "Tablas en resultados").

### `chart_series_config` — orden/color/oculto por serie

Tabla `osemosys.chart_series_config` (modelo `ChartSeriesConfig`). Una fila por (`tipo`, `agrupar_por`, `series_code`) con `display_name`, `color`, `hidden`, `sort_index`, `group_key`, `notes`. El servicio `chart_series_config_service.apply_global_series_config()` se llama dentro de `build_chart_data` y aplica los overrides después del color_fn. La normalización `agrupar_por` colapsa `COMBUSTIBLE → FUEL`.

Endpoints (prefijo `/chart-series-config`):
- `GET /chart-types` — lista de tipos disponibles (CONFIGS ∪ CONFIGS_COMPARACION).
- `GET ?tipo=&agrupar_por=` — filas de un chart.
- `POST /populate` y `POST /populate-all` — inicializa filas a partir del catálogo OSeMOSYS (no destructivo).
- `POST /row`, `PATCH /{id}`, `DELETE /{id}`, `POST /reorder`.

UI: `frontend/src/features/reports/components/ChartSeriesConfigTab.tsx` (también embebido en `ResultDetailPage` para admins).

### `result_table_template` — tablas globales en página de resultados

Tabla `osemosys.result_table_template` + hijos en `result_table_template_column`. Cada plantilla define los parámetros que un usuario seleccionaría manualmente (tipo, un, sub_filtro, loc, variable, agrupar_por, region, timeslice, table_period_years, table_cumulative, custom_series_order, y_axis_min/max). Las plantillas con `is_enabled=true` aparecen automáticamente en `ResultDetailPage` (sección "Tablas de resultados") para todos los usuarios.

Filas con `seed_key` se cargan vía `app/result_table_seeds.py` (upsert idempotente desde migraciones Alembic).

Endpoints (prefijo `/result-table-templates`):
- `GET ""` — plantillas habilitadas (todos los usuarios).
- `GET /manage`, `POST /reorder`, `GET /{id}`, `POST`, `PATCH /{id}`, `DELETE /{id}` — admin.
- `GET /presentation-options?tipo=&agrupar_por=&variable=` — series/categorías candidatas (admin).

UI: `frontend/src/features/reports/components/ResultTablesAdminTab.tsx`.

---

## UDC (User-Defined Constraints)

UDC is an OSeMOSYS extension that lets users define arbitrary linear constraints over technology capacity and activity. This section documents the full UDC pipeline.

### What UDC does

Each UDC constraint `u` has the form:

```
Σ_t [ UDCMultiplierTotalCapacity[r,t,u,y] * TotalCapacity[r,t,y]
    + UDCMultiplierNewCapacity[r,t,u,y]   * NewCapacity[r,t,y]
    + UDCMultiplierActivity[r,t,u,y]      * AnnualActivity[r,t,y] ]
  <= or = UDCConstant[r,u,y]
```

The type of constraint is controlled by `UDCTag[r,u]`:
- `0` → inequality (≤), constraint `UDC1_UserDefinedConstraintInequality`
- `1` → equality (=), constraint `UDC2_UserDefinedConstraintEquality`
- `2` (default) → skip — the constraint is not generated at all

### UDC parameters (model_definition.py)

| Parameter | Dimensions | Default | Description |
|-----------|-----------|---------|-------------|
| `UDCMultiplierTotalCapacity` | `REGION, TECHNOLOGY, UDC, YEAR` | 0 | Coefficient on total installed capacity |
| `UDCMultiplierNewCapacity` | `REGION, TECHNOLOGY, UDC, YEAR` | 0 | Coefficient on new capacity in that year |
| `UDCMultiplierActivity` | `REGION, TECHNOLOGY, UDC, YEAR` | 0 | Coefficient on annual activity |
| `UDCConstant` | `REGION, UDC, YEAR` | 0 | RHS constant of the constraint |
| `UDCTag` | `REGION, UDC` | 2 | Constraint type: 0=≤, 1==, 2=skip |

UDC parameters are only added to the model when `has_udc=True` in `create_abstract_model()`.

### UDC pipeline (data_processing.py)

The UDC pipeline always runs in steps 5–6 of `run_data_processing()`:

**Steps 5–6 — condicional**: Solo se ejecutan si `scenario.udc_config` está configurado y `enabled=True`. Helper `_load_enabled_udc_config(db, scenario_id)` lee el campo y retorna `None` si UDC está deshabilitado o no configurado.

**Step 5 — `ensure_udc_csvs(csv_dir)`**: Hardcodes `udc_list = ["UDC_Margin"]` y genera:
- `UDC.csv` con esa entrada
- `UDCMultiplierTotalCapacity.csv`, `UDCMultiplierNewCapacity.csv`, `UDCMultiplierActivity.csv` (ceros, cross-join con AvailabilityFactor)
- `UDCConstant.csv` (ceros), `UDCTag.csv` (valor 2 = skip por defecto)

**Step 6 — `apply_udc_config(udc_config: dict, csv_dir: str)`**: Recibe el config directamente (ya no lee BD) y llama `actualizar_UDCMultiplier` / `actualizar_UDCTag`. No tiene fallback — si no hay config, no se llama.

### `_UDC_RESERVE_MARGIN_DICT` (hardcoded in data_processing.py)

Dictionary mapping power technology codes to their UDC multiplier for the Reserve Margin constraint. Dispatchable techs get `-1.0` (reduce RHS); non-dispatchable (solar, run-of-river) get `0.0`; grid technology `GRDTYDELC` gets `(1/0.9) * 1.2`. This is the main UDC use case: effectively replacing OSeMOSYS's native Reserve Margin with a UDC formulation.

### `has_udc` detection

`has_udc` se establece en `True` en `ProcessingResult` solo cuando:
1. El escenario tiene `udc_config` configurado con `enabled: True`, y
2. `ensure_udc_csvs` + `apply_udc_config` se ejecutaron exitosamente.

Por defecto (`udc_config=None`) → `has_udc=False` → modelo sin restricciones UDC. En modo Excel/SAND, UDC siempre está deshabilitado (no hay escenario en BD).

### MUIO constraints (model_definition.py lines 1163–1209)

MUIO (LU1–LU4) are defined in the model but currently **not loaded** from CSVs in `instance_builder.py` (commented out). They constrain activity by mode per year (upper/lower bounds, year-over-year increase/decrease rates). To activate them, uncomment the corresponding `_load_param` calls in `instance_builder.py`.

---

## Infeasibility Analysis

When the solver returns an infeasible result, the system provides two levels of diagnosis: a fast basic check during the simulation pipeline and a richer on-demand IIS analysis triggered by the user afterwards.

### Components

| File | Role |
|------|------|
| `backend/app/simulation/core/infeasibility_analysis.py` | Core module: `CONSTRAINT_PARAM_MAP`, Pyomo name parsers, CSV param loader, HiGHS IIS computation (`try_compute_iis`), main pipeline (`analyze` / `enrich_solution_dict`) |
| `backend/app/simulation/core/solver.py` | `_run_infeasibility_diagnostics()` — basic constraint body vs bounds check + variable bound conflict detection; called inline when solve returns infeasible |
| `backend/app/simulation/core/osemosys_defaults.py` | OSeMOSYS default parameter values; used by infeasibility analysis to compute `diff_abs` and `deviation_score` |
| `backend/app/simulation/tasks.py` | Celery task `run_infeasibility_diagnostic_job(job_id)` — rebuilds Pyomo instance and calls `enrich_solution_dict`; handles cancellation |
| `backend/app/simulation/pipeline.py` | `_persist_critical_solver_metadata()` — saves basic diagnostics to DB immediately after infeasible solve |
| `backend/app/services/simulation_service.py` | `request_infeasibility_diagnostic()` / `cancel_infeasibility_diagnostic()` — enqueue / cancel the Celery analysis task |
| `backend/app/api/v1/simulations.py` | Three new endpoints (see table below) |
| `backend/app/models/simulation_job.py` | `run_iis_analysis: bool` — checkbox to auto-run IIS; `infeasibility_diagnostics_json` — stores full enriched result |
| `backend/app/schemas/simulation.py` | `IISReportPublic`, `ConstraintAnalysisPublic`, `ParamHitPublic`, `InfeasibilityOverviewPublic`, `InfeasibilityDiagnosticsPublic` |
| `frontend/src/pages/InfeasibilityReportPage.tsx` | Unified UI: overview card, top-suspects table, IIS-constraints tab, scenario-params tab with IIS badges, variable-bound-conflicts list, JSON download |
| `frontend/src/features/simulation/components/ScenarioParamsTab.tsx` | Shows IIS-membership badge next to parameters that appear in the active IIS |

### API endpoints (in `simulations.py`)

| Endpoint | Purpose |
|----------|---------|
| `POST /simulations/{job_id}/diagnose-infeasibility` | Queue on-demand enriched IIS analysis |
| `POST /simulations/{job_id}/cancel-diagnostic` | Cancel a running diagnosis |
| `GET /simulations/{job_id}/infeasibility-report` | Download full JSON diagnostic report |

### Two-level diagnosis flow

```
[solver.py] solve_model() returns "infeasible"
    └─ _run_infeasibility_diagnostics()
       ├─ Evaluate each constraint: body vs [lower, upper]
       ├─ Detect variable bound conflicts (LB > UB)
       └─ Return {constraint_violations, var_bound_conflicts}
           ↓
[pipeline.py] _persist_critical_solver_metadata()
    └─ Save basic_diagnostics to infeasibility_diagnostics_json

--- USER CLICKS "Analizar infactibilidad" ---

[API] POST /simulations/{id}/diagnose-infeasibility
    └─ [tasks.py] run_infeasibility_diagnostic_job()
       ├─ Rebuild Pyomo ConcreteModel from CSVs
       └─ [infeasibility_analysis.py] enrich_solution_dict()
          ├─ try_compute_iis(instance, "highs")
          │  ├─ Write LP file (symbolic_solver_labels=True)
          │  ├─ Load into highspy.Highs, set iis_strategy=2
          │  ├─ h.run() → h.getIis()
          │  └─ Return IISReport {constraint_names, variable_names}
          ├─ For each IIS constraint:
          │  ├─ parse_constraint_name() → (prefix, tokens)
          │  ├─ constraint_indices() → {REGION, YEAR, TECHNOLOGY, …}
          │  └─ values_for_constraint()
          │     ├─ CONSTRAINT_PARAM_MAP[prefix] → related params
          │     ├─ Load param CSVs, filter by indices
          │     ├─ Get OSeMOSYS default (osemosys_defaults.py)
          │     └─ Compute diff_abs + deviation_score (0–100)
          ├─ _build_overview() → {years, constraint_types, techs_or_fuels}
          ├─ _top_suspects(k=10) → rank by |diff_abs|
          └─ Persist enriched_diagnostics to DB
```

### `CONSTRAINT_PARAM_MAP` coverage

The static map covers 20 constraint types → OSeMOSYS parameters:

`EnergyBalanceEachTS5`, `EnergyBalanceEachYear4`, `ConstraintCapacity`, `TotalAnnualMaxCapacityConstraint`, `TotalAnnualMinCapacityConstraint`, `TotalAnnualMaxNewCapacityConstraint`, `TotalAnnualMinNewCapacityConstraint`, `TotalAnnualTechnologyActivityUpperlimit`, `TotalAnnualTechnologyActivityLowerlimit`, `TotalModelHorizonTechnologyActivityUpperLimit`, `TotalModelHorizonTechnologyActivityLowerLimit`, `AnnualEmissionsLimit`, `ModelPeriodEmissionsLimit`, `ReserveMarginConstraint`, `LU1`–`LU4` (TechnologyActivityByMode), `UDC1`–`UDC2` (User-Defined Constraints).

### Adding GLPK support

To replicate the IIS analysis for GLPK, the key integration point is `try_compute_iis()` in `infeasibility_analysis.py` (lines ~826–946). That function writes an LP file and calls HiGHS-specific APIs (`highspy.Highs`, `getIis()`). A GLPK path would need to:
1. Write the same LP file (Pyomo's `write()` already produces a solver-neutral LP).
2. Call `glpsol --lp <file> --wglp <output>` or use `pyglpk`/`cylp` to invoke GLPK's IIS routines.
3. Parse GLPK's output back into `{row_names, col_names}` and return the same `IISReport` dataclass.
The rest of the pipeline (constraint parsing, param mapping, deviation scoring) is solver-agnostic and requires no changes.

---

## Saved Charts & Reports System

Allows users to save chart configurations as reusable templates and assemble them into shareable reports with scenario assignments.

### Data model

| Model | File | Description |
|-------|------|-------------|
| `SavedChartTemplate` | `backend/app/models/saved_chart_template.py` | One saved chart config: tipo, un, sub_filtro, loc, variable, agrupar_por, view_mode, compare_mode, bar_orientation, facet_placement, facet_legend_mode, num_scenarios, years_to_plot, synthetic_series (JSONB), report_title, is_public |
| `ReportTemplate` | `backend/app/models/report_template.py` | Ordered collection of template IDs: items (JSONB), layout (JSONB category tree), scenario_aliases, default_job_ids, fmt (png/svg), is_public, is_official |
| `SavedChartTemplateFavorite` | `saved_chart_template_favorite.py` | User × template favorites |
| `ReportTemplateFavorite` | `report_template_favorite.py` | User × report favorites |

### Backend API (`backend/app/api/v1/saved_chart_templates.py`)

| Endpoint | Purpose |
|----------|---------|
| `GET /saved-chart-templates` | List user's + public templates |
| `POST /saved-chart-templates` | Create template (detects exact duplicates) |
| `PATCH /saved-chart-templates/{id}` | Update name/description/is_public/report_title/view_mode |
| `DELETE /saved-chart-templates/{id}` | Delete (owner only) |
| `POST /saved-chart-templates/report` | Generate ZIP with PNG/SVG per template × scenario |
| `PATCH /saved-chart-templates/{id}/favorite` | Toggle favorite |
| `POST /saved-chart-templates/{id}/copy` | Clone as private copy |
| `GET /saved-reports` | List reports |
| `POST /saved-reports` | Create report |
| `PATCH /saved-reports/{id}` | Update (tri-state: absent=no-change, null=reset, value=set) |
| `DELETE /saved-reports/{id}` | Delete (owner or admin) |
| `POST /saved-reports/{id}/copy` | Clone (also clones inaccessible templates) |

### Frontend pages & components

| File | Purpose |
|------|---------|
| `frontend/src/pages/ReportsPage.tsx` | 3-tab page: "Mis gráficas guardadas" (CRUD templates) / "Generador de reportes" (assemble + export) / "Mis reportes" (saved reports) |
| `frontend/src/pages/ReportDashboardPage.tsx` | View/edit a saved report: render all charts with scenario bindings, reorder, export ZIP |
| `frontend/src/features/reports/components/SaveChartModal.tsx` | Save current chart view as template; auto-detects duplicates |
| `frontend/src/features/reports/components/ChartPickerModal.tsx` | Select a template to add/replace in a report; filter by compare_mode compatibility |
| `frontend/src/features/reports/components/DashboardChartCard.tsx` | Render a single template in a report dashboard: fetches data, applies aliases, renders correct chart type |
| `frontend/src/features/reports/components/CategoriesPanel.tsx` | Organize charts into category/subcategory tree |
| `frontend/src/features/reports/components/RowScenarioPicker.tsx` | Per-chart job picker (override which global scenario slot) |
| `frontend/src/features/reports/scenarioMemory.ts` | Persist scenario slot assignments to localStorage |
| `frontend/src/features/reports/layout.ts` | Compute/reconcile category structure for export |
| `frontend/src/features/reports/pickRepresentativeJob.ts` | Choose representative job for chart preview |
| `frontend/src/features/reports/api/savedChartsApi.ts` | API client for templates and reports |

### Report workflow

1. User builds a chart in `ResultDetailPage` and clicks "Guardar gráfica" → `SaveChartModal` → stored as `SavedChartTemplate`.
2. In `ReportsPage` → "Generador de reportes": selects templates, assigns scenario slots, previews each chart via `DashboardChartCard`.
3. Exports as ZIP (PNG or SVG) via `POST /saved-chart-templates/report`.
4. Optionally saves the assembled report as `ReportTemplate` for reuse.

---

## Result Data Explorer

`frontend/src/pages/ResultDataExplorerPage.tsx` — Read-only wide-format table of raw simulation output.

- **Data source**: `/simulations/{jobId}/output-values/wide` (paginated) + `/wide/facets` (filter options) + `/export` (Excel)
- **8-dimension filters**: variable, region, technology, fuel, emission, timeslice, mode, storage
- **Category tabs**: 3-level drill-down (category → sub-category → variable name)
- **Dynamic column visibility**: auto-hide empty columns, manual override
- **Year rules**: include/exclude/range rules per year
- **Pagination**: 25/50/100/200 rows per page
- **Excel export**: formatted XLSX of filtered results
- Backend API: `backend/app/api/v1/simulations.py` (output-values routes)

---

## Key Design Decisions

- **Dual simulation path**: DB-mode uses `run_data_processing()` (PostgreSQL → CSVs); SAND/Excel mode uses `run_data_processing_from_excel()` (Excel → CSVs). Both feed the same `build_instance()` → `solve_model()` → `process_results()` pipeline.
- **UDC optional, off by default**: `ensure_udc_csvs()` and `apply_udc_config()` solo se llaman cuando `scenario.udc_config` tiene `"enabled": true`. Nuevos escenarios tienen `udc_config=null` → sin UDC en la simulación.
- **Declarative configs**: Business rules (technology prefixes, sectors, colors) are data in `CONFIGS`/`CONFIGS_COMPARACION`, not scattered in frontend or service code.
- **Two storage shapes**: Primary variables use typed columns; intermediate variables use `index_json` with heuristic parsing.
- **Comparison cap**: Max 10 jobs per comparison to control memory/query cost.
- **Historical year override**: `año_historico_unico=True` in comparison configs makes the first plotted year come from only the first job — for aligned baseline + projection reporting.
- **Visualization labels**: technology and fuel display names are managed in `labels.py` via `get_label()` (single) and `get_labels_batch()` (batch). 740+ static entries in `DISPLAY_NAMES`; `_dynamic_label()` generates from code segments as fallback. No external dictionary file — all mappings live in that module.
- **Individual chart export**: Charts can be exported individually (PNG/SVG/CSV) via a server-side endpoint (`/export-chart`). Frontend uses `serverChartExport.ts` to call this endpoint. Facet export merges SVGs client-side via `mergeFacetChartsSvg.ts`.
- **MODE_OF_OPERATION normalization**: `mode_of_operation_normalize.py` sanitizes mode values before writing CSVs, preventing Pyomo index mismatches from inconsistent input formatting.
- **Saved chart templates**: Chart configurations (tipo, un, filtros, viewMode, compareMode, syntheticSeries, etc.) are persisted as `SavedChartTemplate` records, enabling reuse across sessions and assembly into reports. `num_scenarios` determines how many job slots a template requires.
- **Synthetic series**: Manual data overlays (e.g. historical data, external projections) stored as JSONB in `SavedChartTemplate.synthetic_series` and also in localStorage for in-session use. Only rendered on line/area charts.
- **Pareto view**: Activated when `viewMode="pareto"` and `soportaPareto: true` on the chart item. Backend returns `ParetoChartResponse` (categories, values, cumulative_percent). Frontend renders via `ParetoChart.tsx` with dual Y-axis.
- **Special unit sets**: `CONTAMINANTES_CHART_IDS` and `PORCENTAJE_CHART_IDS` in `ChartSelector.tsx` pin the unit selector to a fixed value — frontend ignores the normal units dropdown for these charts.
- **Report bulk export**: `POST /saved-chart-templates/report` renders all templates with their assigned job IDs server-side (Matplotlib) and returns a ZIP. `organize_by_category=true` creates subdirectories matching the report layout.
- **Two-level infeasibility diagnosis**: Basic diagnostics (constraint body vs bounds, variable bound conflicts) run synchronously in `solver.py` during the pipeline. Enriched IIS analysis (HiGHS `getIis()`, constraint→param mapping, deviation scoring) runs on-demand in a separate Celery task to avoid blocking the pipeline. `run_iis_analysis=True` on a job is reserved for future automatic triggering.
- **Solver-agnostic infeasibility pipeline**: Constraint name parsing, `CONSTRAINT_PARAM_MAP`, CSV param loading, and deviation scoring in `infeasibility_analysis.py` are solver-agnostic. Only `try_compute_iis()` is HiGHS-specific; replacing it with a GLPK equivalent is sufficient to port IIS analysis to GLPK.
