/**
 * ChartViewerPage — Visor amplificado de una sola gráfica.
 *
 * Esta página vive fuera de `AppLayout` (sin barra de navegación lateral)
 * para maximizar el área de visualización. Es el destino al que apuntan los
 * "share links" generados desde Resultados.
 *
 * Layout:
 *   ┌────────────────────────────────────────────────────────┐
 *   │ Header (título, atrás, ⚙ toggle)                       │
 *   ├────────────────────────────────────────────┬───────────┤
 *   │                                            │ Config    │
 *   │            CHART (ancho completo)          │ ─────────  │
 *   │                                            │ ▼ Escen.  │
 *   │                                            │ ▼ Compar. │
 *   │                                            │ ▼ Gráfica │
 *   └────────────────────────────────────────────┴───────────┘
 *
 * El chart usa una altura calculada dinámicamente del viewport (no aspect
 * ratio fijo) para que se vea ancho y alto al mismo tiempo sin extremos.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { paths } from "@/routes/paths";
import { simulationApi } from "@/features/simulation/api/simulationApi";
import { ChartSelector } from "@/shared/charts/ChartSelector";
import type { ChartSelection } from "@/shared/charts/ChartSelector";
import { HighchartsChart } from "@/shared/charts/HighchartsChart";
import { LineChart } from "@/shared/charts/LineChart";
import { ParetoChart } from "@/shared/charts/ParetoChart";
import { CompareChart } from "@/shared/charts/CompareChart";
import { CompareChartFacet } from "@/shared/charts/CompareChartFacet";
import { ChartDataTable } from "@/shared/charts/ChartDataTable";
import { decodeChartShareParams } from "@/shared/charts/chartShareLink";
import { getDefaultChartSelection } from "@/shared/charts/defaultChartSelection";
import type {
  ChartDataResponse,
  CompareChartFacetResponse,
  CompareChartResponse,
  ParetoChartResponse,
  ResultSummaryResponse,
} from "@/types/domain";
import type { CompareViewMode } from "@/shared/charts/ScenarioComparer";

// ─── Constantes ─────────────────────────────────────────────────────────────

/** Altura mínima/máxima del chart, calculada del viewport en cada resize. */
const HEADER_HEIGHT = 64;
const CHART_PADDING = 56; // padding del card + márgenes externos

// ─── Helpers ────────────────────────────────────────────────────────────────

function computeChartHeight(): number {
  if (typeof window === "undefined") return 600;
  return Math.max(420, Math.min(820, window.innerHeight - HEADER_HEIGHT - CHART_PADDING));
}

// ─── Subcomponentes ─────────────────────────────────────────────────────────

