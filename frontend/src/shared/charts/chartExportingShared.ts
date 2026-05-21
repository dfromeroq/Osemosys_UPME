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
      style: { color: "#334155", fontSize: "20pt" },
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
    labels: { style: { color: "#334155", fontSize: "20pt" } },
    title: { style: { color: "#334155", fontSize: "28pt" } },
    lineColor: "#334155",
    lineWidth: 1,
    gridLineColor: "#e2e8f0",
    stackLabels: { style: { color: "#1e293b", fontSize: "20pt" } },
  },
  legend: { itemStyle: { color: "#334155", fontSize: "20pt" } },
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
 * Menú de exportación: si hay job y selección, PNG/SVG/CSV vía API (servidor).
 * Si no, usa offline-exporting en el navegador.
 */
export function buildChartExportMenuItems(serverExport?: {
  jobId: number;
  selection: ChartSelection;
}): (string | Highcharts.ExportingMenuObject)[] {
  if (!serverExport) {
    return [...INDIVIDUAL_CHART_EXPORT_MENU_ITEMS];
  }
  const { jobId, selection } = serverExport;
  const run = (fmt: "png" | "svg" | "csv", clean?: boolean) => {
    void downloadChartFromServer(jobId, selection, fmt, undefined, clean).catch((e: unknown) => {
      console.error(e);
      window.alert(
        "No se pudo descargar desde el servidor. Comprueba la sesión o que el escenario tenga datos para esta gráfica.",
      );
    });
  };
  return [
    { text: "Descargar PNG (completo)", onclick: () => run("png") },
    { text: "Descargar SVG (completo)", onclick: () => run("svg") },
    { text: "Descargar CSV", onclick: () => run("csv") },
    "_separator_",
    { text: "Descargar PNG (sin título/números)", onclick: () => run("png", true) },
    { text: "Descargar SVG (sin título/números)", onclick: () => run("svg", true) },
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
