/**
 * Codifica/decodifica el estado completo de una visualización en query params
 * para generar **links compartibles** que reproducen exactamente lo que el
 * usuario está viendo: tipo de gráfica, modo de vista, filtros, orientación,
 * comparación entre escenarios, jobs participantes, años a graficar, opciones
 * de tabla, etc.
 *
 * Patrón:
 *   /app/results/<jobId>?<query-params>
 *
 * Donde el path usa el primer job como "principal" y los adicionales (en
 * comparación) viajan en `jobs=`.
 *
 * Las claves son cortas a propósito (URL legible, no excede límites comunes
 * de longitud). Solo se serializan los valores no-default; los defaults se
 * inferirán al deserializar.
 */
import type { ChartSelection } from "./ChartSelector";
import type { CompareViewMode } from "./ScenarioComparer";

export type ShareableChartState = {
  jobIds: number[];
  selection: ChartSelection;
  barOrientation?: "vertical" | "horizontal" | undefined;
  compareMode?: CompareViewMode | "off" | undefined;
  compareYearsToPlot?: number[] | undefined;
  facetPlacement?: "inline" | "stacked" | undefined;
  facetLegendMode?: "shared" | "perFacet" | undefined;
};

/** Construye un Record<string,string> con los params no vacíos, listo para URLSearchParams. */
export function encodeChartShareParams(
  state: ShareableChartState,
): Record<string, string> {
  const out: Record<string, string> = {};
  const s = state.selection;
  if (s.tipo) out.t = s.tipo;
  if (s.un) out.u = s.un;
  if (s.un2) out.u2 = s.un2;
  if (s.sub_filtro) out.sf = s.sub_filtro;
  if (s.loc) out.loc = s.loc;
  if (s.variable) out.v = s.variable;
  if (s.agrupar_por) out.ag = s.agrupar_por;
  if (s.viewMode && s.viewMode !== "column") out.vm = s.viewMode;
  if (typeof s.tablePeriodYears === "number") {
    out.tpy = String(s.tablePeriodYears);
  }
  if (s.tableCumulative) out.tcum = "1";
  if (s.customSeriesOrder && s.customSeriesOrder.length > 0) {
    // Encoded como pipes para diferenciar de los splits por coma.
    out.so = s.customSeriesOrder.join("||");
  }
  if (typeof s.yAxisMin === "number") out.ymin = String(s.yAxisMin);
  if (typeof s.yAxisMax === "number") out.ymax = String(s.yAxisMax);

  if (state.barOrientation && state.barOrientation !== "vertical") {
    out.bo = state.barOrientation;
  }

  // Comparación: solo si hay 2+ jobs y un modo distinto de off.
  const jobs = (state.jobIds ?? []).filter(
    (id) => Number.isFinite(id) && id > 0,
  );
  if (jobs.length > 1) {
    out.jobs = jobs.join(",");
    if (state.compareMode && state.compareMode !== "off") {
      out.cm = state.compareMode;
    }
    if (
      state.compareMode === "by-year" &&
      state.compareYearsToPlot &&
      state.compareYearsToPlot.length > 0
    ) {
      out.years = state.compareYearsToPlot.join(",");
    }
    if (state.compareMode === "facet") {
      if (state.facetPlacement && state.facetPlacement !== "inline") {
        out.fp = state.facetPlacement;
      }
      if (state.facetLegendMode && state.facetLegendMode !== "shared") {
        out.flm = state.facetLegendMode;
      }
    }
  }
  return out;
}

/** Construye la URL absoluta lista para copiar al clipboard. */
export function buildChartShareUrl(state: ShareableChartState): string {
  const jobs = (state.jobIds ?? []).filter(
    (id) => Number.isFinite(id) && id > 0,
  );
  const primary = jobs[0];
  if (!primary) {
    return window.location.origin + window.location.pathname;
  }
  const params = encodeChartShareParams(state);
  const query = new URLSearchParams(params).toString();
  // El visor amplificado vive en su propia ruta sin AppLayout (sidebar de
  // navegación oculto), con un panel de Configuración a la derecha.
  const path = `/app/charts/viewer/${primary}`;
  return `${window.location.origin}${path}${query ? `?${query}` : ""}`;
}

/** Parsea query params de vuelta a un estado parcial reusable. */
export function decodeChartShareParams(
  search: URLSearchParams,
): Partial<ShareableChartState> {
  const get = (k: string): string | undefined => {
    const v = search.get(k);
    return v == null ? undefined : v;
  };
  const selection: ChartSelection = {
    tipo: get("t") ?? "",
    un: get("u") ?? "",
  };
  const u2 = get("u2");
  if (u2) selection.un2 = u2;
  const sf = get("sf");
  if (sf) selection.sub_filtro = sf;
  const loc = get("loc");
  if (loc) selection.loc = loc;
  const v = get("v");
  if (v) selection.variable = v;
  const ag = get("ag");
  if (ag) selection.agrupar_por = ag;
  const vm = get("vm");
  if (
    vm === "column" ||
    vm === "line" ||
    vm === "area" ||
    vm === "pareto" ||
    vm === "porcentaje" ||
    vm === "table"
  ) {
    selection.viewMode = vm;
  }
  const tpy = get("tpy");
  if (tpy != null) {
    const n = Number(tpy);
    if (Number.isFinite(n) && n >= 1) selection.tablePeriodYears = n;
  }
  if (get("tcum") === "1") selection.tableCumulative = true;
  const so = get("so");
  if (so) {
    const parts = so.split("||").map((p) => p.trim()).filter(Boolean);
    if (parts.length > 0) selection.customSeriesOrder = parts;
  }
  const ymin = get("ymin");
  if (ymin != null) {
    const n = Number(ymin);
    if (Number.isFinite(n)) selection.yAxisMin = n;
  }
  const ymax = get("ymax");
  if (ymax != null) {
    const n = Number(ymax);
    if (Number.isFinite(n)) selection.yAxisMax = n;
  }

  const partial: Partial<ShareableChartState> = { selection };
  const bo = get("bo");
  if (bo === "horizontal" || bo === "vertical") {
    partial.barOrientation = bo;
  }
  const jobsRaw = get("jobs");
  if (jobsRaw) {
    const parsed = jobsRaw
      .split(",")
      .map((x) => Number(x.trim()))
      .filter((n) => Number.isFinite(n) && n > 0);
    if (parsed.length > 0) partial.jobIds = parsed;
  }
  const cm = get("cm");
  if (cm === "facet" || cm === "by-year" || cm === "line-total") {
    partial.compareMode = cm;
  }
  const years = get("years");
  if (years) {
    const ys = years
      .split(",")
      .map((x) => Number(x.trim()))
      .filter((n) => Number.isFinite(n));
    if (ys.length > 0) partial.compareYearsToPlot = ys;
  }
  const fp = get("fp");
  if (fp === "inline" || fp === "stacked") partial.facetPlacement = fp;
  const flm = get("flm");
  if (flm === "shared" || flm === "perFacet") partial.facetLegendMode = flm;

  return partial;
}

/** Copia un texto al clipboard con fallback robusto para HTTP / iframe. */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fallback */
  }
  // Fallback: textarea oculto.
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