interface AccordionProps {
  title: string;
  summary: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

/** Acordeón con resumen del estado actual cuando está cerrado. */
function Accordion({ title, summary, defaultOpen, children }: AccordionProps) {
  const [open, setOpen] = useState(Boolean(defaultOpen));
  return (
    <div className="border-b border-slate-800/80 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-start justify-between gap-3 px-4 py-3 text-left hover:bg-slate-800/40 transition-colors"
        aria-expanded={open}
      >
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-cyan-300/80">
            {title}
          </div>
          {!open && summary ? (
            <div className="mt-1 text-xs text-slate-200 line-clamp-2 break-words">
              {summary}
            </div>
          ) : null}
        </div>
        <span
          className={`text-slate-400 text-sm shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
          aria-hidden
        >
          ▸
        </span>
      </button>
      {open ? <div className="px-4 pb-3">{children}</div> : null}
    </div>
  );
}

// ─── Página ─────────────────────────────────────────────────────────────────

export function ChartViewerPage() {
  const { jobId: jobIdParam } = useParams<{ jobId: string }>();
  const primaryJobId = Number(jobIdParam);
  const [searchParams] = useSearchParams();

  // ── State principal ──
  const [chartSelection, setChartSelection] = useState<ChartSelection>(() => {
    const decoded = decodeChartShareParams(searchParams);
    if (decoded.selection?.tipo) return decoded.selection as ChartSelection;
    return getDefaultChartSelection();
  });
  const [chartBarOrientation, setChartBarOrientation] = useState<"vertical" | "horizontal">(() => {
    return decodeChartShareParams(searchParams).barOrientation ?? "vertical";
  });
  const [compareJobIds, setCompareJobIds] = useState<number[]>(() => {
    const decoded = decodeChartShareParams(searchParams);
    if (decoded.jobIds && decoded.jobIds.length > 0) return decoded.jobIds;
    return Number.isFinite(primaryJobId) && primaryJobId > 0 ? [primaryJobId] : [];
  });
  const [compareMode, setCompareMode] = useState<"off" | CompareViewMode>(() => {
    const decoded = decodeChartShareParams(searchParams);
    if (decoded.compareMode && decoded.compareMode !== "off") return decoded.compareMode;
    const ids = decoded.jobIds ?? [];
    return ids.length >= 2 ? "facet" : "off";
  });
  const [yearsToPlot, setYearsToPlot] = useState<number[]>(() => {
    return decodeChartShareParams(searchParams).compareYearsToPlot ?? [
      2024, 2030, 2040, 2050,
    ];
  });
  const [facetPlacement, setFacetPlacement] = useState<"inline" | "stacked">(
    () => decodeChartShareParams(searchParams).facetPlacement ?? "inline",
  );
  const [facetLegendMode, setFacetLegendMode] = useState<"shared" | "perFacet">(
    () => decodeChartShareParams(searchParams).facetLegendMode ?? "shared",
  );

  // ── Sidebar abierto/cerrado ──
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // ── Chart height dinámico ──
  const [chartHeight, setChartHeight] = useState(() => computeChartHeight());
  useEffect(() => {
    const onResize = () => setChartHeight(computeChartHeight());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // ── Listado de escenarios (para tabla en el sidebar) ──
  const [allSummaries, setAllSummaries] = useState<ResultSummaryResponse[]>([]);
  const [loadingSummaries, setLoadingSummaries] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setLoadingSummaries(true);
    simulationApi
      .listRuns({ scope: "global", status_filter: "SUCCEEDED", cantidad: 100 })
      .then(async (res) => {
        const runs = (res.data || []).filter((r) => !r.is_infeasible_result);
        const summaries = await Promise.all(
          runs.map((r) => simulationApi.getResultSummary(r.id).catch(() => null)),
        );
        if (cancelled) return;
        setAllSummaries(summaries.filter(Boolean) as ResultSummaryResponse[]);
      })
      .catch(console.error)
      .finally(() => {
        if (!cancelled) setLoadingSummaries(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Carga de datos del chart ──
  const [singleChartData, setSingleChartData] = useState<ChartDataResponse | null>(null);
  const [paretoData, setParetoData] = useState<ParetoChartResponse | null>(null);
  const [facetData, setFacetData] = useState<CompareChartFacetResponse | null>(null);
  const [byYearData, setByYearData] = useState<CompareChartResponse | null>(null);
  const [lineTotalData, setLineTotalData] = useState<ChartDataResponse | null>(null);
  const [loadingChart, setLoadingChart] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);

  const isComparing = compareJobIds.length >= 2 && compareMode !== "off";
  const effectiveCompareMode = isComparing ? compareMode : "off";

  // Fingerprint para evitar re-fetch redundante.
  const fpRef = useRef("");
  useEffect(() => {
    if (!Number.isFinite(primaryJobId) || primaryJobId <= 0) return;
    const fp = JSON.stringify({
      tipo: chartSelection.tipo,
      un: chartSelection.un,
      sf: chartSelection.sub_filtro,
      loc: chartSelection.loc,
      v: chartSelection.variable,
      ag: chartSelection.agrupar_por,
      vm: chartSelection.viewMode,
      jobs: compareJobIds.join(","),
      cm: effectiveCompareMode,
      years: yearsToPlot.join(","),
    });
    if (fp === fpRef.current) return;
    fpRef.current = fp;

    let cancelled = false;
    setLoadingChart(true);
    setChartError(null);

    const wrap = async () => {
      try {
        if (effectiveCompareMode === "facet") {
          const params = {
            job_ids: compareJobIds.join(","),
            tipo: chartSelection.tipo,
            un: chartSelection.un,
            ...(chartSelection.sub_filtro ? { sub_filtro: chartSelection.sub_filtro } : {}),
            ...(chartSelection.loc ? { loc: chartSelection.loc } : {}),
            ...(chartSelection.variable ? { variable: chartSelection.variable } : {}),
            ...(chartSelection.agrupar_por ? { agrupar_por: chartSelection.agrupar_por } : {}),
          };
          const data = await simulationApi.getCompareFacetData(params);
          if (!cancelled) {
            setFacetData(data);
            setSingleChartData(null);
            setByYearData(null);
            setLineTotalData(null);
            setParetoData(null);
          }
          return;
        }
        if (effectiveCompareMode === "by-year") {
          const params = {
            job_ids: compareJobIds.join(","),
            tipo: chartSelection.tipo,
            un: chartSelection.un,
            years_to_plot: yearsToPlot.join(","),
            ...(chartSelection.sub_filtro ? { sub_filtro: chartSelection.sub_filtro } : {}),
            ...(chartSelection.loc ? { loc: chartSelection.loc } : {}),
            ...(chartSelection.agrupar_por ? { agrupacion: chartSelection.agrupar_por } : {}),
          };
          const data = await simulationApi.getCompareData(params);
          if (!cancelled) {
            setByYearData(data);
            setSingleChartData(null);
            setFacetData(null);
            setLineTotalData(null);
            setParetoData(null);
          }
          return;
        }
        if (effectiveCompareMode === "line-total") {
          const params = {
            job_ids: compareJobIds.join(","),
            tipo: chartSelection.tipo,
            un: chartSelection.un,
            ...(chartSelection.sub_filtro ? { sub_filtro: chartSelection.sub_filtro } : {}),
            ...(chartSelection.loc ? { loc: chartSelection.loc } : {}),
          };
          const data = await simulationApi.getCompareLineData(params);
          if (!cancelled) {
            setLineTotalData(data);
            setSingleChartData(null);
            setFacetData(null);
            setByYearData(null);
            setParetoData(null);
          }
          return;
        }
        // ── Modo single ──
        if (chartSelection.viewMode === "pareto") {
          const params = {
            tipo: chartSelection.tipo,
            un: chartSelection.un,
            ...(chartSelection.sub_filtro ? { sub_filtro: chartSelection.sub_filtro } : {}),
            ...(chartSelection.loc ? { loc: chartSelection.loc } : {}),
          };
          const data = await simulationApi.getParetoData(primaryJobId, params);
          if (!cancelled) {
            setParetoData(data);
            setSingleChartData(null);
            setFacetData(null);
            setByYearData(null);
            setLineTotalData(null);
          }
          return;
        }
        const params = {
          tipo: chartSelection.tipo,
          un: chartSelection.un,
          ...(chartSelection.sub_filtro ? { sub_filtro: chartSelection.sub_filtro } : {}),
          ...(chartSelection.loc ? { loc: chartSelection.loc } : {}),
          ...(chartSelection.variable ? { variable: chartSelection.variable } : {}),
          ...(chartSelection.agrupar_por ? { agrupar_por: chartSelection.agrupar_por } : {}),
        };
        const data = await simulationApi.getChartData(primaryJobId, params);
        if (!cancelled) {
          setSingleChartData(data);
          setFacetData(null);
          setByYearData(null);
          setLineTotalData(null);
          setParetoData(null);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setChartError(err instanceof Error ? err.message : "Error cargando datos.");
        }
      } finally {
        if (!cancelled) setLoadingChart(false);
      }
    };
    void wrap();
    return () => {
      cancelled = true;
    };
  }, [
    primaryJobId,
    chartSelection,
    compareJobIds,
    effectiveCompareMode,
    yearsToPlot,
  ]);

  // ── Resúmenes para mostrar nombres en la tabla ──
  const summariesByJob = useMemo(() => {
    const m = new Map<number, ResultSummaryResponse>();
    for (const s of allSummaries) m.set(s.job_id, s);
    return m;
  }, [allSummaries]);

  // ── Toggle de selección para comparación ──
  const toggleJobSelection = useCallback((jobId: number) => {
    setCompareJobIds((prev) => {
      if (prev.includes(jobId)) {
        const next = prev.filter((j) => j !== jobId);
        // Si quedan menos de 2, cambia a "off".
        if (next.length < 2) setCompareMode("off");
        return next.length === 0 ? [primaryJobId].filter((n) => n > 0) : next;
      }
      const next = [...prev, jobId];
      // Si pasamos a 2+ y estamos en off, sugerimos facet.
      if (next.length >= 2 && compareMode === "off") setCompareMode("facet");
      return next;
    });
  }, [primaryJobId, compareMode]);

  // ── Resúmenes para los acordeones ──
  const scenariosSummary = compareJobIds.length === 0
    ? "Sin selección"
    : compareJobIds
        .map((jid) => {
          const s = summariesByJob.get(jid);
          return s?.display_name?.trim() || s?.scenario_name || `Job ${jid}`;
        })
        .join(" · ");

  const compareSummary = compareJobIds.length < 2
    ? "—"
    : effectiveCompareMode === "facet"
      ? "Paneles por escenario (facet)"
      : effectiveCompareMode === "by-year"
        ? `Por año (${yearsToPlot.length} años)`
        : effectiveCompareMode === "line-total"
          ? "Líneas totales"
          : "Sin comparación";

  const chartConfigSummary = [
    chartSelection.tipo,
    chartSelection.un,
    chartSelection.viewMode || "column",
    chartSelection.agrupar_por,
  ]
    .filter(Boolean)
    .join(" · ");

  // ── Render ──
  if (!Number.isFinite(primaryJobId) || primaryJobId <= 0) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-200 p-8">
        <h1 className="text-xl font-bold">Visor de gráfica</h1>
        <p className="mt-3 text-sm text-slate-400">
          Job ID inválido en la URL.
        </p>
        <Link to={paths.results} className="text-cyan-400 hover:underline">
          ← Volver a Resultados
        </Link>
      </div>
    );
  }

  return (
    <div className="chart-viewer-page min-h-screen bg-slate-950 text-slate-200 flex flex-col">
      {/* En el visor amplificado los tooltips deben ser bien legibles.
          Highcharts pone los estilos del tooltip inline en el SVG, así que
          los sobre-escribimos con un selector global mientras esta página
          esté montada. */}
      <style>{`
        .chart-viewer-page .highcharts-tooltip text,
        .chart-viewer-page .highcharts-tooltip span {
          font-size: 17px !important;
        }
      `}</style>
      {/* Header */}
      <header
        className="flex items-center justify-between gap-4 border-b border-slate-800/70 bg-slate-900/60 px-5"
        style={{ height: HEADER_HEIGHT }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <Link
            to={paths.resultsDetail(primaryJobId)}
            className="rounded-md border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700/60"
          >
            ← Resultados
          </Link>
          <div className="min-w-0">
            <h1 className="m-0 truncate text-base font-semibold text-white">
              {singleChartData?.title
                || facetData?.title
                || byYearData?.title
                || lineTotalData?.title
                || paretoData?.title
                || "Visor de gráfica"}
            </h1>
            <p className="m-0 text-[11px] text-slate-500">
              Job {primaryJobId}
              {compareJobIds.length > 1 ? ` · comparado con ${compareJobIds.length - 1}` : ""}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setSidebarOpen((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-sm font-semibold text-cyan-300 hover:bg-cyan-500/20"
          title="Abrir/Cerrar configuración"
          aria-label="Abrir configuración"
          aria-expanded={sidebarOpen}
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Configuración
        </button>
      </header>

      {/* Body: chart + sidebar */}
      <div className="flex-1 flex min-h-0">
        {/* Chart area */}
        <main className="flex-1 min-w-0 p-6 overflow-auto">
          {chartError ? (
            <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
              {chartError}
            </div>
          ) : null}
          <div
            className="rounded-xl border border-slate-800 bg-slate-900/30 p-4 relative"
            style={{ minHeight: chartHeight + 32 }}
          >
            {loadingChart ? (
              <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-slate-950/70 backdrop-blur-sm">
                <div className="flex flex-col items-center gap-2">
                  <div className="h-8 w-8 rounded-full border-2 border-slate-700 border-t-emerald-500 animate-spin" />
                  <span className="text-sm text-slate-400">Cargando gráfica…</span>
                </div>
              </div>
            ) : null}

            {effectiveCompareMode === "facet" && facetData ? (
              <CompareChartFacet
                data={facetData}
                barOrientation={chartBarOrientation}
                facetPlacement={facetPlacement}
                legendMode={facetLegendMode}
                viewMode={chartSelection.viewMode === "line" ? "line" : "column"}
                serverFacetExport={{ jobIds: compareJobIds, selection: chartSelection }}
                compactToolbar
              />
            ) : effectiveCompareMode === "by-year" && byYearData ? (
              <CompareChart data={byYearData} barOrientation={chartBarOrientation} sharedYAxis={true} />
            ) : effectiveCompareMode === "line-total" && lineTotalData ? (
              <LineChart data={lineTotalData} amplified chartHeight={chartHeight} />
            ) : chartSelection.viewMode === "pareto" && paretoData ? (
              <ParetoChart
                data={paretoData}
                serverExport={{ jobId: primaryJobId, selection: chartSelection }}
                amplified
                chartHeight={chartHeight}
              />
            ) : chartSelection.viewMode === "table" && singleChartData ? (
              <ChartDataTable
                data={singleChartData}
                periodYears={chartSelection.tablePeriodYears ?? null}
                cumulative={Boolean(chartSelection.tableCumulative)}
                serverExport={{ jobId: primaryJobId, selection: chartSelection }}
              />
            ) : chartSelection.viewMode === "line" && singleChartData ? (
              <LineChart
                data={singleChartData}
                serverExport={{ jobId: primaryJobId, selection: chartSelection }}
                amplified
                chartHeight={chartHeight}
              />
            ) : singleChartData ? (
              <HighchartsChart
                data={singleChartData}
                barOrientation={chartBarOrientation}
                serverExport={{ jobId: primaryJobId, selection: chartSelection }}
                stackType={chartSelection.viewMode === "area" ? "area" : "column"}
                amplified
                chartHeight={chartHeight}
              />
            ) : !loadingChart ? (
              <div className="flex h-[400px] items-center justify-center text-sm text-slate-500">
                Sin datos.
              </div>
            ) : null}
          </div>
        </main>

        {/* Sidebar de configuración */}
        {sidebarOpen ? (
          <aside
            className="w-[380px] shrink-0 border-l border-slate-800/70 bg-slate-900/40 overflow-y-auto"
            style={{ maxHeight: `calc(100vh - ${HEADER_HEIGHT}px)` }}
          >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-800/70 bg-slate-900/95 px-4 py-3 backdrop-blur">
              <h2 className="m-0 text-sm font-semibold uppercase tracking-wider text-cyan-200">
                Configuración
              </h2>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                className="text-slate-400 text-xl leading-none hover:text-slate-200"
                aria-label="Cerrar configuración"
              >
                ×
              </button>
            </div>

            {/* Acordeón 1 — Escenarios */}
            <Accordion title="Escenarios" summary={scenariosSummary} defaultOpen>
              <ScenariosTable
                summaries={allSummaries}
                loading={loadingSummaries}
                selectedJobIds={compareJobIds}
                primaryJobId={primaryJobId}
                onToggle={toggleJobSelection}
              />
            </Accordion>

            {/* Acordeón 2 — Tipo de comparación */}
            <Accordion title="Tipo de comparación" summary={compareSummary}>
              {compareJobIds.length < 2 ? (
                <p className="m-0 text-xs text-slate-500">
                  Selecciona al menos 2 escenarios arriba para comparar.
                </p>
              ) : (
                <div className="space-y-2">
                  {([
                    { v: "facet", label: "Paneles por escenario (facet)" },
                    { v: "by-year", label: "Comparación por año" },
                    { v: "line-total", label: "Líneas totales" },
                  ] as const).map((opt) => (
                    <label key={opt.v} className="flex items-center gap-2 text-xs text-slate-200 cursor-pointer">
                      <input
                        type="radio"
                        name="cmpmode"
                        value={opt.v}
                        checked={compareMode === opt.v}
                        onChange={() => setCompareMode(opt.v)}
                      />
                      <span>{opt.label}</span>
                    </label>
                  ))}
                  {compareMode === "by-year" ? (
                    <label className="grid gap-1 mt-2">
                      <span className="text-[10px] uppercase tracking-wider text-slate-400">
                        Años (separados por coma)
                      </span>
                      <input
                        type="text"
                        value={yearsToPlot.join(",")}
                        onChange={(e) => {
                          const ys = e.target.value
                            .split(",")
                            .map((s) => Number(s.trim()))
                            .filter((n) => Number.isFinite(n));
                          setYearsToPlot(ys);
                        }}
                        className="rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100"
                      />
                    </label>
                  ) : null}
                  {compareMode === "facet" ? (
                    <div className="grid gap-2 mt-2">
                      <label className="grid gap-1">
                        <span className="text-[10px] uppercase tracking-wider text-slate-400">
                          Disposición de facets
                        </span>
                        <select
                          value={facetPlacement}
                          onChange={(e) =>
                            setFacetPlacement(e.target.value as "inline" | "stacked")
                          }
                          className="rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100"
                        >
                          <option value="inline">En línea</option>
                          <option value="stacked">Apilados verticalmente</option>
                        </select>
                      </label>
                      <label className="grid gap-1">
                        <span className="text-[10px] uppercase tracking-wider text-slate-400">
                          Leyenda
                        </span>
                        <select
                          value={facetLegendMode}
                          onChange={(e) =>
                            setFacetLegendMode(e.target.value as "shared" | "perFacet")
                          }
                          className="rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100"
                        >
                          <option value="shared">Compartida</option>
                          <option value="perFacet">Una por panel</option>
                        </select>
                      </label>
                    </div>
                  ) : null}
                </div>
              )}
            </Accordion>

            {/* Acordeón 3 — Configuración de la gráfica (módulo, tipo, unidades, agrupar, vista) */}
            <Accordion
              title="Módulo · Gráfica · Vista"
              summary={chartConfigSummary}
              defaultOpen
            >
              <div className="-mx-2">
                <ChartSelector
                  value={chartSelection}
                  onChange={setChartSelection}
                  hideGroupBy={effectiveCompareMode === "line-total"}
                  barOrientation={chartBarOrientation}
                  onChangeBarOrientation={setChartBarOrientation}
                />
              </div>
            </Accordion>
          </aside>
        ) : null}
      </div>
    </div>
  );
}

// ─── Tabla de escenarios ────────────────────────────────────────────────────

interface ScenariosTableProps {
  summaries: ResultSummaryResponse[];
  loading: boolean;
  selectedJobIds: number[];
  primaryJobId: number;
  onToggle: (jobId: number) => void;
}

function ScenariosTable({
  summaries,
  loading,
  selectedJobIds,
  primaryJobId,
  onToggle,
}: ScenariosTableProps) {
  const [filterText, setFilterText] = useState("");
  const [showOnlyFavorites, setShowOnlyFavorites] = useState(false);

  const filtered = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    return summaries
      .filter((s) => {
        if (showOnlyFavorites && !s.is_favorite) return false;
        if (!q) return true;
        const name = (s.display_name || s.scenario_name || `Job ${s.job_id}`).toLowerCase();
        const tags = (s.scenario_tags ?? [])
          .map((t) => t.name.toLowerCase())
          .join(" ");
        return name.includes(q) || tags.includes(q);
      })
      .sort((a, b) => {
        // Primero el primario, luego favoritos, luego por job_id desc.
        if (a.job_id === primaryJobId) return -1;
        if (b.job_id === primaryJobId) return 1;
        if (Boolean(a.is_favorite) !== Boolean(b.is_favorite)) {
          return a.is_favorite ? -1 : 1;
        }
        return b.job_id - a.job_id;
      });
  }, [summaries, filterText, showOnlyFavorites, primaryJobId]);

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          placeholder="Filtrar por nombre o tag…"
          className="flex-1 min-w-0 rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100 placeholder:text-slate-600"
        />
        <label className="inline-flex items-center gap-1 text-[11px] text-slate-300 whitespace-nowrap">
          <input
            type="checkbox"
            checked={showOnlyFavorites}
            onChange={(e) => setShowOnlyFavorites(e.target.checked)}
          />
          Solo ★
        </label>
      </div>

      {loading ? (
        <p className="text-xs text-slate-500">Cargando escenarios…</p>
      ) : filtered.length === 0 ? (
        <p className="text-xs text-slate-500">Sin escenarios.</p>
      ) : (
        <div
          className="rounded-lg border border-slate-800/80 overflow-hidden"
          style={{ maxHeight: 360, overflowY: "auto" }}
        >
          <table className="w-full text-xs">
            <thead className="bg-slate-800/60 sticky top-0">
              <tr>
                <th className="px-2 py-1.5 text-left w-8"></th>
                <th className="px-2 py-1.5 text-left font-semibold text-slate-300">
                  Escenario
                </th>
                <th className="px-2 py-1.5 text-left font-semibold text-slate-300">
                  Tags
                </th>
                <th className="px-2 py-1.5 text-center font-semibold text-slate-300 w-8">
                  ★
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => {
                const checked = selectedJobIds.includes(s.job_id);
                const isPrimary = s.job_id === primaryJobId;
                return (
                  <tr
                    key={s.job_id}
                    className={`border-t border-slate-800/60 ${checked ? "bg-cyan-500/5" : "hover:bg-slate-800/30"} ${isPrimary ? "ring-1 ring-cyan-500/30" : ""}`}
                  >
                    <td className="px-2 py-1.5">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => onToggle(s.job_id)}
                        disabled={isPrimary && selectedJobIds.length === 1}
                        title={
                          isPrimary && selectedJobIds.length === 1
                            ? "Job principal — no se puede desmarcar"
                            : undefined
                        }
                      />
                    </td>
                    <td className="px-2 py-1.5 text-slate-100 break-words">
                      <div className="font-medium">
                        {s.display_name?.trim() || s.scenario_name || `Job ${s.job_id}`}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        Job {s.job_id}
                      </div>
                    </td>
                    <td className="px-2 py-1.5">
                      <div className="flex flex-wrap gap-1">
                        {(s.scenario_tags ?? []).slice(0, 3).map((t) => (
                          <span
                            key={t.id}
                            className="inline-block rounded-full bg-slate-700/60 px-1.5 py-0.5 text-[9px] text-slate-200"
                            style={t.color ? { background: `${t.color}33`, color: t.color } : {}}
                          >
                            {t.name}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      {s.is_favorite ? <span className="text-yellow-400">★</span> : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
