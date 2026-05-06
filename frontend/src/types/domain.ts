/**
 * Tipos del dominio del negocio: escenarios, usuarios, simulaciones, catálogos, etc.
 */
export type ScenarioEditPolicy = "OWNER_ONLY" | "OPEN" | "RESTRICTED";
export type SimulationType = "NATIONAL" | "REGIONAL";

export type ChangeRequestStatus = "PENDING" | "APPROVED" | "REJECTED";
export type ScenarioPermissionScope = "mine" | "readable" | "editable" | "readonly";

export type RunStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
export type SimulationSolver = "highs" | "glpk" | "gurobi";
export type SimulationInputMode = "SCENARIO" | "CSV_UPLOAD";

export type CatalogEntity =
  | "parameter"
  | "region"
  | "technology"
  | "fuel"
  | "emission"
  | "solver";

export type User = {
  id: string;
  email: string;
  username: string;
  is_active: boolean;
  can_manage_catalogs: boolean;
  can_import_official_data: boolean;
  can_manage_users: boolean;
  /** Admin Escenarios — ve privados ajenos; edita metadatos, política,
   * etiquetas y valores de cualquier escenario; administra permisos
   * granulares; clona, exporta y revisa change requests; elimina escenarios
   * y simulaciones/resultados ajenos. */
  can_manage_scenarios: boolean;
  /** Admin Reportes — puede editar reportes oficiales, cambiar nombre de
   * reportes públicos ajenos, marcar/desmarcar oficiales y ver reportes
   * privados ajenos. */
  is_admin_reports?: boolean;
  /** Admin de configuración del sistema — puede modificar runtime settings
   * (ej. hilos del solver) desde el panel admin. */
  can_manage_system_settings?: boolean;
};

/** Categoría jerárquica de etiquetas de escenario. */
export type ScenarioTagCategory = {
  id: number;
  name: string;
  hierarchy_level: number;
  sort_order: number;
  max_tags_per_scenario: number | null;
  is_exclusive_combination: boolean;
  default_color: string;
};

/** Etiqueta asignable a un escenario; pertenece a una categoría. */
export type ScenarioTag = {
  id: number;
  name: string;
  color: string;
  sort_order: number;
  category_id: number;
  /** Si true, la combinación (tag + cualquier tag de otra categoría) debe ser
   *  única entre escenarios. Independiente del flag homónimo de la categoría. */
  is_exclusive_combination?: boolean;
  category?: ScenarioTagCategory | null;
};

/** Conflicto detectado al intentar asignar una etiqueta a un escenario. */
export type ScenarioTagConflict = {
  scenario_id: number;
  scenario_name: string;
  conflicting_tag_id: number;
  conflicting_tag_name: string;
  reason: "exclusive_combination" | "max_one_per_scenario";
};

export type Scenario = {
  id: number;
  name: string;
  description: string | null;
  owner: string;
  base_scenario_id?: number | null;
  base_scenario_name?: string | null;
  changed_param_names?: string[];
  edit_policy: ScenarioEditPolicy;
  simulation_type: SimulationType;
  is_template: boolean;
  created_at: string;
  /** Etiqueta "primaria" (menor hierarchy_level). Compatibilidad con listados legacy. */
  tag?: ScenarioTag | null;
  /** Todas las etiquetas asignadas al escenario, ordenadas por jerarquía ascendente. */
  tags?: ScenarioTag[];
  effective_access?: {
    can_view: boolean;
    is_owner: boolean;
    can_edit_direct: boolean;
    can_propose: boolean;
    can_manage_values: boolean;
  } | null;
  /** Resumen de warnings de calidad de datos. null si nunca se corrió la
   * validación (ej. escenarios creados antes del refactor). */
  data_quality_summary?: DataQualitySummary | null;
};

/** Conteos del reporte de calidad de datos (ver backend `data_validation`). */
export type DataQualitySummary = {
  n_bound_conflicts: number;
  n_bound_real_conflict: number;
  n_bound_numeric_precision: number;
  n_year_exclusions: number;
};

/** Detalle completo del reporte (devuelto por GET /scenarios/{id}/data-quality). */
export type DataQualityReport = {
  bound_conflicts: BoundConflict[];
  year_exclusions: YearExclusion[];
  detected_at: string;
  detected_during: string;
  summary: DataQualitySummary;
};

