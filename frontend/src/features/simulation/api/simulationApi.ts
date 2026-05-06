/**
 * API de simulación OSeMOSYS. Envío de trabajos, listado, cancelación,
 * logs y obtención de resultados (dispatch, unmet, new_capacity, etc.).
 */
import { httpClient } from "@/shared/api/httpClient";
import type { PaginatedResponse } from "@/shared/api/pagination";
import type {
  ChartCatalogItem,
  ChartDataResponse,
  CompareChartFacetResponse,
  CompareChartResponse,
  CompareFacetExportFilenameMode,
  ParetoChartResponse,
  ResultSummaryResponse,
  RunResult,
  SimulationLog,
  SimulationOverview,
  SimulationRun,
  SimulationSolver,
  SimulationType,
} from "@/types/domain";
import type { ChartSelection } from "@/shared/charts/ChartSelector";

type ListRunsParams = {
  scope?: "mine" | "global";
  status_filter?: string;
  username?: string;
  scenario_id?: number;
  solver_name?: SimulationSolver;
  cantidad?: number;
  offset?: number;
};

export const simulationApi = {
  async submit(
    scenarioId: number,
    solverName: SimulationSolver,
    options?: {
      runIisAnalysis?: boolean;
      generateLp?: boolean;
      display_name?: string | null;
    },
  ) {
    // Unifica en un solo `options` los flags opcionales:
    //   - `runIisAnalysis`: correr análisis de infactibilidad inline.
    //   - `generateLp`: persistir el modelo a `.lp` antes de resolver.
    //   - `display_name`: alias visible de la corrida.
    const body: {
      scenario_id: number;
      solver_name: SimulationSolver;
      run_iis_analysis: boolean;
      generate_lp: boolean;
      display_name?: string;
    } = {
      scenario_id: scenarioId,
      solver_name: solverName,
      run_iis_analysis: Boolean(options?.runIisAnalysis),
      generate_lp: Boolean(options?.generateLp),
    };
    const dn = options?.display_name?.trim();
    if (dn) body.display_name = dn.slice(0, 255);
    const { data } = await httpClient.post<SimulationRun>("/simulations", body);
    return data;
  },

  async submitFromCsv(
    file: File,
    solverName: SimulationSolver,
    runIisAnalysis: boolean = false,
    input: {
      input_name?: string;
      simulation_type: SimulationType;
      save_as_scenario: boolean;
      scenario_name?: string;
      description?: string;
      edit_policy?: "OWNER_ONLY" | "OPEN" | "RESTRICTED";
      tag_id?: number | null;
      display_name?: string | null;
    },
    options?: { display_name?: string | null; generateLp?: boolean },
  ) {
    const formData = new FormData();
    formData.append("csv_zip", file);
    formData.append("solver_name", solverName);
    formData.append("run_iis_analysis", String(runIisAnalysis));
    formData.append("generate_lp", String(Boolean(options?.generateLp)));
    formData.append("simulation_type", input.simulation_type);
    formData.append("save_as_scenario", input.save_as_scenario ? "true" : "false");
    if (input.input_name?.trim()) formData.append("input_name", input.input_name.trim());
    if (input.scenario_name?.trim()) formData.append("scenario_name", input.scenario_name.trim());
    if (input.description?.trim()) formData.append("description", input.description.trim());
    if (input.edit_policy) formData.append("edit_policy", input.edit_policy);
    if (input.tag_id != null) formData.append("tag_id", String(input.tag_id));
    const dn = input.display_name?.trim();
    if (dn) formData.append("display_name", dn.slice(0, 255));
    const { data } = await httpClient.post<SimulationRun>("/simulations/from-csv", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 10 * 60 * 1000,
    });
    return data;
  },

  async listRuns(params: ListRunsParams = {}) {
    const { data } = await httpClient.get<PaginatedResponse<SimulationRun>>(
      "/simulations",
      { params },
    );
    return data;
  },

  async getOverview() {
    const { data } = await httpClient.get<SimulationOverview>("/simulations/overview");
    return data;
  },

  async getRun(jobId: number) {
    const { data } = await httpClient.get<SimulationRun>(`/simulations/${jobId}`);
    return data;
  },

  async patchDisplayName(jobId: number, displayName: string | null) {
    const { data } = await httpClient.patch<SimulationRun>(`/simulations/${jobId}`, {
      display_name: displayName,
    });
    return data;
  },

  /** Cambia la visibilidad del resultado (solo dueño). */
  async patchVisibility(jobId: number, isPublic: boolean) {
    const { data } = await httpClient.patch<SimulationRun>(
      `/simulations/${jobId}`,
      { is_public: isPublic },
    );
    return data;
  },

  /** Marca/desmarca como favorito del usuario actual. */
  async setFavorite(jobId: number, isFavorite: boolean) {
    const { data } = await httpClient.patch<SimulationRun>(
      `/simulations/${jobId}/favorite`,
      { is_favorite: isFavorite },
    );
    return data;
  },

  async cancel(jobId: number) {
    const { data } = await httpClient.post<SimulationRun>(
      `/simulations/${jobId}/cancel`,
    );
    return data;
  },

  async deleteJob(jobId: number): Promise<void> {
    await httpClient.delete(`/simulations/${jobId}`);
  },

  async listLogs(jobId: number, cantidad = 100, offset = 1) {
    const { data } = await httpClient.get<PaginatedResponse<SimulationLog>>(
      `/simulations/${jobId}/logs`,
      { params: { cantidad, offset } },
    );
    return data;
  },

  async getResult(jobId: number) {
    const { data } = await httpClient.get<RunResult>(`/simulations/${jobId}/result`, {
      timeout: 5 * 60 * 1000,
    });
    return data;
  },

  /** Encola el análisis de infactibilidad (IIS + mapeo a parámetros) para un job
   * SUCCEEDED pero infactible. Solo aplica a HiGHS. Devuelve el job actualizado
   * con `diagnostic_status='QUEUED'`. */
  async runInfeasibilityDiagnostic(jobId: number) {
    const { data } = await httpClient.post<SimulationRun>(
      `/simulations/${jobId}/diagnose-infeasibility`,
    );
    return data;
  },

  /** Cancela un diagnóstico en QUEUED/RUNNING. */
  async cancelInfeasibilityDiagnostic(jobId: number) {
    const { data } = await httpClient.post<SimulationRun>(
      `/simulations/${jobId}/cancel-diagnostic`,
    );
    return data;
  },

  /** Descarga el reporte de infactibilidad como JSON (attachment). */
  async downloadInfeasibilityReport(jobId: number): Promise<{ blob: Blob; filename: string }> {
    const { data, headers } = await httpClient.get(
      `/simulations/${jobId}/infeasibility-report`,
      { responseType: "blob", timeout: 2 * 60 * 1000 },
    );
    const blob = data as Blob;
    const disposition = headers["content-disposition"];
    let filename = `infeasibility_report_job_${jobId}.json`;
    if (typeof disposition === "string") {
      const match = /filename="?([^";\n]+)"?/i.exec(disposition);
      if (match?.[1]) filename = match[1].trim();
    }
    return { blob, filename };
  },

  /** Descarga el `.lp` del modelo Pyomo (solo si la corrida se lanzó con
   * `generate_lp=true`). */
  async downloadLpFile(jobId: number): Promise<{ blob: Blob; filename: string }> {
    const { data, headers } = await httpClient.get(
      `/simulations/${jobId}/lp-file`,
      { responseType: "blob", timeout: 5 * 60 * 1000 },
    );
    const blob = data as Blob;
    const disposition = headers["content-disposition"];
    let filename = `sim_${jobId}.lp`;
    if (typeof disposition === "string") {
      const match = /filename="?([^";\n]+)"?/i.exec(disposition);
      if (match?.[1]) filename = match[1].trim();
    }
    return { blob, filename };
  },

  /** Descarga el `.ilp` del IIS (solo si la corrida fue con Gurobi y el
   * análisis ya finalizó). */
  async downloadIisIlp(jobId: number): Promise<{ blob: Blob; filename: string }> {
    const { data, headers } = await httpClient.get(
      `/simulations/${jobId}/iis-ilp`,
      { responseType: "blob", timeout: 2 * 60 * 1000 },
    );
    const blob = data as Blob;
    const disposition = headers["content-disposition"];
    let filename = `iis_job_${jobId}.ilp`;
    if (typeof disposition === "string") {
      const match = /filename="?([^";\n]+)"?/i.exec(disposition);
      if (match?.[1]) filename = match[1].trim();
    }
    return { blob, filename };
  },

  async getResultSummary(jobId: number) {
    const { data } = await httpClient.get<ResultSummaryResponse>(`/visualizations/${jobId}/result-summary`);
    return data;
  },

  async getChartData(
    jobId: number,
    params: {
      tipo: string;
      un?: string;
      sub_filtro?: string;
      loc?: string;
      variable?: string;
      agrupar_por?: string;
    },
  ) {
    const { data } = await httpClient.get<ChartDataResponse>(`/visualizations/${jobId}/chart-data`, { params });
    return data;
  },

  /**
   * Una gráfica como PNG/SVG (Matplotlib) o CSV; mismos filtros que chart-data.
   */
  async exportChart(
    jobId: number,
    selection: ChartSelection,
    fmt: "png" | "svg" | "csv" | "xlsx",
  ): Promise<{ blob: Blob; filename: string }> {
    const params: Record<string, string> = {
      tipo: selection.tipo,
      un: selection.un,
      fmt,
      view_mode: selection.viewMode ?? "column",
    };
    if (selection.sub_filtro) params.sub_filtro = selection.sub_filtro;
    if (selection.loc) params.loc = selection.loc;
    if (selection.variable) params.variable = selection.variable;
    if (selection.agrupar_por) params.agrupar_por = selection.agrupar_por;
    // Solo aplican cuando view_mode === 'table'
    if (selection.viewMode === "table") {
      if (typeof selection.tablePeriodYears === "number" && selection.tablePeriodYears >= 1) {
        params.table_period_years = String(selection.tablePeriodYears);
      }
      if (selection.tableCumulative) {
        params.table_cumulative = "true";
      }
    }
    // Modificadores universales: orden custom de series + rango Y.
    if (selection.customSeriesOrder && selection.customSeriesOrder.length > 0) {
      params.series_order = selection.customSeriesOrder.join(",");
    }
    if (typeof selection.yAxisMin === "number") {
      params.y_axis_min = String(selection.yAxisMin);
    }
    if (typeof selection.yAxisMax === "number") {
      params.y_axis_max = String(selection.yAxisMax);
    }

    const response = await httpClient.get(`/visualizations/${jobId}/export-chart`, {
      params,
      responseType: "blob",
      timeout: 5 * 60 * 1000,
    });
    const blob = response.data as Blob;
    const disposition = response.headers["content-disposition"];
    const ext = fmt;
    let filename = `grafica_${jobId}.${ext}`;
    if (typeof disposition === "string") {
      const match = /filename="?([^";\n]+)"?/i.exec(disposition);
      if (match?.[1]) filename = match[1].trim();
    }
    return { blob, filename };
  },

  async getCompareData(params: { job_ids: string, tipo: string, un?: string, years_to_plot?: string, agrupacion?: string, sub_filtro?: string, loc?: string, group_by?: string }) {
    const { data } = await httpClient.get<CompareChartResponse>(`/visualizations/chart-data/compare`, { params });
    return data;
  },

  async getCompareFacetData(params: {
    job_ids: string;
    tipo: string;
    un?: string;
    sub_filtro?: string;
    loc?: string;
    variable?: string;
    agrupar_por?: string;
  }) {
    const { data } = await httpClient.get<CompareChartFacetResponse>(`/visualizations/chart-data/compare-facet`, { params });
    return data;
  },

  async getCompareLineData(params: {
    job_ids: string;
    tipo: string;
    un?: string;
    sub_filtro?: string;
    loc?: string;
  }) {
    const { data } = await httpClient.get<ChartDataResponse>(
      `/visualizations/chart-data/compare-line`,
      { params },
    );
    return data;
  },

  async getParetoData(
    jobId: number,
    params: { tipo: string; un?: string; sub_filtro?: string; loc?: string },
  ) {
    const { data } = await httpClient.get<ParetoChartResponse>(
      `/visualizations/${jobId}/pareto-data`,
      { params },
    );
    return data;
  },

  /** Una imagen PNG/SVG con todas las facetas en fila (Matplotlib; mismo filtro que compare-facet). */
  async exportCompareFacet(
    params: {
      job_ids: string;
      tipo: string;
      un?: string;
      sub_filtro?: string;
      loc?: string;
      variable?: string;
      agrupar_por?: string;
      legend_title?: string;
      filename_mode?: CompareFacetExportFilenameMode;
    },
    fmt: "png" | "svg" = "png",
  ): Promise<{ blob: Blob; filename: string }> {
    const q: Record<string, string> = {
      job_ids: params.job_ids,
      tipo: params.tipo,
      un: params.un ?? "PJ",
      fmt,
    };
    if (params.sub_filtro) q.sub_filtro = params.sub_filtro;
    if (params.loc) q.loc = params.loc;
    if (params.variable) q.variable = params.variable;
    if (params.agrupar_por) q.agrupar_por = params.agrupar_por;
    if (params.legend_title) q.legend_title = params.legend_title;
    if (params.filename_mode) q.filename_mode = params.filename_mode;

    const response = await httpClient.get("/visualizations/export-compare-facet", {
      params: q,
      responseType: "blob",
      timeout: 5 * 60 * 1000,
    });
    const blob = response.data as Blob;
    const disposition = response.headers["content-disposition"];
    const ext = fmt === "svg" ? "svg" : "png";
    let filename = `comparativa_facet.${ext}`;
    if (typeof disposition === "string") {
      const match = /filename="?([^";\n]+)"?/i.exec(disposition);
      if (match?.[1]) filename = match[1].trim();
    }
    return { blob, filename };
  },

  async getChartCatalog() {
    const { data } = await httpClient.get<ChartCatalogItem[]>("/visualizations/chart-catalog");
    return data;
  },

  async exportAllCharts(jobId: number, un: string = "PJ", fmt: string = "svg") {
    const response = await httpClient.get(`/visualizations/${jobId}/export-all`, {
      params: { un, fmt },
      responseType: "blob",
      timeout: 5 * 60 * 1000,
    });
    return response;
  },

  /** Descarga los datos crudos del job como Excel (osemosys_output_param_value). */
  async exportRawData(jobId: number): Promise<{ blob: Blob; filename: string }> {
    const { data, headers } = await httpClient.get(`/visualizations/${jobId}/export-raw`, {
      responseType: "blob",
      timeout: 10 * 60 * 1000,
    });
    const blob = data as Blob;
    const disposition = headers["content-disposition"];
    let filename = `Resultados_Crudos_Job_${jobId}.xlsx`;
    if (typeof disposition === "string") {
      const match = /filename="?([^";\n]+)"?/i.exec(disposition);
      if (match?.[1]) filename = match[1].trim();
    }
    return { blob, filename };
  },

  /** Descarga un ZIP con un CSV por variable en formato OSeMOSYS estándar. */
  async exportResultsCsvZip(jobId: number): Promise<{ blob: Blob; filename: string }> {
    const { data, headers } = await httpClient.get(`/visualizations/${jobId}/export-csv-bundle`, {
      responseType: "blob",
      timeout: 10 * 60 * 1000,
    });
    const blob = data as Blob;
    const disposition = headers["content-disposition"];
    let filename = `Resultados_CSV_Job_${jobId}.zip`;
    if (typeof disposition === "string") {
      const match = /filename="?([^";\n]+)"?/i.exec(disposition);
      if (match?.[1]) filename = match[1].trim();
    }
    return { blob, filename };
  },
};
