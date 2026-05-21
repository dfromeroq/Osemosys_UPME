import type Highcharts from "highcharts";

import type { ChartSelection } from "./ChartSelector";
import { downloadChartFromServer } from "./serverChartExport";

/**
 * Apariencia al exportar SVG (misma base que `exporting.chartOptions` en las gráficas de barras).
 * Se reutiliza en Chart#getSVG para la descarga combinada de facetas.
 */
export const HIGHCHARTS_GETSVG_MERGE_OPTIONS: Partial<Highcharts.Options> = {
  chart: {
    backgroundColor: "#FFFFFF",
    plotBorderWidth: 1,
    plotBorderColor: "#94a3b8",
    /** Espacio para etiquetas del eje Y (fuente grande al exportar). */
    marginLeft: 100,
  },
  title: { style: { color: "#1e293b", fontSize: "28pt" } },
  xAxis: {
    labels: {
      style: { color: "#334155", fontSize: "20pt", fontWeight: "normal" },
      rotation: -90,
      align: "right",
      /** Sin esto Highcharts fuerza -45° al exportar. `false` es válido en runtime (tipos incompletos). */
      autoRotation: false,
    } as unknown as Highcharts.XAxisLabelsOptions,
    lineColor: "#334155",
    lineWidth: 1,
    tickColor: "#334155",
    tickWidth: 1,
  },
  yAxis: {
    labels: { style: { color: "#334155", fontSize: "20pt", fontWeight: "normal" } },
    title: { style: { color: "#334155", fontSize: "28pt" } },
    lineColor: "#334155",
    lineWidth: 1,
    gridLineColor: "#e2e8f0",
    stackLabels: { style: { color: "#1e293b", fontSize: "20pt", fontWeight: "normal" } },
  },
  legend: { itemStyle: { color: "#334155", fontSize: "20pt", fontWeight: "normal" } },
};

/**
 * Botón de menú de exportación con fondo oscuro (el predeterminado es blanco y destaca en capturas PNG).
 */
export const EXPORTING_CONTEXT_BUTTON_DARK = {
  theme: {
    fill: "#0f172a",
    stroke: "#334155",
    states: {
      hover: { fill: "#1e293b", stroke: "#475569" },
      select: { fill: "#1e293b", stroke: "#475569" },
    },
  },
  symbolStroke: "#94a3b8",
} as const;

/**
 * Menú contextual cuando están cargados en `highchartsSetup.ts`:
 * - `exporting`
 * - `offline-exporting` → PNG (y JPEG/PDF) en el cliente sin servidor
 * - `export-data` → CSV / XLS
 */
export const INDIVIDUAL_CHART_EXPORT_MENU_ITEMS = [
  "downloadPNG",
  "downloadSVG",
  "downloadCSV",
] as const satisfies readonly string[];

/**
 * Overrides de Highcharts para exportación "limpia" (sin título ni stackLabels).
 * Adecuado para charts con un solo yAxis (HighchartsChart, LineChart, FacetChart).
 */
export const CLEAN_EXPORT_OVERRIDES_SINGLE_YAXIS: Partial<Highcharts.Options> = {
  title: { text: '' },
  yAxis: { stackLabels: { enabled: false } },
  plotOptions: { series: { dataLabels: { enabled: false } as any } },
};

/**
 * Overrides de Highcharts para exportación "limpia" en charts con múltiples yAxis.
 * `count` = número de subplots/ejes Y.
 */
export function buildCleanExportOverridesMultiYAxis(count: number): Partial<Highcharts.Options> {
  return {
    title: { text: '' },
    yAxis: Array.from({ length: count }, () => ({
      stackLabels: { enabled: false },
    })),
    plotOptions: { series: { dataLabels: { enabled: false } as any } },
  };
}

/**
 * Menú de exportación: si hay job y selección, PNG/SVG/CSV vía API (servidor).
 * Si no, usa offline-exporting en el navegador.
 * Cuando hay servidor, se agregan ítems para descarga "limpia".
 */
export function buildChartExportMenuItems(serverExport?: {
  jobId: number;
  selection: ChartSelection;
}): (string | Highcharts.ExportingMenuObject)[] {
  if (!serverExport) {
    return [...INDIVIDUAL_CHART_EXPORT_MENU_ITEMS];
  }
  const { jobId, selection } = serverExport;
  const run = (fmt: "png" | "svg" | "csv", options?: { clean?: boolean }) => {
    void downloadChartFromServer(jobId, selection, fmt, options).catch((e: unknown) => {
      console.error(e);
      window.alert(
        "No se pudo descargar desde el servidor. Comprueba la sesión o que el escenario tenga datos para esta gráfica.",
      );
    });
  };
  return [
    { text: "Descargar PNG", onclick: () => run("png") },
    { text: "Descargar SVG", onclick: () => run("svg") },
    { text: "Descargar CSV", onclick: () => run("csv") },
    "_separator_",
    { text: "Descargar PNG (limpia)", onclick: () => run("png", { clean: true }) },
    { text: "Descargar SVG (limpia)", onclick: () => run("svg", { clean: true }) },
  ];
}

/**
 * Callback de Highcharts cuando falla la exportación local (offline-exporting).
 * API: exporting.error(exportingOptions, err) — ver módulo offline-exporting.
 * Sin esto el fallo puede ser silencioso si fallbackToExportServer es false.
 */
export function onHighchartsExportError(
  _exportingOptions: unknown,
  err: unknown,
): void {
  console.error("Highcharts export", err);
  window.alert(
    "No se pudo exportar la gráfica desde el navegador (PNG, SVG o CSV). Si usas un navegador muy antiguo, prueba con uno actual o descarga el ZIP desde Exportar en la página de resultados.",
  );
}

/**
 * Helper para generar un item de menú de exportación "limpia" (client-side).
 * Usa `this.exportChart()` que Highcharts vincula al Chart en handlers del menú contextual.
 */
export function createCleanExportMenuItem(
  fmt: 'png' | 'svg',
  cleanOverrides: Partial<Highcharts.Options>,
): Highcharts.ExportingMenuObject {
  const typeMap = { png: 'image/png' as const, svg: 'image/svg+xml' as const };
  return {
    text: fmt === 'png' ? 'Descargar PNG (limpia)' : 'Descargar SVG (limpia)',
    onclick(this: Highcharts.Chart) {
      (this as any).exportChartLocal({ type: typeMap[fmt] }, cleanOverrides);
    },
  };
}