export type BoundConflict = {
  lower: string;
  upper: string;
  key: { REGION?: string; TECHNOLOGY?: string; YEAR?: number; [k: string]: unknown };
  value_lower: number;
  value_upper: number;
  gap: number;
  /** "real_conflict" si gap >= 1e-4, "numeric_precision" en otro caso */
  severity: "real_conflict" | "numeric_precision";
};

export type YearExclusion = {
  year: number;
  reason: string;
  n_timeslices_zero: number;
  n_timeslices_total: number;
};

export type ScenarioPermission = {
  id: number;
  id_scenario: number;
  user_identifier: string;
  user_id: string | null;
  can_edit_direct: boolean;
  can_propose: boolean;
  can_manage_values: boolean;
};

export type ParameterValue = {
  id: number;
  id_parameter: number;
  id_region: number;
  id_solver: number;
  id_technology: number | null;
  id_fuel: number | null;
  id_emission: number | null;
  mode_of_operation: boolean;
  year: number;
  value: number;
  unit: string | null;
};

export type ChangeRequest = {
  id: number;
  id_osemosys_param_value: number;
  created_by: string;
  applied: boolean;
  old_value: number;
  new_value: number;
  status: ChangeRequestStatus;
  created_at: string;
};

export type CatalogItem = {
  id: number;
  entity: CatalogEntity;
  name: string;
  is_active: boolean;
};

export type SimulationRun = {
  id: number;
  scenario_id: number | null;
  scenario_name?: string | null;
  /** Alias opcional de la corrida (resultados y exportación). */
  display_name?: string | null;
  scenario_tag?: ScenarioTag | null;
  scenario_tags?: ScenarioTag[];
  user_id: string;
  username?: string | null;
  solver_name: SimulationSolver;
  /** Hilos efectivamente entregados al solver (leídos del propio optimizador
   * tras configurarlo). null si el solver es single-thread o si la lectura
   * falló. */
  solver_threads_used?: number | null;
  input_mode: SimulationInputMode;
  input_name?: string | null;
  simulation_type: SimulationType;
  status: RunStatus;
  progress: number;
  cancel_requested: boolean;
  queue_position: number | null;
  result_ref: string | null;
  error_message: string | null;
  queued_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  /** true si SUCCEEDED pero el solver reportó infactibilidad o hay diagnóstico en el job. */
  is_infeasible_result?: boolean;
  /** True si la simulación se encoló con "correr diagnóstico de infactibilidad automático". */
  run_iis_analysis?: boolean;
  /** True si la simulación se encoló con "guardar archivo .lp". */
  generate_lp?: boolean;
  /** True si el archivo .lp ya está escrito y disponible para descarga vía
   * `GET /simulations/{id}/lp-file`. */
  has_lp_file?: boolean;
  /** Estado del análisis enriquecido de infactibilidad (opcional, on-demand). */
  diagnostic_status?: "NONE" | "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  diagnostic_error?: string | null;
  diagnostic_started_at?: string | null;
  diagnostic_finished_at?: string | null;
  diagnostic_seconds?: number | null;
  /** Visibilidad del resultado: true = público (todos los usuarios), false = solo dueño. */
  is_public?: boolean;
  /** True si el usuario actual marcó este resultado como favorito. */
  is_favorite?: boolean;
};

export type SimulationOverview = {
  queued_count: number;
  running_count: number;
  active_count: number;
  total_count: number;
  services_memory_total_bytes: number;
};

export type ConstraintViolation = {
  name: string;
  body: number;
  lower: number | null;
  upper: number | null;
  side: string;
  violation: number;
};

export type VarBoundConflict = {
  name: string;
  lb: number;
  ub: number;
  gap: number;
};

export type IISBoundConflict = {
  /** Nombre de la variable cuyo bound entra en el IIS. */
  name: string;
  /** Cota que conflictúa: `LB` (lower bound) o `UB` (upper bound). */
  side: "LB" | "UB";
};

export type IISReport = {
  available: boolean;
  method: string | null;
  constraint_names: string[];
  variable_names: string[];
  /** Conflictos por cota que reporta Gurobi (`IISLB` / `IISUB`). HiGHS no
   * expone esta distinción, así que la lista queda vacía con ese solver. */
  bound_conflicts?: IISBoundConflict[];
  /** Path absoluto en el servidor del archivo `.ilp` generado por Gurobi.
   * Se descarga vía `GET /simulations/{id}/iis-ilp`. */
  ilp_path?: string | null;
  unavailable_reason: string | null;
};

