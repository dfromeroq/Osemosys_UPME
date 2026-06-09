import React, { useEffect, useMemo, useRef, useState } from "react";
import { FileDown } from "lucide-react";
import { useToast } from "@/app/providers/useToast";
import { simulationApi } from "@/features/simulation/api/simulationApi";
import { Button } from "@/shared/components/Button";
import { downloadBlob } from "@/shared/utils/downloadBlob";
import Highcharts from "./highchartsSetup";
import {
  CLEAN_EXPORT_OVERRIDES_SINGLE_YAXIS,
  EXPORTING_CONTEXT_BUTTON_DARK,
  HIGHCHARTS_GETSVG_MERGE_OPTIONS,
  INDIVIDUAL_CHART_EXPORT_MENU_ITEMS,
  createCleanExportMenuItem,
  onHighchartsExportError,
} from "./chartExportingShared";
import {
  buildCombinedFacetSvgDocument,
  extractSvgRootInnerXml,
  remapSvgFragmentIds,
} from "./mergeFacetChartsSvg";
import { buildLineTooltipOptions, buildStackedTooltipOptions } from "./chartTooltips";
import { formatAxis3Sig } from "./numberFormat";
import {
  createLegendDblclickState,
  dispatchLegendClick,
} from "./chartLegendInteractions";
import HighchartsReact from "highcharts-react-official";
import type {
  CompareChartFacetResponse,
  CompareFacetExportFilenameMode,
  FacetData,
} from "../../types/domain";
import type {
  ChartBarOrientation,
  ChartFacetLegendMode,
  ChartFacetPlacement,
} from "./chartLayoutPreferences";
import type { ChartSelection } from "./ChartSelector";

/** Título de leyenda en PNG servidor según agrupación (similar a la referencia de exportación). */
function safeExportBaseFromTitle(title: string, maxLen = 80): string {
  const clean = title.replace(/[^a-zA-Z0-9 _-]+/g, "_").replace(/_+/g, "_").trim();
  const base = clean || "grafico";
  return base.length > maxLen ? base.slice(0, maxLen) : base;
}

function compareFacetClientFilenameBase(
  data: CompareChartFacetResponse,
  mode: CompareFacetExportFilenameMode,
): string {
  const facets = data.facets.filter((f) => f.series?.length);
  if (facets.length === 0) {
    return safeExportBaseFromTitle(data.title);
  }
  const parts = facets.map((f) => {
    const simFb = (f.scenario_name || `job_${f.job_id}`).trim();
    const resultName = (f.display_name?.trim() || simFb).trim();
    if (mode === "tags") {
      const tag = f.scenario_tag_name?.trim() || "";
      return tag || resultName;
    }
    return resultName;
  });
  return safeExportBaseFromTitle(parts.join("__"), 140);
}

function facetExportLegendTitleFromSelection(sel: ChartSelection): string | undefined {
  const a = sel.agrupar_por?.toUpperCase();
  if (a === "FUEL" || a === "COMBUSTIBLE") return "Combustible / tecnología";
  if (a === "TECNOLOGIA") return "Tecnología";
  if (a === "GROUP") return "Familia / grupo";
  if (a === "SECTOR") return "Sector";
  return undefined;
}

function stackLabelFormatter(this: Highcharts.StackItemObject): string {
  if (Math.abs(this.total) < 1) {
    return this.total.toLocaleString("en-US", { minimumSignificantDigits: 2, maximumSignificantDigits: 2 });
  }
  return Highcharts.numberFormat(this.total, 2, ".", ",");
}

/**
 * Tamaño de fuente para etiquetas del eje X (años) según cuántos subplots.
 * Menos facetas = más ancho disponible = fuente más grande.
 */
function facetXLabelFontPx(_facetCount: number): number {
  return 20;
}

/**
 * Paso entre etiquetas visibles del eje X (saltarse N categorías).
 * Con más facetas → menos ancho por subplot → mostrar menos etiquetas.
 * Ajusta también según la cantidad total de años para que nunca choquen.
 */
function facetXLabelStep(facetCount: number, categoryCount: number): number {
  // Densidad aproximada: más años y más facetas → paso mayor.
  const base = facetCount <= 1 ? 1 : facetCount === 2 ? 2 : facetCount === 3 ? 3 : 4;
  if (categoryCount <= 6) return 1;
  if (categoryCount <= 10) return Math.max(1, base - 1);
  return base;
}
/** Etiquetas del eje Y (valores) en pantalla. */
const FACET_Y_LABEL_FONT_PX = 11;

function maxCategoryCharLength(categories: string[]): number {
  if (categories.length === 0) return 1;
  return Math.max(1, ...categories.map((c) => String(c).length));
}

/**
 * Margen inferior para etiquetas en vertical: escala con la etiqueta más larga y el tamaño de fuente.
 * Incluye un buffer extra para el offset `y` de la etiqueta y separación respecto al eje.
 */
function facetMarginBottomForVerticalCategoryLabels(
  categories: string[],
  fontPx: number,
): number {
  const len = maxCategoryCharLength(categories);
  const perChar = fontPx * 0.62;
  // 28px de buffer cubre el offset y: 16 de la etiqueta + padding inferior.
  return Math.round(Math.min(28 + 28 + len * perChar, 300));
}

function useMediaMinWidth(px: number): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(`(min-width: ${px}px)`).matches : false,
  );
  useEffect(() => {
    const mq = window.matchMedia(`(min-width: ${px}px)`);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [px]);
  return matches;
}