export type ParamHit = {
  param: string;
  indices: Record<string, string>;
  value: number | null;
  is_default: boolean;
  default_value?: number | null;
  diff_abs?: number | null;
  deviation_score?: number | null;
};

export type ConstraintAnalysis = {
  name: string;
  constraint_type: string;
  indices: Record<string, string>;
  body: number | null;
  lower: number | null;
  upper: number | null;
  side: string;
  violation: number;
  in_iis: boolean;
  has_mapping: boolean;
  description: string;
  related_params: ParamHit[];
};

export type InfeasibilityOverview = {
  years: number[];
  constraint_types: Record<string, number>;
  variable_types: Record<string, number>;
  techs_or_fuels: Record<string, number>;
  total_constraints: number;
  total_variables: number;
};

export type InfeasibilityDiagnostics = {
  constraint_violations: ConstraintViolation[];
  var_bound_conflicts: VarBoundConflict[];
  // Estado del análisis on-demand (QUEUED/RUNNING/SUCCEEDED/FAILED; ausente = NONE):
  diagnostic_status?: "NONE" | "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  diagnostic_error?: string | null;
  diagnostic_started_at?: string | null;
  diagnostic_finished_at?: string | null;
  diagnostic_seconds?: number | null;
  // Campos enriquecidos (presentes solo si diagnostic_status === 'SUCCEEDED'):
  iis?: IISReport | null;
  overview?: InfeasibilityOverview | null;
  top_suspects?: ParamHit[];
  constraint_analyses?: ConstraintAnalysis[];
  unmapped_constraint_prefixes?: string[];
  csv_dir?: string | null;
};

export type RunResult = {
  job_id: number;
  scenario_id: number | null;
  solver_name: SimulationSolver;
  solver_threads_used?: number | null;
  records_used: number;
  osemosys_param_records: number;
  objective_value: number;
  solver_status: string;
  coverage_ratio: number;
  total_demand: number;
  total_dispatch: number;
  total_unmet: number;
  dispatch: Array<{
    region_id: number;
    year: number;
    technology_name: string | null;
    technology_id: number;
    fuel_name: string | null;
    dispatch: number;
    cost: number;
  }>;
  unmet_demand: Array<{
    region_id: number;
    year: number;
    unmet_demand: number;
  }>;
  new_capacity: Array<{
    region_id: number;
    technology_id: number;
    year: number;
    new_capacity: number;
    technology_name?: string;
  }>;
  annual_emissions: Array<{
    region_id: number;
    year: number;
    annual_emissions: number;
  }>;
  osemosys_inputs_summary: Array<{
    param_name: string;
    year: number | null;
    records: number;
    total_value: number;
  }>;
  stage_times: Record<string, number | string>;
  model_timings: Record<string, number | string>;
  /** Diccionario de solución por variable: lista de { index, value } (tipo HiGHS). */
  sol?: Record<string, Array<{ index: (string | number)[]; value: number }>>;
  /** Variables intermedias: ProductionByTechnology, UseByTechnology, etc. */
  intermediate_variables?: Record<string, Array<{ index: (string | number)[]; value: number }>>;
  infeasibility_diagnostics?: InfeasibilityDiagnostics | null;
};

export type SimulationLog = {
  id: number;
  event_type: string;
  stage: string | null;
  message: string | null;
  progress: number | null;
  created_at: string;
};

export type CsvSimulationResult = {
  solver_name: SimulationSolver;
  objective_value: number;
  solver_status: string;
  coverage_ratio: number;
  total_demand: number;
  total_dispatch: number;
  total_unmet: number;
  dispatch: Array<Record<string, unknown>>;
  unmet_demand: Array<Record<string, unknown>>;
  new_capacity: Array<Record<string, unknown>>;
  annual_emissions: Array<Record<string, unknown>>;
  stage_times: Record<string, number | string>;
  model_timings: Record<string, number | string>;
  sol?: Record<string, Array<{ index: (string | number)[]; value: number }>>;
  intermediate_variables?: Record<string, Array<{ index: (string | number)[]; value: number }>>;
  infeasibility_diagnostics?: InfeasibilityDiagnostics | null;
};

export type ScenarioOperationType = "CLONE_SCENARIO" | "APPLY_EXCEL_CHANGES";
export type ScenarioOperationStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";

export type ScenarioOperationJob = {
  id: number;
  operation_type: ScenarioOperationType;
  status: ScenarioOperationStatus;
  user_id: string;
  username?: string | null;
  scenario_id: number | null;
  scenario_name?: string | null;
  target_scenario_id: number | null;
  target_scenario_name?: string | null;
  progress: number;
  stage: string | null;
  message: string | null;
  result_json?: Record<string, unknown> | null;
  error_message: string | null;
  queued_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type ScenarioOperationLog = {
  id: number;
  event_type: string;
  stage: string | null;
  message: string | null;
  progress: number | null;
  created_at: string;
};

export type ChartSeries = {
  name: string;
  /**
   * `null` representa "no hay dato aquí" — produce un gap en líneas y
   * "no hay barra" en columnas. Se usa cuando se unifica el eje X entre
   * facets de distinto rango de años.
   */
  data: (number | null)[];
  color: string;
  stack?: string | null;
  /** True si es overlay manual del usuario (synthetic series). */
  is_synthetic?: boolean | null;
  /** Estilo de línea para overlays. */
  lineStyle?:
    | "Solid"
    | "Dash"
    | "Dot"
    | "DashDot"
    | "ShortDash"
    | null;
  /** Símbolo de marker para overlays. */
  markerSymbol?:
    | "circle"
    | "diamond"
    | "square"
    | "triangle"
    | "triangle-down"
    | "none"
    | null;
  /** Radio del marker en px. */
  markerRadius?: number | null;
  /** Grosor de línea en px. */
  lineWidth?: number | null;
};

export type ChartDataResponse = {
  categories: string[];
  series: ChartSeries[];
  title: string;
  yAxisLabel: string;
};

export type SubplotData = {
  year: number;
  scenario_name?: string | null;
  categories: string[];
  series: ChartSeries[];
};

export type CompareChartResponse = {
  title: string;
  subplots: SubplotData[];
  yAxisLabel: string;
};

export type CompareMode = "off" | "facet" | "by-year" | "by-year-alt" | "line-total";

/** Modo del nombre de archivo al exportar comparación por facetas (PNG/SVG). */
export type CompareFacetExportFilenameMode = "result" | "tags";

export type FacetData = {
  scenario_name: string;
  job_id: number;
  display_name?: string | null;
  scenario_tag_name?: string | null;
  categories: string[];
  series: ChartSeries[];
};

export type CompareChartFacetResponse = {
  title: string;
  facets: FacetData[];
  yAxisLabel: string;
};

export type ParetoChartResponse = {
  categories: string[];
  values: number[];
  cumulative_percent: number[];
  title: string;
  yAxisLabel: string;
};

/**
 * Filtros que reproducen las filas que un chart agrega/grafica. Consumido
 * por el botón "Ver Datos de Resultados" para abrir el Data Explorer ya
 * filtrado a las filas que el chart suma.
 */
export type ChartDataExplorerFilters = {
  variable_names?: string[];
  technology_prefixes?: string[];
  fuel_prefixes?: string[];
  fuel_names?: string[];
  emission_names?: string[];
};

export type ChartCatalogItem = {
  id: string;
  label: string;
  variable_default: string;
  has_sub_filtro: boolean;
  has_loc: boolean;
  sub_filtros: string[] | null;
  es_capacidad: boolean;
  soporta_pareto: boolean;
  data_explorer_filters?: ChartDataExplorerFilters | null;
};

/** Tipo de línea de una serie sintética (overlay). */
export type SyntheticLineStyle =
  | "Solid"
  | "Dash"
  | "Dot"
  | "DashDot"
  | "ShortDash";

/** Símbolo del marker de una serie sintética. `none` oculta los markers. */
export type SyntheticMarkerSymbol =
  | "circle"
  | "diamond"
  | "square"
  | "triangle"
  | "triangle-down"
  | "none";

/**
 * Serie manual con puntos (año, valor). Se adjunta a una plantilla para overlays
 * de línea (p.ej. datos externos de un estudio comparable).
 */
export type SyntheticSeries = {
  id: string;
  name: string;
  /** Nota descriptiva opcional (fuente de datos, supuestos, etc.). */
  description?: string | null;
  /**
   * Si `false`, la serie existe pero no se dibuja en la gráfica ni se cuenta
   * en el reporte. Permite guardar varias series y alternar cuáles mostrar.
   * Si está ausente, se considera `true` (retrocompatible con templates viejos).
   */
  active?: boolean | null;
  color: string;
  data: Array<[number, number]>;
  /** Estilo de línea. Default: ShortDash (punteada, señal visual de "manual"). */
  lineStyle?: SyntheticLineStyle | null;
  /** Símbolo del marker. Default: diamond. */
  markerSymbol?: SyntheticMarkerSymbol | null;
  /** Radio del marker en px. Default: 5. */
  markerRadius?: number | null;
  /** Grosor de línea en px. Default: 2 (Highcharts default). */
  lineWidth?: number | null;
};

/** Plantilla de gráfica guardada por un usuario para generar reportes. */
export type SavedChartTemplate = {
  id: number;
  name: string;
  description: string | null;
  tipo: string;
  un: string;
  sub_filtro: string | null;
  loc: string | null;
  variable: string | null;
  agrupar_por: string | null;
  view_mode: "column" | "line" | "area" | "pareto" | "porcentaje" | "table" | null;
  compare_mode: "off" | "facet" | "by-year" | "by-year-alt" | "line-total";
  /** Años a graficar cuando `compare_mode === "by-year"`. Null en otros modos. */
  years_to_plot: number[] | null;
  /** Series manuales overlay (línea). */
  synthetic_series: SyntheticSeries[] | null;
  /** Solo `view_mode === "table"`: muestra años cada N (5=cada 5 años). */
  table_period_years?: number | null;
  /** Solo `view_mode === "table"`: si true muestra valores acumulados. */
  table_cumulative?: boolean | null;
  /** Override del orden de series (lista de nombres). null = orden natural. */
  custom_series_order?: string[] | null;
  /** Override del valor mínimo del eje Y. null = auto. */
  y_axis_min?: number | null;
  /** Override del valor máximo del eje Y. null = auto. */
  y_axis_max?: number | null;
  bar_orientation: "vertical" | "horizontal" | null;
  facet_placement: "inline" | "stacked" | null;
  facet_legend_mode: "shared" | "perFacet" | null;
  num_scenarios: number;
  legend_title: string | null;
  filename_mode: "result" | "tags" | null;
  /** Título personalizado usado al renderizar en reportes (null → título auto). */
  report_title?: string | null;
  created_at: string;
  /** Visibilidad: false = solo dueño, true = visible a todos (solo lectura). */
  is_public?: boolean;
  /** Username del dueño (siempre poblado por el backend). */
  owner_username?: string | null;
  /** True si el usuario actual es el dueño. */
  is_owner?: boolean;
  /** True si el usuario actual marcó esta gráfica como favorita. */
  is_favorite?: boolean;
};

export type SavedChartTemplateCreate = Omit<
  SavedChartTemplate,
  "id" | "created_at"
>;

export type SavedChartTemplateUpdate = {
  name?: string;
  description?: string | null;
  is_public?: boolean;
  /** Enviar "" o null limpia el override. */
  report_title?: string | null;
  /** Tipo de trazo. Permite alternar columnas/áreas desde el reporte. */
  view_mode?: "column" | "line" | "area" | "pareto" | "porcentaje" | "table" | null;
  table_period_years?: number | null;
  table_cumulative?: boolean | null;
  custom_series_order?: string[] | null;
  y_axis_min?: number | null;
  y_axis_max?: number | null;
};

export type ReportTemplateItem = {
  template_id: number;
  job_ids: number[];
  /** Alias del escenario para agregar al título al exportar (solo single-chart). */
  scenario_alias_for_title?: string | null;
};

/** Subcategoría dentro de una categoría del reporte. */
export type ReportLayoutSubcategory = {
  id: string;
  label: string;
  items: number[];
};

export type ReportLayoutCategory = {
  id: string;
  label: string;
  items: number[];
  subcategories: ReportLayoutSubcategory[];
};

export type SubcategoryDisplay = "tabs" | "accordions";

export type ReportLayout = {
  categories: ReportLayoutCategory[];
  /** Modo de presentación de subcategorías en el dashboard. Default "tabs". */
  subcategory_display?: SubcategoryDisplay;
};

/** Subcategoría con items expandidos (template_id + job_ids) — para export. */
export type ReportCategoryExportSub = {
  id: string;
  label: string;
  items: ReportTemplateItem[];
};

export type ReportCategoryExport = {
  id: string;
  label: string;
  items: ReportTemplateItem[];
  subcategories: ReportCategoryExportSub[];
};

export type ReportRequest = {
  items: ReportTemplateItem[];
  fmt: "png" | "svg";
  report_name?: string | null;
  organize_by_category?: boolean;
  categories?: ReportCategoryExport[];
  /**
   * Alias por job_id solo para este export; no muta el `display_name` real del
   * resultado. Las claves son strings por el wire format (JSON).
   */
  job_display_overrides?: Record<string, string> | null;
  /** Año mínimo a incluir (cierra inclusive). `null`/ausente = sin tope inferior. */
  year_from?: number | null;
  /** Año máximo a incluir (cierra inclusive). `null`/ausente = sin tope superior. */
  year_to?: number | null;
};

/** Reporte guardado: colección ordenada de IDs de SavedChartTemplate. */
export type SavedReport = {
  id: number;
  name: string;
  description: string | null;
  fmt: "png" | "svg";
  items: number[];
  created_at: string;
  updated_at: string;
  is_public?: boolean;
  is_official?: boolean;
  owner_username?: string | null;
  is_owner?: boolean;
  /** True si el usuario actual marcó este reporte como favorito. */
  is_favorite?: boolean;
  /** null = modo automático (frontend computa por módulo); objeto = override manual. */
  layout?: ReportLayout | null;
  /** Alias por escenario global (0-based). `null`/ausente = sin aliases. */
  scenario_aliases?: string[] | null;
  /** Job IDs por defecto por slot (0-based). `null` en la posición = slot vacío. */
  default_job_ids?: (number | null)[] | null;
  /** Año mínimo persistido del rango. `null` = sin tope inferior. */
  year_from?: number | null;
  /** Año máximo persistido del rango. `null` = sin tope superior. */
  year_to?: number | null;
};

export type SavedReportCreate = {
  name: string;
  description?: string | null;
  fmt: "png" | "svg";
  items: number[];
  layout?: ReportLayout | null;
  scenario_aliases?: string[] | null;
  default_job_ids?: (number | null)[] | null;
  year_from?: number | null;
  year_to?: number | null;
};

export type SavedReportUpdate = {
  name?: string;
  description?: string | null;
  fmt?: "png" | "svg";
  items?: number[];
  is_public?: boolean;
  is_official?: boolean;
  /** Enviar `null` resetea al modo automático; enviar objeto guarda el override. */
  layout?: ReportLayout | null;
  /** Enviar `null` o `[]` limpia los aliases. */
  scenario_aliases?: string[] | null;
  /** Enviar `null` o `[]` limpia los defaults. */
  default_job_ids?: (number | null)[] | null;
  /** Enviar `null` limpia el filtro inferior. */
  year_from?: number | null;
  /** Enviar `null` limpia el filtro superior. */
  year_to?: number | null;
};

export type ResultSummaryResponse = {
  job_id: number;
  scenario_id: number | null;
  scenario_name: string | null;
  scenario_tag?: ScenarioTag | null;
  scenario_tags?: ScenarioTag[];
  /** Alias opcional definido por el usuario para esta corrida. */
  display_name?: string | null;
  solver_name: string;
  solver_status: string;
  objective_value: number;
  coverage_ratio: number;
  total_demand: number;
  total_dispatch: number;
  total_unmet: number;
  total_co2: number;
  /** Visibilidad del resultado. */
  is_public?: boolean;
  /** True si el usuario actual lo marcó como favorito. */
  is_favorite?: boolean;
  /** True si el solver terminó infactible (aunque el job esté SUCCEEDED). */
  is_infeasible_result?: boolean;
  /** Username del dueño del resultado. */
  owner_username?: string | null;
};

export type DeletionLogEntry = {
  id: number;
  entity_type: "SCENARIO" | "SIMULATION_JOB";
  entity_id: number;
  entity_name: string;
  deleted_by_user_id: string;
  deleted_by_username: string;
  deleted_at: string;
  details_json?: Record<string, unknown> | null;
};