/**
 * Pequeño kebab "⋯" con menú flotante para los controles de export del facet
 * cuando el contenedor pide modo compacto (dashboard).
 */
function FacetExportKebab({
  disabled,
  showServerPng,
  onExportPng,
  onExportSvg,
  exportingPng,
  exportingSvg,
  exportClean,
  onToggleClean,
}: {
  disabled: boolean;
  showServerPng: boolean;
  onExportPng: () => Promise<void> | void;
  onExportSvg: () => Promise<void> | void;
  exportingPng: boolean;
  exportingSvg: boolean;
  exportClean: boolean;
  onToggleClean: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        title="Opciones de la gráfica"
        aria-label="Opciones de la gráfica"
        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-700 bg-slate-900/40 text-slate-300 hover:bg-slate-800 disabled:opacity-50"
      >
        ⋯
      </button>
      {open ? (
        <div className="absolute right-0 top-full z-30 mt-1 min-w-[220px] rounded-lg border border-slate-800 bg-slate-900/95 p-1 shadow-2xl backdrop-blur-md">
          {showServerPng ? (
            <button
              type="button"
              disabled={disabled}
              onClick={async () => {
                setOpen(false);
                await onExportPng();
              }}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800/80 disabled:opacity-50"
            >
              <FileDown className="h-3.5 w-3.5 shrink-0" aria-hidden />
              {exportingPng ? "Generando PNG…" : "Descargar PNG"}
            </button>
          ) : null}
          <label className="flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800/80">
            <input
              type="checkbox"
              checked={exportClean}
              onChange={onToggleClean}
              className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-800 text-emerald-500 focus:ring-emerald-500"
            />
            Sin título / valores
          </label>
          <button
            type="button"
            disabled={disabled}
            onClick={async () => {
              setOpen(false);
              await onExportSvg();
            }}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800/80 disabled:opacity-50"
          >
            <FileDown className="h-3.5 w-3.5 shrink-0" aria-hidden />
            {exportingSvg ? "Generando SVG…" : "Descargar SVG"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

interface CompareChartFacetProps {
  data: CompareChartFacetResponse;
  barOrientation?: ChartBarOrientation;
  facetPlacement?: ChartFacetPlacement;
  /** Predeterminado: leyenda compartida (panel React). */
  legendMode?: ChartFacetLegendMode;
  /**
   * Tipo de visualización por subplot:
   *   - `column` (default): barras apiladas (stacking normal).
   *   - `line`: una línea por serie; sin stacking. Útil para ver la evolución
   *     por año de cada serie dentro de cada escenario.
   */
  viewMode?: 'column' | 'line' | 'area';
  /** Si se define, permite descargar PNG (y parámetros) desde el backend sin Highcharts. */
  serverFacetExport?: {
    jobIds: number[];
    selection: ChartSelection;
    legendTitle?: string;
    scenarioAliases?: Record<number, string>;
    /** Datos exógenos (Refinerías) serializados como JSON string. */
    exogenousData?: string | undefined;
    /** Datos exógenos contaminantes criterio serializados como JSON string. */
    exogenousContaminantesData?: string | undefined;
  };
  /** Si true, los controles de export se colapsan en un menú kebab "⋯". */
  compactToolbar?: boolean;
  /** Override del eje Y para todos los facets. ``null``/undefined = auto. */
  yAxisMin?: number | null;
  yAxisMax?: number | null;
  /** Años fijos para las etiquetas del eje X (solo se muestran estos años). */
  fixedTickYears?: number[];
}

/** Metadatos en la instancia Chart para exportar sin depender de un array de refs (getSVG / update rompen ese enlace). */
type HighchartsChartFacetExportMeta = Highcharts.Chart & {
  __facetSyncGroup?: string;
  __facetJobId?: number;
  __facetExportInstanceId?: string;
};

function resolveFacetChartsForExport(
  exportInstanceId: string,
  facets: FacetData[],
): Highcharts.Chart[] | null {
  const byJob = new Map<number, Highcharts.Chart>();
  for (const raw of Highcharts.charts) {
    if (!raw) continue;
    const c = raw as HighchartsChartFacetExportMeta;
    if (c.__facetExportInstanceId !== exportInstanceId || c.__facetJobId == null) continue;
    byJob.set(Number(c.__facetJobId), c);
  }
  const ordered: Highcharts.Chart[] = [];
  for (const f of facets) {
    const ch = byJob.get(Number(f.job_id));
    if (!ch) return null;
    ordered.push(ch);
  }
  return ordered;
}

function FacetChart({
  facet,
  yAxisLabel,
  sharedYAxisMax,
  syncGroup,
  hiddenSeriesNames,
  onLegendToggle,
  onLegendIsolate,
  onLegendRestoreAll,
  inverted,
  chartHeight,
  showHighchartsLegend,
  viewMode,
  facetCount,
  hoveredSeriesName = null,
  facetExportInstanceId,
  yAxisMin,
  yAxisMax,
  showLeftTitle = false,
  fixedTickYears,
}: {
  facet: FacetData;
  yAxisLabel: string;
  sharedYAxisMax: number;
  syncGroup: string;
  hiddenSeriesNames: Set<string>;
  onLegendToggle: (seriesName: string) => void;
  onLegendIsolate: (seriesName: string) => void;
  onLegendRestoreAll: () => void;
  inverted: boolean;
  chartHeight: number;
  showHighchartsLegend: boolean;
  viewMode: 'column' | 'line' | 'area';
  /** Cantidad de facetas en el grupo. Define responsive de font y step del eje X. */
  facetCount: number;
  /** Resaltado sincronizado con leyenda compartida (hover). */
  hoveredSeriesName?: string | null;
  /** Id estable del bloque CompareChartFacet (marcado en cada Chart en `load`). */
  facetExportInstanceId: string;
  /** Override del eje Y. */
  yAxisMin?: number | null;
  yAxisMax?: number | null;
  /** Si true, el título del escenario se renderiza fuera de Highcharts (a la izquierda). */
  showLeftTitle?: boolean;
  /** Años fijos para las etiquetas del eje X. */
  fixedTickYears?: number[];
}) {
  const chartRef = useRef<Highcharts.Chart | null>(null);
  const legendDblclickStateRef = useRef(createLegendDblclickState());
  const [chartGeneration, setChartGeneration] = useState(0);

  useEffect(() => {
    return () => {
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart?.series?.length) return;
    chart.series.forEach((s) => {
      if (!s.visible) {
        s.setState("");
        return;
      }
      if (!hoveredSeriesName) {
        s.setState("");
        return;
      }
      if (s.name === hoveredSeriesName) {
        s.setState("hover");
      } else {
        s.setState("inactive");
      }
    });
  }, [hoveredSeriesName, facet, hiddenSeriesNames, chartGeneration]);

  const options = useMemo<Highcharts.Options>(() => {
    const series = facet.series.map((s) => {
      const effectiveType = s.chart_type ?? (viewMode === "line" ? "line" : viewMode === "area" ? "area" : "column");
      const isLine = effectiveType === "line";
      const isArea = effectiveType === "area";
      return {
        type: effectiveType as "column" | "area" | "line",
        name: s.name,
        data: s.data,
        color: s.color,
        stacking: isLine ? undefined : "normal" as const,
        stack: isLine ? undefined : s.stack,
        visible: !hiddenSeriesNames.has(s.name),
        marker: isLine ? { enabled: true, radius: 3 } : (isArea ? { enabled: false } : undefined),
        borderWidth: isLine ? undefined : 0,
        fillOpacity: isArea ? 0.85 : undefined,
        lineWidth: isArea ? 0.5 : (isLine ? 2 : undefined),
      };
    });

    const xLabelFontPx = facetXLabelFontPx(facetCount);
    const xLabelStep = facetXLabelStep(facetCount, facet.categories.length);

    const marginBottomVert = !inverted
      ? facetMarginBottomForVerticalCategoryLabels(facet.categories, xLabelFontPx)
      : undefined;

    const simPart = facet.display_name?.trim() || facet.scenario_name;
    const tagPart = facet.scenario_tag_name?.trim();
    const facetTitleText = tagPart ? `${simPart} — ${tagPart}` : simPart;

    return {
      title: showLeftTitle
        ? { text: null as unknown as string }
        : { text: facetTitleText, style: { fontSize: "14pt", fontWeight: "bold", color: "#f8fafc" } },
      xAxis: {
        categories: facet.categories,
        crosshair: { color: "#334155" },
        lineWidth: 1,
        // Tick visible en CADA categoría (año), incluso cuando la etiqueta se salta,
        // para que quede claro a qué columna corresponde cada label.
        tickmarkPlacement: "on",
        tickWidth: 1,
        tickLength: 6,
        minorTickLength: 0,
        ...(fixedTickYears
          ? {
              tickPositioner: function (this: Highcharts.Axis) {
                const cats = this.categories ?? [];
                const positions = (fixedTickYears ?? [])
                  .map((y) => cats.indexOf(String(y)))
                  .filter((i) => i >= 0);
                return positions.length > 0 ? positions : [];
              } as Highcharts.AxisTickPositionerCallbackFunction,
            }
          : {}),
        labels: (
          inverted
            ? {
                style: { color: "#94a3b8", fontSize: `${xLabelFontPx}px` },
                autoRotation: false,
              }
            : {
                rotation: -90,
                // Align `center` + y positivo mantiene la etiqueta debajo del eje,
                // alineada con el tick/columna correspondiente (no "flotando" a un lado).
                align: "center",
                y: 16,
                reserveSpace: true,
                autoRotation: false,
                step: fixedTickYears ? 1 : xLabelStep,
                style: {
                  color: "#94a3b8",
                  fontSize: `${xLabelFontPx}px`,
                  whiteSpace: "nowrap",
                },
              }
        ) as unknown as Highcharts.XAxisLabelsOptions,
        lineColor: "#64748b",
        tickColor: "#64748b",
        events: {
          afterSetExtremes(event) {
            const evt = event as Highcharts.AxisSetExtremesEventObject & {
              trigger?: string;
            };
            if (evt.trigger === "sync-facet-x") return;
            const sourceChart = this.chart as Highcharts.Chart & {
              __facetSyncGroup?: string;
            };
            Highcharts.charts.forEach((chartCandidate) => {
              const targetChart = chartCandidate as
                | (Highcharts.Chart & { __facetSyncGroup?: string })
                | undefined;
              if (!targetChart || targetChart === sourceChart) return;
              if (targetChart.__facetSyncGroup !== syncGroup) return;
              const axis = targetChart.xAxis?.[0];
              if (!axis) return;
              axis.setExtremes(evt.min, evt.max, true, false, {
                trigger: "sync-facet-x",
              } as Highcharts.AxisSetExtremesEventObject);
            });
          },
        },
      },
      yAxis: {
        min: typeof yAxisMin === 'number' ? yAxisMin : 0,
        max: typeof yAxisMax === 'number'
          ? yAxisMax
          : (sharedYAxisMax > 0 ? sharedYAxisMax : null),
        lineWidth: 1,
        lineColor: "#64748b",
        title: {
          text: yAxisLabel,
          style: { color: "#94a3b8", fontSize: "14pt" },
        },
        labels: {
          style: { color: "#94a3b8", fontSize: `${FACET_Y_LABEL_FONT_PX}px` },
          // Mínimo 3 cifras significativas (sin notación científica).
          formatter: function (this: Highcharts.AxisLabelsFormatterContextObject) {
            return formatAxis3Sig(this.value as number);
          },
        },
        gridLineColor: "#334155",
        stackLabels: viewMode === "line"
          ? { enabled: false }
          : {
              enabled: true,
              style: {
                fontWeight: "bold",
                color: "#94a3b8",
                textOutline: "none",
                fontSize: "11pt",
              },
              formatter: stackLabelFormatter,
            },
      },
      tooltip: viewMode === "line"
        ? buildLineTooltipOptions({ unitLabel: yAxisLabel })
        : buildStackedTooltipOptions({
            unitLabel: yAxisLabel,
            headerPrefix: () => facetTitleText,
          }),
      plotOptions: {
        series: {
          states: {
            inactive: {
              enabled: true,
              opacity: 0.35,
            },
            hover: {
              enabled: true,
              brightness: 0.12,
            },
          },
          events: showHighchartsLegend
            ? {
                // Sincroniza visibilidad de series entre todas las facetas del mismo grupo.
                // 1 click → toggle; doble click → aislar (o restaurar si ya está aislada).
                legendItemClick: function (this: Highcharts.Series) {
                  const name = this.name;
                  dispatchLegendClick(
                    legendDblclickStateRef.current,
                    name,
                    {
                      onToggle: onLegendToggle,
                      onIsolate: onLegendIsolate,
                      onRestoreAll: onLegendRestoreAll,
                    },
                  );
                  return false;
                },
              }
            : {},
        },
        column: {
          stacking: "normal",
          borderWidth: 0,
          groupPadding: 0.08,
          dataLabels: { enabled: false },
        },
        area: {
          stacking: "normal",
          lineWidth: 0.5,
          fillOpacity: 0.85,
          marker: { enabled: false },
          dataLabels: { enabled: false },
        },
        line: {
          dataLabels: { enabled: false },
          marker: { enabled: true, radius: 3 },
        },
      },
      series: series as Highcharts.SeriesOptionsType[],
      chart: {
        type: viewMode === "line" ? "line" : viewMode === "area" ? "area" : "column",
        height: chartHeight,
        inverted,
        ...(marginBottomVert !== undefined ? { marginBottom: marginBottomVert } : {}),
        style: { fontFamily: "Verdana, sans-serif" },
        backgroundColor: "transparent",
        borderWidth: 0,
        plotBorderWidth: 1,
        plotBorderColor: "rgba(148, 163, 184, 0.45)",
        plotShadow: false,
        events: {
          load() {
            const ch = this as HighchartsChartFacetExportMeta;
            ch.__facetSyncGroup = syncGroup;
            ch.__facetJobId = facet.job_id;
            ch.__facetExportInstanceId = facetExportInstanceId;
          },
        },
      },
      exporting: {
        enabled: true,
        sourceWidth: 1920,
        sourceHeight: 1080,
        scale: 1,
        fallbackToExportServer: false,
        error: onHighchartsExportError,
        chartOptions: HIGHCHARTS_GETSVG_MERGE_OPTIONS as Highcharts.Options,
        buttons: {
          contextButton: {
            menuItems: [
              ...INDIVIDUAL_CHART_EXPORT_MENU_ITEMS,
              '_separator_',
              createCleanExportMenuItem('png', CLEAN_EXPORT_OVERRIDES_SINGLE_YAXIS),
              createCleanExportMenuItem('svg', CLEAN_EXPORT_OVERRIDES_SINGLE_YAXIS),
            ] as unknown as string[],
            ...EXPORTING_CONTEXT_BUTTON_DARK,
          },
        },
      },
      credits: { enabled: false },
      legend: {
        enabled: showHighchartsLegend,
        align: "center",
        verticalAlign: "bottom",
        layout: "horizontal",
        // Leyenda invertida respecto al stack (lectura abajo→arriba).
        reversed: true,
        itemStyle: { color: "#94a3b8", fontWeight: "normal", fontSize: "11pt" },
        itemHoverStyle: { color: "#f8fafc" },
      },
    };
  }, [
    facet,
    yAxisLabel,
    sharedYAxisMax,
    syncGroup,
    hiddenSeriesNames,
    onLegendToggle,
    inverted,
    chartHeight,
    showHighchartsLegend,
    viewMode,
    facetCount,
    facetExportInstanceId,
    fixedTickYears,
  ]);

  return (
    <HighchartsReact
      highcharts={Highcharts}
      options={options}
      callback={(chart: Highcharts.Chart) => {
        chartRef.current = chart;
        setChartGeneration((g) => g + 1);
      }}
      containerProps={{ style: { width: "100%" } }}
    />
  );
}

function buildSharedLegendItems(
  facets: FacetData[],
  customOrder?: string[] | null,
): { name: string; color: string }[] {
  const byName = new Map<string, string>();
  for (const facet of facets) {
    for (const s of facet.series) {
      if (!byName.has(s.name)) byName.set(s.name, s.color);
    }
  }
  const items = Array.from(byName.entries()).map(([name, color]) => ({ name, color }));
  if (!customOrder || customOrder.length === 0) return items;
  // Si el usuario configuró un orden custom, lo usamos como criterio principal
  // para la leyenda (compartida entre todas las facetas). Las series que no
  // estén en ``customOrder`` quedan al final, en su orden natural — así la
  // leyenda corresponde con el orden general de las series y se ve consistente
  // con el stack de cada subplot.
  const rank = new Map<string, number>();
  customOrder.forEach((name, idx) => {
    if (!rank.has(name)) rank.set(name, idx);
  });
  const fallback = customOrder.length;
  return items.slice().sort((a, b) => {
    const ra = rank.has(a.name) ? (rank.get(a.name) as number) : fallback;
    const rb = rank.has(b.name) ? (rank.get(b.name) as number) : fallback;
    return ra - rb;
  });
}

export const CompareChartFacet: React.FC<CompareChartFacetProps> = ({
  data,
  barOrientation = "vertical",
  facetPlacement = "inline",
  legendMode = "shared",
  viewMode = "column",
  serverFacetExport,
  compactToolbar = false,
  yAxisMin,
  yAxisMax,
  fixedTickYears,
}) => {
  const inverted = barOrientation === "horizontal";
  const n = data.facets.length;
  const seriesStateSignature = useMemo(
    () => `${data.title}|${data.facets.map((f) => f.job_id).join(",")}`,
    [data.title, data.facets],
  );
  const [legendState, setLegendState] = useState<{
    signature: string;
    hiddenSeriesNames: Set<string>;
  }>({
    signature: seriesStateSignature,
    hiddenSeriesNames: new Set(),
  });
  const hiddenSeriesNames =
    legendState.signature === seriesStateSignature
      ? legendState.hiddenSeriesNames
      : new Set<string>();

  const [legendHover, setLegendHover] = useState<{
    dataSig: string;
    seriesName: string | null;
  } | null>(null);

  const effectiveLegendHover =
    legendHover && legendHover.dataSig === seriesStateSignature
      ? legendHover.seriesName
      : null;

  const handleLegendToggle = (seriesName: string) => {
    setLegendHover({ dataSig: seriesStateSignature, seriesName: null });
    setLegendState((prev) => {
      const baseHidden =
        prev.signature === seriesStateSignature ? prev.hiddenSeriesNames : new Set<string>();
      const next = new Set(baseHidden);
      if (next.has(seriesName)) next.delete(seriesName);
      else next.add(seriesName);
      return {
        signature: seriesStateSignature,
        hiddenSeriesNames: next,
      };
    });
  };

  const handleLegendIsolate = (seriesName: string) => {
    setLegendHover({ dataSig: seriesStateSignature, seriesName: null });
    setLegendState(() => ({
      signature: seriesStateSignature,
      hiddenSeriesNames: new Set<string>(
        sharedLegendItems.map((item) => item.name).filter((n) => n !== seriesName),
      ),
    }));
  };

  const handleLegendRestoreAll = () => {
    setLegendHover({ dataSig: seriesStateSignature, seriesName: null });
    setLegendState(() => ({
      signature: seriesStateSignature,
      hiddenSeriesNames: new Set<string>(),
    }));
  };

  const htmlLegendDblclickStateRef = useRef(createLegendDblclickState());

  const facetChartHeight = useMemo(() => {
    const catLen = Math.max(
      ...data.facets.map((f) => f.categories.length),
      1,
    );
    if (inverted) {
      return Math.min(640, 240 + catLen * 15);
    }
    // Altura algo menor; el margen inferior dinámico reserva sitio para etiquetas verticales.
    if (n >= 4) return 320;
    if (n >= 3) return 335;
    return 360;
  }, [data.facets, inverted, n]);

  // Orden custom de series — se obtiene de la selección que viene del padre
  // (ResultDetailPage). Sirve tanto para la leyenda compartida como para el
  // PNG/SVG exportado, así el render UI y export coinciden.
  const customSeriesOrder = serverFacetExport?.selection?.customSeriesOrder ?? null;

  const sharedLegendItems = useMemo(
    () => buildSharedLegendItems(data.facets, customSeriesOrder),
    [data.facets, customSeriesOrder],
  );

  const sharedYAxisMax = useMemo(() => {
    let globalMax = 0;
    data.facets.forEach((facet) => {
      const categoryCount = facet.categories.length;
      for (let i = 0; i < categoryCount; i += 1) {
        const stackTotal = facet.series.reduce((acc, serie) => {
          const point = serie.data[i];
          return acc + (typeof point === "number" ? point : 0);
        }, 0);
        if (stackTotal > globalMax) globalMax = stackTotal;
      }
    });
    return globalMax;
  }, [data.facets]);

  const isStacked = facetPlacement === "stacked";
  const useSharedLegendPanel = legendMode === "shared" && sharedLegendItems.length > 0;
  const isLg = useMediaMinWidth(1024);
  /** Id único por montaje: cada Chart marca `__facetExportInstanceId` en `load` para resolver exportaciones desde `Highcharts.charts`. */
  const facetExportInstanceIdRef = useRef<string | null>(null);
  if (facetExportInstanceIdRef.current == null) {
    facetExportInstanceIdRef.current =
      globalThis.crypto?.randomUUID?.() ??
      `facet-export-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
  }
  const { push } = useToast();
  const [exportingFacetSvg, setExportingFacetSvg] = useState(false);
  const [exportingFacetPng, setExportingFacetPng] = useState(false);
  const [facetExportClean, setFacetExportClean] = useState(false);
  const [facetExportFilenameMode, setFacetExportFilenameMode] =
    useState<CompareFacetExportFilenameMode>("result");
  const exportBusy = exportingFacetSvg || exportingFacetPng;
  const exportFilenameSelectId = React.useId();

  const handleExportFacetPngServer = async (): Promise<void> => {
    if (!serverFacetExport || serverFacetExport.jobIds.length < 2) {
      push("Se necesitan al menos dos escenarios seleccionados.", "error");
      return;
    }
    setExportingFacetPng(true);
    try {
      const sel = serverFacetExport.selection;
      const legend_title =
        serverFacetExport.legendTitle ?? facetExportLegendTitleFromSelection(sel);
      const esPorcentaje = sel.viewMode === 'porcentaje';
      const payload: Parameters<typeof simulationApi.exportCompareFacet>[0] = {
        job_ids: serverFacetExport.jobIds.join(","),
        tipo: sel.tipo,
        un: sel.un,
      };
      if (esPorcentaje) payload.es_porcentaje = 'true';
      if (sel.viewMode && sel.viewMode !== 'column') payload.view_mode = sel.viewMode;
      if (sel.sub_filtro) payload.sub_filtro = sel.sub_filtro;
      if (sel.loc) payload.loc = sel.loc;
      if (sel.variable) payload.variable = sel.variable;
      if (sel.agrupar_por) payload.agrupar_por = sel.agrupar_por;
      if (legend_title) payload.legend_title = legend_title;
      if (facetExportClean) payload.clean = true;
      payload.filename_mode = facetExportFilenameMode;
      if (sel.customSeriesOrder && sel.customSeriesOrder.length > 0) {
        payload.series_order = sel.customSeriesOrder.join(",");
      }
      if (sel.region && sel.agrupar_por !== 'REGION') {
        payload.region = sel.region;
      }
      if (serverFacetExport.scenarioAliases && Object.keys(serverFacetExport.scenarioAliases).some(k => serverFacetExport.scenarioAliases![Number(k)]?.trim())) {
        payload.job_display_overrides = JSON.stringify(serverFacetExport.scenarioAliases);
      }
      if (serverFacetExport.exogenousData) {
        payload.exogenous_data = serverFacetExport.exogenousData;
      }
      if (serverFacetExport.exogenousContaminantesData) {
        payload.exogenous_contaminantes_data = serverFacetExport.exogenousContaminantesData;
      }
      if (hiddenSeriesNames.size > 0) {
        payload.hidden_series = Array.from(hiddenSeriesNames).join(",");
      }
      payload.facet_placement = facetPlacement;
      const { blob, filename } = await simulationApi.exportCompareFacet(payload, "png");
      downloadBlob(blob, filename);
      push("PNG descargado (todas las facetas en una imagen).", "success");
    } catch (err) {
      console.error(err);
      let msg = "No se pudo generar el PNG en el servidor.";
      if (err && typeof err === 'object' && 'response' in err) {
        const resp = (err as any).response;
        if (resp?.data instanceof Blob) {
          try {
            const text = await resp.data.text();
            const parsed = JSON.parse(text);
            if (parsed.detail) msg = parsed.detail;
          } catch {}
        } else if (resp?.data?.detail) {
          msg = resp.data.detail;
        }
      }
      push(msg, "error");
    } finally {
      setExportingFacetPng(false);
    }
  };

  const handleExportCombinedSvg = () => {
    setExportingFacetSvg(true);
    try {
      const instanceId = facetExportInstanceIdRef.current;
      if (instanceId == null) {
        push("Espera a que todas las gráficas terminen de cargar.", "error");
        return;
      }
      const charts = resolveFacetChartsForExport(instanceId, data.facets);
      if (charts == null || charts.length !== n) {
        push("Espera a que todas las gráficas terminen de cargar.", "error");
        return;
      }
      const layout = isStacked ? "column" : "row";
      const totalBaseW = isStacked ? 2400 : 1920;
      let sliceW: number;
      let sliceH: number;
      if (layout === "row") {
        const padding = 24 * 2;
        const gaps = Math.max(0, n - 1) * 14;
        sliceW = Math.floor((totalBaseW - padding - gaps) / n);
        sliceH = 1080;
      } else {
        sliceW = totalBaseW - 48;
        sliceH = Math.floor((1080 - Math.max(0, n - 1) * 14) / Math.max(n, 1));
      }

      const exportXLabelPx = 20;
      const maxCatLenExport = Math.max(
        ...data.facets.map((f) => maxCategoryCharLength(f.categories)),
        1,
      );
      const exportMarginBottom = !inverted
        ? Math.round(Math.min(44 + maxCatLenExport * exportXLabelPx * 0.62, 340))
        : undefined;

      /** Evita que las etiquetas del eje Y queden pegadas al borde en facetas estrechas. */
      const yLabelCharEstimate = Math.max(
        7,
        String(Math.round(sharedYAxisMax > 0 ? sharedYAxisMax : 0)).length + 4,
      );
      const exportMarginLeft = Math.min(
        175,
        Math.max(108, Math.round(36 + yLabelCharEstimate * 10 + sliceW * 0.04)),
      );

      const innerXmls: string[] = [];
      for (let i = 0; i < n; i += 1) {
        const chart = charts[i]!;
        const raw = chart.getSVG({
          ...HIGHCHARTS_GETSVG_MERGE_OPTIONS,
          chart: {
            ...(HIGHCHARTS_GETSVG_MERGE_OPTIONS.chart as Record<string, unknown>),
            width: sliceW,
            height: sliceH,
            backgroundColor: "#FFFFFF",
            marginLeft: exportMarginLeft,
            ...(exportMarginBottom !== undefined ? { marginBottom: exportMarginBottom } : {}),
          },
          exporting: {
            sourceWidth: sliceW,
            sourceHeight: sliceH,
          },
          ...(!inverted
            ? {
                xAxis: {
                  labels: {
                    rotation: -90,
                    align: "right",
                    reserveSpace: true,
                    autoRotation: false,
                    style: { color: "#334155", fontSize: `${exportXLabelPx}px` },
                  } as unknown as Highcharts.XAxisLabelsOptions,
                  lineWidth: 1,
                  lineColor: "#334155",
                  tickWidth: 1,
                  tickColor: "#334155",
                },
                yAxis: {
                  lineWidth: 1,
                  lineColor: "#334155",
                },
              }
            : {}),
        } as Highcharts.Options);
        const fixed = i === 0 ? raw : remapSvgFragmentIds(raw, `f${i}_`);
        innerXmls.push(extractSvgRootInnerXml(fixed));
      }

      const exportLegendItems =
        sharedLegendItems.length > 0
          ? sharedLegendItems.map(({ name, color }) => ({
              name,
              color,
              hidden: hiddenSeriesNames.has(name),
            }))
          : undefined;

      const facetLabels = data.facets.map((f) => {
        const simPart = f.display_name?.trim() || f.scenario_name;
        const tagPart = f.scenario_tag_name?.trim();
        return tagPart ? `${simPart} — ${tagPart}` : simPart;
      });
      const doc = buildCombinedFacetSvgDocument({
        mainTitle: data.title,
        fragmentInnerXmls: innerXmls,
        layout,
        sliceW,
        sliceH,
        facetLabels,
        ...(exportLegendItems ? { legendItems: exportLegendItems } : {}),
        ...(facetExportClean ? { clean: true } : {}),
      });
      const base = compareFacetClientFilenameBase(data, facetExportFilenameMode);
      const filename = `comparativa-facet-${base}-${new Date().toISOString().slice(0, 10)}.svg`;
      downloadBlob(new Blob([doc], { type: "image/svg+xml;charset=utf-8" }), filename);
      push("SVG combinado descargado (misma apariencia que exportar una gráfica).", "success");
    } catch (err) {
      console.error(err);
      push("No se pudo generar el SVG combinado.", "error");
    } finally {
      setExportingFacetSvg(false);
    }
  };

  return (
    <div className="w-full space-y-4">
      <div className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between lg:gap-4">
          <h3 className="m-0 min-w-0 flex-1 text-base font-bold text-slate-100" style={{ fontSize: "16px" }}>
            {data.title}
          </h3>
          <div className="flex w-full min-w-0 flex-wrap items-center justify-start gap-2 sm:justify-end lg:w-auto lg:flex-nowrap lg:shrink-0">
            {compactToolbar ? (
              <FacetExportKebab
                disabled={exportBusy}
                showServerPng={Boolean(serverFacetExport && serverFacetExport.jobIds.length > 1)}
                onExportPng={handleExportFacetPngServer}
                onExportSvg={handleExportCombinedSvg}
                exportingPng={exportingFacetPng}
                exportingSvg={exportingFacetSvg}
                exportClean={facetExportClean}
                onToggleClean={() => setFacetExportClean((v) => !v)}
              />
            ) : (
              <>
                {serverFacetExport && serverFacetExport.jobIds.length > 1 ? (
                  <>
                    <div className="flex min-w-0 max-w-full items-center gap-2">
                      <label
                        htmlFor={exportFilenameSelectId}
                        className="m-0 shrink-0 text-[10px] font-semibold uppercase tracking-wide text-slate-500"
                      >
                        Títulos de la gráfica
                      </label>
                      <select
                        id={exportFilenameSelectId}
                        value={facetExportFilenameMode}
                        onChange={(e) =>
                          setFacetExportFilenameMode(e.target.value as CompareFacetExportFilenameMode)
                        }
                        disabled={exportBusy}
                        className="h-9 min-w-[min(100%,12rem)] max-w-[min(100%,20rem)] shrink rounded-lg border border-slate-700 bg-slate-950 px-2.5 text-xs text-slate-200 disabled:opacity-50"
                      >
                        <option value="result">Nombre del resultado</option>
                        <option value="tags">Etiquetas (sin etiqueta → nombre del resultado)</option>
                      </select>
                    </div>
                    <label className="flex shrink-0 items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                      <input
                        type="checkbox"
                        checked={facetExportClean}
                        onChange={(e) => setFacetExportClean(e.target.checked)}
                        disabled={exportBusy}
                        className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-800 text-emerald-500 focus:ring-emerald-500"
                      />
                      Limpia
                    </label>
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={exportBusy}
                      onClick={() => void handleExportFacetPngServer()}
                      className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-emerald-700/50 bg-emerald-950/40 px-3 py-2 text-xs font-semibold text-emerald-100 hover:border-emerald-600 hover:bg-emerald-900/50 disabled:opacity-50"
                    >
                      <FileDown className="h-4 w-4 shrink-0" aria-hidden />
                      {exportingFacetPng ? "Generando PNG…" : "Descargar PNG (servidor)"}
                    </Button>
                  </>
                ) : null}
                <Button
                  type="button"
                  variant="ghost"
                  disabled={exportBusy}
                  onClick={handleExportCombinedSvg}
                  className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-xs font-semibold text-slate-200 hover:border-slate-600 hover:bg-slate-800/80 disabled:opacity-50"
                >
                  <FileDown className="h-4 w-4 shrink-0" aria-hidden />
                  {exportingFacetSvg ? "Generando SVG…" : "Descargar SVG (todas las facetas)"}
                </Button>
              </>
            )}
          </div>
        </div>
        <div className="w-full pb-2">
          <div
            className={
              isStacked
                ? "flex w-full flex-col gap-4"
                : "grid w-full gap-4"
            }
            style={
              isStacked
                ? undefined
                : {
                    gridTemplateColumns:
                      n === 1 || !isLg ? "minmax(0, 1fr)" : `repeat(${n}, minmax(0, 1fr))`,
                  }
            }
          >
            {data.facets.map((facet, idx) => {
              const simPart2 = facet.display_name?.trim() || facet.scenario_name;
              const tagPart2 = facet.scenario_tag_name?.trim();
              const facetLabel = tagPart2 ? `${simPart2} — ${tagPart2}` : simPart2;
              return (
                <div
                  key={facet.job_id}
                  className={
                    "min-w-0 rounded-lg border border-slate-800/80 bg-[#1e293b]/30 p-2" +
                    (isStacked ? " flex gap-2" : "")
                  }
                >
                  {isStacked ? (
                    <div
                      className="flex shrink-0 items-center justify-end text-right"
                      style={{ width: "120px", minWidth: "120px" }}
                    >
                      <span
                        className="text-sm font-bold leading-tight text-slate-100"
                        style={{ fontSize: "14px", lineHeight: "1.2" }}
                      >
                        {facetLabel}
                      </span>
                    </div>
                  ) : null}
                  <div className={isStacked ? "min-w-0 flex-1" : "w-full"}>
                    <FacetChart
                      facet={facet}
                      yAxisLabel={data.yAxisLabel}
                      sharedYAxisMax={sharedYAxisMax}
                      syncGroup={data.title}
                      hiddenSeriesNames={hiddenSeriesNames}
                      onLegendToggle={handleLegendToggle}
                      onLegendIsolate={handleLegendIsolate}
                      onLegendRestoreAll={handleLegendRestoreAll}
                      inverted={inverted}
                      chartHeight={facetChartHeight}
                      viewMode={viewMode}
                      facetCount={n}
                      showLeftTitle={isStacked}
                      showHighchartsLegend={
                        legendMode === "perFacet" && idx === 0
                      }
                      hoveredSeriesName={
                        useSharedLegendPanel ? effectiveLegendHover : null
                      }
                      facetExportInstanceId={facetExportInstanceIdRef.current!}
                      yAxisMin={yAxisMin ?? null}
                      yAxisMax={yAxisMax ?? null}
                      {...(fixedTickYears !== undefined ? { fixedTickYears } : {})}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        {useSharedLegendPanel ? (
        <div
          className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-3"
          role="group"
          aria-label="Leyenda de series (compartida)"
        >
          <p className="m-0 mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
            Leyenda (todas las gráficas)
          </p>
          <div className="flex flex-wrap gap-2">
            {sharedLegendItems.map(({ name, color }) => {
              const hidden = hiddenSeriesNames.has(name);
              const isLegendHover = !hidden && effectiveLegendHover === name;
              return (
                <button
                  key={name}
                  type="button"
                  onClick={() =>
                    dispatchLegendClick(
                      htmlLegendDblclickStateRef.current,
                      name,
                      {
                        onToggle: handleLegendToggle,
                        onIsolate: handleLegendIsolate,
                        onRestoreAll: handleLegendRestoreAll,
                      },
                    )
                  }
                  onDoubleClick={(e) => {
                    // Evita selección de texto en dblclick rápidos.
                    e.preventDefault();
                  }}
                  onMouseEnter={() => {
                    if (!hidden) {
                      setLegendHover({ dataSig: seriesStateSignature, seriesName: name });
                    }
                  }}
                  onMouseLeave={() =>
                    setLegendHover({ dataSig: seriesStateSignature, seriesName: null })
                  }
                  onFocus={() => {
                    if (!hidden) {
                      setLegendHover({ dataSig: seriesStateSignature, seriesName: name });
                    }
                  }}
                  onBlur={() =>
                    setLegendHover({ dataSig: seriesStateSignature, seriesName: null })
                  }
                  title={hidden ? "Mostrar serie" : "Ocultar serie"}
                  className={[
                    "inline-flex max-w-full items-center gap-2 rounded-full border px-2.5 py-1 text-left text-xs font-medium transition-colors",
                    hidden
                      ? "border-slate-700 bg-slate-900/60 text-slate-500 line-through opacity-70"
                      : [
                          "border-slate-600 bg-slate-900/40 text-slate-200 hover:border-slate-500 hover:bg-slate-800/60",
                          isLegendHover
                            ? "ring-2 ring-cyan-400/50 border-cyan-500/35 bg-slate-800/80 z-10"
                            : "",
                        ].join(" "),
                  ].join(" ")}
                >
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: hidden ? "#475569" : color }}
                    aria-hidden
                  />
                  <span className="min-w-0 truncate">{name}</span>
                </button>
              );
            })}
          </div>
        </div>
        ) : null}
      </div>
    </div>
  );
};
