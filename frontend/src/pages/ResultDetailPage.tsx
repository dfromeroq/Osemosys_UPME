import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import {
  DollarSign,
  LayoutGrid,
  Leaf,
  List,
  Zap,
} from 'lucide-react';
import { simulationApi } from '../features/simulation/api/simulationApi';
import type {
  ResultSummaryResponse,
  ChartCatalogItem,
  ChartDataResponse,
  CompareChartResponse,
  CompareChartFacetResponse,
  CompareMode,
  ParetoChartResponse,
  RunResult,
  SimulationRun,
} from '../types/domain';
import { paths } from '../routes/paths';
import { RunDisplayNameEditor } from '../features/simulation/components/RunDisplayNameEditor';
import { ChartSelector, getChartLabel, type ChartSelection } from '../shared/charts/ChartSelector';
import { getDefaultChartSelection } from '../shared/charts/defaultChartSelection';
import { ScenarioComparer, type CompareViewMode } from '../shared/charts/ScenarioComparer';
import { HighchartsChart } from '../shared/charts/HighchartsChart';
import { LineChart } from '../shared/charts/LineChart';
import { ChartDataTable } from '../shared/charts/ChartDataTable';
import {
  buildChartShareUrl,
  copyToClipboard,
  decodeChartShareParams,
} from '../shared/charts/chartShareLink';
import {
  SeriesOrderModal,
  reorderChartSeries,
  reorderFacetSeries,
  reorderByYearSeries,
} from '../shared/charts/SeriesOrderModal';
import { CompareChart } from '../shared/charts/CompareChart';
import { CompareChartFacet } from '../shared/charts/CompareChartFacet';
import { ParetoChart } from '../shared/charts/ParetoChart';
import type {
  ChartBarOrientation,
  ChartFacetLegendMode,
  ChartFacetPlacement,
} from '../shared/charts/chartLayoutPreferences';
import {
  loadChartBarOrientation,
  loadChartFacetLegendMode,
  loadChartFacetPlacement,
  saveChartBarOrientation,
  saveChartFacetLegendMode,
  saveChartFacetPlacement,
} from '../shared/charts/chartLayoutPreferences';
import { Button } from '../shared/components/Button';
import { ScenarioTagChip } from '../shared/components/ScenarioTagChip';
import { downloadBlob } from '../shared/utils/downloadBlob';
import { formatCompactNumber, formatPercent } from '../shared/utils/numberFormat';
import { SaveChartModal } from '../features/reports/components/SaveChartModal';
import { SyntheticSeriesEditor } from '../shared/charts/SyntheticSeriesEditor';
import {
  loadSyntheticSeries,
  saveSyntheticSeries,
  syntheticSeriesSignature,
} from '../shared/charts/syntheticSeriesStorage';
import type { SyntheticSeries } from '../types/domain';
import { savedChartsApi } from '@/features/reports/api/savedChartsApi';
import { FavoriteStarButton } from '../features/simulation/components/FavoriteStarButton';

const MAX_COMPARE_COLUMNS = 10;
const EXECUTIONS_TABLE_PAGE_SIZE = 10;

const BADGE_OPTIMAL =
  'inline-flex shrink-0 items-center px-2 py-1 rounded-full bg-green-500/10 text-green-400 text-xs font-bold border border-green-500/20';

function getSolverStatusPresentation(statusRaw: string): { label: string; badgeClass: string } {
  const trimmed = statusRaw.trim();
  const label = (trimmed || 'UNKNOWN').toUpperCase();
  const s = trimmed.toLowerCase();

  const pill =
    'inline-flex shrink-0 items-center px-2 py-1 rounded-full text-xs font-bold border';

  if (s.includes('optimal')) {
    return { label, badgeClass: BADGE_OPTIMAL };
  }
  if (s.includes('infeasible')) {
    return {
      label,
      badgeClass: `${pill} bg-rose-500/10 text-rose-400 border-rose-500/20`,
    };
  }
  if (s.includes('unbounded')) {
    return {
      label,
      badgeClass: `${pill} bg-violet-500/10 text-violet-400 border-violet-500/20`,
    };
  }
  if (s.includes('limit') || s.includes('interrupt') || s.includes('stopped')) {
    return {
      label,
      badgeClass: `${pill} bg-amber-500/10 text-amber-400 border-amber-500/20`,
    };
  }
  if (s.includes('fail') || s.includes('error')) {
    return {
      label,
      badgeClass: `${pill} bg-red-500/10 text-red-400 border-red-500/20`,
    };
  }
  return {
    label,
    badgeClass: `${pill} bg-slate-500/10 text-slate-400 border-slate-500/20`,
  };
}

type ScenarioCardProps = {
  summary: ResultSummaryResponse;
  isCurrent?: boolean;
};

function ScenarioCard({ summary, isCurrent = false }: ScenarioCardProps) {
  const status = getSolverStatusPresentation(summary.solver_status);
  const resultTitle =
    summary.display_name?.trim() ||
    summary.scenario_name?.trim() ||
    `Job #${summary.job_id}`;

  return (
    <div
      className={[
        'bg-[#0f172a] border border-slate-800 rounded-xl p-5 shadow-2xl',
        isCurrent ? 'ring-2 ring-cyan-500/35' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <header className="flex flex-col gap-3 pb-4 border-b border-slate-800/60 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="min-w-0 flex-1 space-y-3">
          <div className="space-y-1.5">
            <p className="m-0 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
              Nombre del resultado
            </p>
            <p className="m-0 text-lg font-semibold text-white break-words">{resultTitle}</p>
          </div>
          <div className="space-y-1.5 border-t border-slate-800/60 pt-3">
            <p className="m-0 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
              Escenario (referencia)
            </p>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="text-sm font-medium text-slate-300">
                {summary.scenario_name?.trim() || '—'}
              </span>
              {(summary.scenario_tags && summary.scenario_tags.length > 0
                ? summary.scenario_tags
                : summary.scenario_tag
                ? [summary.scenario_tag]
                : []
              ).map((t) => (
                <ScenarioTagChip key={t.id} tag={t} size="sm" />
              ))}
              {isCurrent ? (
                <span className="inline-flex shrink-0 items-center rounded-full border border-cyan-500/25 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-cyan-400">
                  Actual
                </span>
              ) : null}
              <Link
                to={`/app/results/${summary.job_id}`}
                className="text-xs font-semibold text-cyan-400 hover:text-cyan-300 hover:underline"
              >
                Abrir detalle
              </Link>
            </div>
          </div>
          <p className="m-0 text-[10px] text-slate-600 font-mono">
            ID de ejecución (referencia interna) · {summary.job_id}
          </p>
        </div>
        <span className={`${status.badgeClass} self-start sm:mt-0.5`}>{status.label}</span>
      </header>

      <div className="pt-3 flex flex-col gap-1">
        <ScenarioMetricRow
          icon={DollarSign}
          label="Objective Value (USD)"
          value={formatCompactNumber(summary.objective_value, 2)}
          highlight
        />
        <ScenarioMetricRow
          icon={Zap}
          label="Demand Coverage"
          value={formatPercent(summary.coverage_ratio, 2)}
        />
        <ScenarioMetricRow
          icon={Leaf}
          label="CO₂ Emissions (MtCO₂eq)"
          value={formatCompactNumber(summary.total_co2, 2)}
        />
      </div>
    </div>
  );
}

function ScenarioMetricRow({
  icon: Icon,
  label,
  value,
  highlight = false,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex justify-between items-center gap-4 py-2 border-b border-slate-800/50 last:border-0">
      <span className="text-slate-400 text-sm flex items-center gap-2 min-w-0">
        <Icon className="w-4 h-4 shrink-0 text-slate-500" aria-hidden />
        {label}
      </span>
      <span
        className={[
          'font-mono font-bold tabular-nums text-right shrink-0',
          highlight ? 'text-cyan-300 text-[15px]' : 'text-white',
        ].join(' ')}
      >
        {value}
      </span>
    </div>
  );
}

export function ResultDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const currentRunId = Number(runId);

  // Summary & error
  const [summary, setSummary] = useState<ResultSummaryResponse | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [runMeta, setRunMeta] = useState<SimulationRun | null>(null);

  // All summaries for comparison table
  const [allSummaries, setAllSummaries] = useState<ResultSummaryResponse[]>([]);
  const [loadingSummaries, setLoadingSummaries] = useState(true);
  /** Hasta 4 jobs para la vista en columnas (independiente de la comparación de gráficos). */
  const [selectedCompareColumnJobIds, setSelectedCompareColumnJobIds] = useState<number[]>([]);
  /** Disposición de las tarjetas KPI: cuadrícula o lista compacta. */
  const [scenarioCardsViewMode, setScenarioCardsViewMode] = useState<'grid' | 'list'>('grid');
  /** Paginación de la tabla de ejecuciones (comparativa). */
  const [executionsTablePage, setExecutionsTablePage] = useState(1);
  /** Solo reinicia la selección por defecto al cambiar de run; no en cada nuevo array `allSummaries`. */
  const compareColumnInitKeyRef = useRef<number | null>(null);
  const selectedCompareColumnJobIdsRef = useRef(selectedCompareColumnJobIds);
  selectedCompareColumnJobIdsRef.current = selectedCompareColumnJobIds;

  // Chart selector (tipo por defecto = primera gráfica del catálogo)
  const [chartSelection, setChartSelection] = useState<ChartSelection>(() => getDefaultChartSelection());

  /**
   * Catálogo de gráficas (incluye ``data_explorer_filters`` por chart) para
   * construir el URL del Data Explorer cuando el usuario hace click en
   * "Ver Datos de Resultados".
   */
  const [chartCatalog, setChartCatalog] = useState<ChartCatalogItem[]>([]);
  useEffect(() => {
    let cancelled = false;
    simulationApi
      .getChartCatalog()
      .then((items) => {
        if (!cancelled) setChartCatalog(items);
      })
      .catch(() => {
        if (!cancelled) setChartCatalog([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Comparison state: la selección de escenarios vive 100% en la tabla superior
  // (`selectedCompareColumnJobIds`). Aquí solo se guarda el modo de vista y los
  // años a graficar cuando el modo es `by-year`.
  const [compareViewMode, setCompareViewMode] = useState<CompareViewMode>('facet');
  const [compareYearsToPlot, setCompareYearsToPlot] = useState<number[]>([
    2024, 2030, 2040, 2050,
  ]);

  // Chart data
  const [singleChartData, setSingleChartData] = useState<ChartDataResponse | null>(null);
  const [compareChartData, setCompareChartData] = useState<CompareChartResponse | null>(null);
  const [compareFacetData, setCompareFacetData] = useState<CompareChartFacetResponse | null>(null);
  const [compareLineData, setCompareLineData] = useState<ChartDataResponse | null>(null);
  const [paretoData, setParetoData] = useState<ParetoChartResponse | null>(null);
  const [loadingChart, setLoadingChart] = useState(false);

  const [chartBarOrientation, setChartBarOrientation] = useState<ChartBarOrientation>(() =>
    loadChartBarOrientation(),
  );
  const [chartFacetPlacement, setChartFacetPlacement] = useState<ChartFacetPlacement>(() =>
    loadChartFacetPlacement(),
  );
  const [chartFacetLegendMode, setChartFacetLegendMode] = useState<ChartFacetLegendMode>(() =>
    loadChartFacetLegendMode(),
  );

  useEffect(() => {
    saveChartBarOrientation(chartBarOrientation);
  }, [chartBarOrientation]);

  useEffect(() => {
    saveChartFacetPlacement(chartFacetPlacement);
  }, [chartFacetPlacement]);

  useEffect(() => {
    saveChartFacetLegendMode(chartFacetLegendMode);
  }, [chartFacetLegendMode]);

  // Export state: 'svg' | 'excel' mientras se descarga, null si no
  const [exportingType, setExportingType] = useState<'svg' | 'excel' | 'csvzip' | null>(null);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const [showSaveChartModal, setShowSaveChartModal] = useState(false);
  const [savedChartToast, setSavedChartToast] = useState<string | null>(null);
  // Toast de feedback al copiar el enlace compartible.
  const [shareLinkToast, setShareLinkToast] = useState<string | null>(null);

  // ── Modificadores de gráfica (orden custom + rango Y) ─────────────────
  // ``customSeriesOrder`` = lista de nombres de serie en el orden deseado.
  // ``null`` = orden natural (el que devuelve el backend).
  const [customSeriesOrder, setCustomSeriesOrder] = useState<string[] | null>(null);
  // Override de min/max del eje Y. ``null`` en cualquiera = auto.
  const [yAxisMin, setYAxisMin] = useState<number | null>(null);
  const [yAxisMax, setYAxisMax] = useState<number | null>(null);
  const [seriesOrderOpen, setSeriesOrderOpen] = useState(false);

  // Resetear modificadores cuando cambia la identidad del chart
  // (otro tipo, otra agrupación, otro filtro): el conjunto de series cambia,
  // así que un orden custom anterior dejaría de tener sentido.
  const chartIdentityKey =
    `${chartSelection.tipo}|${chartSelection.sub_filtro ?? ''}|${chartSelection.loc ?? ''}|${chartSelection.variable ?? ''}|${chartSelection.agrupar_por ?? ''}`;
  useEffect(() => {
    setCustomSeriesOrder(null);
    setYAxisMin(null);
    setYAxisMax(null);
  }, [chartIdentityKey]);

  // Sincronizar los modificadores DENTRO de chartSelection — así fluyen a
  // ``simulationApi.exportChart`` (descarga ad-hoc), a ``buildChartShareUrl``
  // (link compartible) y a ``SaveChartModal`` (persistencia en plantilla).
  useEffect(() => {
    setChartSelection((prev) => {
      const next: ChartSelection = { ...prev };
      if (customSeriesOrder && customSeriesOrder.length > 0) {
        next.customSeriesOrder = customSeriesOrder;
      } else {
        delete next.customSeriesOrder;
      }
      if (typeof yAxisMin === 'number') next.yAxisMin = yAxisMin;
      else delete next.yAxisMin;
      if (typeof yAxisMax === 'number') next.yAxisMax = yAxisMax;
      else delete next.yAxisMax;
      return next;
    });
  }, [customSeriesOrder, yAxisMin, yAxisMax]);
  /**
   * Series manuales overlay. Persisten en localStorage por "firma" de gráfica
   * (tipo+unidad+filtros+modo) — al cambiar de configuración se cargan las
   * series guardadas para esa otra configuración (o un array vacío).
   *
   * Cuando el usuario guarda el chart como plantilla, el array completo viaja
   * en el payload (incluye series inactivas).
   */
  const [syntheticSeries, setSyntheticSeries] = useState<SyntheticSeries[]>([]);
  const [showSyntheticEditor, setShowSyntheticEditor] = useState(false);
  /**
   * Flujo "crear gráfica y agregarla al reporte". Si la URL tiene el query
   * param ?addToReport=<id>, el botón Guardar cambia de etiqueta y al guardar
   * se inserta automáticamente en el reporte indicado.
   */
  const [searchParams] = useSearchParams();
  const navigateResult = useNavigate();
  const addToReportId = (() => {
    const raw = searchParams.get("addToReport");
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : null;
  })();
  const addMode = (searchParams.get("addMode") || "") as
    | ""
    | "generator"
    | "dashboard";
  const addAfterIdx = (() => {
    const raw = searchParams.get("addAfterIdx");
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  })();
  const addCatId = searchParams.get("addCatId");
  const addSubId = searchParams.get("addSubId");
  const isAddToReportFlow = addToReportId != null;
  const hasInfeasibilityDetails = Boolean(runResult?.infeasibility_diagnostics);
  const normalizedSolverStatus = (
    summary?.solver_status ?? runResult?.solver_status ?? ''
  ).toLowerCase();
  const isOptimal = normalizedSolverStatus.includes('optimal');
  const isNonOptimal = Boolean(summary || runResult) && !isOptimal;
  const failureMessage = runMeta?.error_message?.trim() || null;

  // 1. Fetch current run summary
  useEffect(() => {
    if (!currentRunId) return;
    setLoadingSummary(true);
    simulationApi
      .getResultSummary(currentRunId)
      .then(setSummary)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Error loading summary'),
      )
      .finally(() => setLoadingSummary(false));
  }, [currentRunId]);

  useEffect(() => {
    if (!currentRunId) return;
    simulationApi
      .getResult(currentRunId)
      .then(setRunResult)
      .catch((err: unknown) => {
        console.error('Error loading full result', err);
        setRunResult(null);
      });
  }, [currentRunId]);

  useEffect(() => {
    if (!currentRunId) return;
    simulationApi
      .getRun(currentRunId)
      .then(setRunMeta)
      .catch((err: unknown) => {
        console.error('Error loading run metadata', err);
        setRunMeta(null);
      });
  }, [currentRunId]);

  // 2. Fetch all summaries for comparison table
  useEffect(() => {
    setLoadingSummaries(true);
    simulationApi
      .listRuns({ scope: 'global', status_filter: 'SUCCEEDED', cantidad: 50 })
      .then(async (res) => {
        // Solo escenarios con resultados utilizables (excluye infactibles).
        const runs = (res.data || []).filter((r) => !r.is_infeasible_result);
        const summaries = await Promise.all(
          runs.map((run) => simulationApi.getResultSummary(run.id).catch(() => null)),
        );
        setAllSummaries(summaries.filter(Boolean) as ResultSummaryResponse[]);
      })
      .catch(console.error)
      .finally(() => setLoadingSummaries(false));
  }, []);

  useEffect(() => {
    if (loadingSummaries || allSummaries.length === 0) return;
    if (!currentRunId || Number.isNaN(currentRunId)) {
      setSelectedCompareColumnJobIds([]);
      compareColumnInitKeyRef.current = null;
      return;
    }
    if (compareColumnInitKeyRef.current === currentRunId) return;

    const head = allSummaries[0];
    if (!head) return;

    const hasCurrent = allSummaries.some((s) => Number(s.job_id) === Number(currentRunId));
    const firstId = Number(head.job_id);
    const defaultIds = hasCurrent ? [currentRunId] : [firstId];
    setSelectedCompareColumnJobIds(defaultIds);
    compareColumnInitKeyRef.current = currentRunId;
  }, [loadingSummaries, allSummaries, currentRunId]);

  // ── Hidratación desde share-link ──────────────────────────────────────
  // Si la URL trae query params codificados por `chartShareLink.ts`,
  // restauramos el chartSelection, modo de comparación, jobs adicionales,
  // años a graficar y placements de facet. Solo se ejecuta una vez al montar.
  // El ref `compareColumnInitKeyRef.current = currentRunId` evita que el
  // efecto siguiente sobreescriba la selección de jobs cuando lleguen los
  // summaries.
  const hydratedFromUrlRef = useRef(false);
  useEffect(() => {
    if (hydratedFromUrlRef.current) return;
    const sp = new URLSearchParams(window.location.search);
    if (!sp.get("t") && !sp.get("jobs") && !sp.get("vm")) return; // no hay share-link
    const decoded = decodeChartShareParams(sp);
    if (decoded.selection?.tipo) {
      setChartSelection(decoded.selection as ChartSelection);
    }
    if (decoded.barOrientation) {
      setChartBarOrientation(decoded.barOrientation);
    }
    if (decoded.facetPlacement) {
      setChartFacetPlacement(decoded.facetPlacement);
    }
    if (decoded.facetLegendMode) {
      setChartFacetLegendMode(decoded.facetLegendMode);
    }
    if (decoded.compareYearsToPlot && decoded.compareYearsToPlot.length > 0) {
      setCompareYearsToPlot(decoded.compareYearsToPlot);
    }
    if (decoded.compareMode && decoded.compareMode !== "off") {
      setCompareViewMode(decoded.compareMode);
    }
    if (decoded.jobIds && decoded.jobIds.length >= 2) {
      setSelectedCompareColumnJobIds(decoded.jobIds);
      // Importante: marcamos el ref para que el efecto basado en summaries
      // no resetee la selección.
      compareColumnInitKeyRef.current = currentRunId;
    }
    hydratedFromUrlRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setExecutionsTablePage(1);
  }, [currentRunId]);

  // ── Filtros por columna de la tabla comparativa ──
  const [execColumnFilters, setExecColumnFilters] = useState<{
    name: string;
    scenario: string;
    tag: string;
    status: string;
    owner: string;
    favorite: '' | 'fav' | 'no';
  }>({
    name: '',
    scenario: '',
    tag: '',
    status: '',
    owner: '',
    favorite: '',
  });
  const resetExecFilters = useCallback(() => {
    setExecColumnFilters({
      name: '',
      scenario: '',
      tag: '',
      status: '',
      owner: '',
      favorite: '',
    });
  }, []);

  // Oculta infactibles/no exitosas; filas seleccionadas se muestran siempre.
  const eligibleSummaries = useMemo(
    () =>
      allSummaries.filter(
        (s) =>
          !s.is_infeasible_result &&
          !(s.solver_status ?? '').toLowerCase().includes('infeasible') &&
          !(s.solver_status ?? '').toLowerCase().includes('fail') &&
          !(s.solver_status ?? '').toLowerCase().includes('cancel'),
      ),
    [allSummaries],
  );

  const selectedJobIdSet = useMemo(
    () => new Set(selectedCompareColumnJobIds.map(Number)),
    [selectedCompareColumnJobIds],
  );

  const filteredNonSelectedSummaries = useMemo(() => {
    const nameQ = execColumnFilters.name.trim().toLowerCase();
    const scenarioQ = execColumnFilters.scenario.trim().toLowerCase();
    const tagQ = execColumnFilters.tag.trim().toLowerCase();
    const statusQ = execColumnFilters.status.trim().toLowerCase();
    const ownerQ = execColumnFilters.owner.trim().toLowerCase();
    const favQ = execColumnFilters.favorite;
    return eligibleSummaries.filter((s) => {
      if (selectedJobIdSet.has(Number(s.job_id))) return false;
      if (nameQ) {
        const name = (s.display_name ?? s.scenario_name ?? `Job ${s.job_id}`).toLowerCase();
        if (!name.includes(nameQ)) return false;
      }
      if (scenarioQ && !(s.scenario_name ?? '').toLowerCase().includes(scenarioQ)) return false;
      if (tagQ && !(s.scenario_tag?.name ?? '').toLowerCase().includes(tagQ)) return false;
      if (statusQ && !(s.solver_status ?? '').toLowerCase().includes(statusQ)) return false;
      if (ownerQ && !(s.owner_username ?? '').toLowerCase().includes(ownerQ)) return false;
      if (favQ === 'fav' && !s.is_favorite) return false;
      if (favQ === 'no' && s.is_favorite) return false;
      return true;
    });
  }, [eligibleSummaries, selectedJobIdSet, execColumnFilters]);

  // Orden final: seleccionados arriba → favoritos → resto.
  const orderedExecutionRows = useMemo(() => {
    const selectedRows = selectedCompareColumnJobIds
      .map((jid) => allSummaries.find((s) => Number(s.job_id) === Number(jid)))
      .filter((x): x is ResultSummaryResponse => Boolean(x));
    const rest = [...filteredNonSelectedSummaries].sort((a, b) => {
      const af = a.is_favorite ? 0 : 1;
      const bf = b.is_favorite ? 0 : 1;
      if (af !== bf) return af - bf;
      return 0;
    });
    return [...selectedRows, ...rest];
  }, [selectedCompareColumnJobIds, allSummaries, filteredNonSelectedSummaries]);

  const anyExecFilterActive = Object.values(execColumnFilters).some((v) => v !== '');

  useEffect(() => {
    const maxPage = Math.max(
      1,
      Math.ceil(orderedExecutionRows.length / EXECUTIONS_TABLE_PAGE_SIZE),
    );
    setExecutionsTablePage((p) => Math.min(p, maxPage));
  }, [orderedExecutionRows.length]);

  // Al filtrar por columnas, vuelve a la página 1.
  useEffect(() => {
    setExecutionsTablePage(1);
  }, [
    execColumnFilters.name,
    execColumnFilters.scenario,
    execColumnFilters.tag,
    execColumnFilters.status,
    execColumnFilters.owner,
    execColumnFilters.favorite,
  ]);

  const toggleCompareColumnSelection = useCallback((jobId: number) => {
    const id = Number(jobId);
    setSelectedCompareColumnJobIds((prev) => {
      const normalized = prev.map(Number);
      if (normalized.includes(id)) {
        return normalized.filter((j) => j !== id);
      }
      if (normalized.length >= MAX_COMPARE_COLUMNS) {
        alert(`Máximo ${MAX_COMPARE_COLUMNS} escenarios para comparar.`);
        return prev;
      }
      return [...normalized, id];
    });
  }, []);

  const clearCompareColumnSelection = useCallback(() => {
    setSelectedCompareColumnJobIds([]);
  }, []);

  /** Jobs seleccionados para comparación (viene exclusivamente de la tabla superior). */
  const columnCompareJobIds = useMemo(
    () => selectedCompareColumnJobIds.map(Number).filter((id) => !Number.isNaN(id) && id > 0),
    [selectedCompareColumnJobIds],
  );
  const isComparing = columnCompareJobIds.length >= 2;
  const chartCompareMode: CompareMode = isComparing ? compareViewMode : 'off';

  // Lista de series disponibles para el modal de orden, según el modo
  // activo. La unión de nombres permite definir un orden coherente que
  // funcione en cualquier facet/subplot/línea-total/single.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const seriesForModal = useMemo<{ name: string; color?: string | null | undefined }[]>(() => {
    const seen = new Map<string, string | null | undefined>();
    const push = (name: string, color?: string | null) => {
      if (!seen.has(name)) seen.set(name, color);
    };
    if (chartCompareMode === 'facet' && compareFacetData) {
      for (const f of compareFacetData.facets) {
        for (const s of f.series) push(s.name, s.color);
      }
    } else if (chartCompareMode === 'by-year' && compareChartData) {
      for (const sp of compareChartData.subplots) {
        for (const s of sp.series) push(s.name, s.color);
      }
    } else if (chartCompareMode === 'line-total' && compareLineData) {
      for (const s of compareLineData.series) push(s.name, s.color);
    } else if (singleChartData) {
      for (const s of singleChartData.series) push(s.name, s.color);
    }
    return Array.from(seen.entries()).map(([name, color]) => ({ name, color }));
  }, [
    chartCompareMode,
    compareFacetData,
    compareChartData,
    compareLineData,
    singleChartData,
  ]);
  const chartJobIds = useMemo(() => {
    if (isComparing) return columnCompareJobIds;
    return [currentRunId];
  }, [isComparing, columnCompareJobIds, currentRunId]);
  const chartYearsToPlot = compareYearsToPlot;

  // Firma estable del contexto para persistir series sintéticas por gráfica.
  const syntheticSignature = useMemo(
    () =>
      syntheticSeriesSignature({
        tipo: chartSelection.tipo,
        un: chartSelection.un,
        sub_filtro: chartSelection.sub_filtro,
        loc: chartSelection.loc,
        variable: chartSelection.variable,
        agrupar_por: chartSelection.agrupar_por,
        view_mode: chartSelection.viewMode,
        compare_mode: chartCompareMode,
      }),
    [chartSelection, chartCompareMode],
  );
  // Carga desde localStorage al cambiar el contexto.
  useEffect(() => {
    setSyntheticSeries(loadSyntheticSeries(syntheticSignature));
  }, [syntheticSignature]);
  // Guarda en localStorage en cada mutación.
  useEffect(() => {
    saveSyntheticSeries(syntheticSignature, syntheticSeries);
  }, [syntheticSignature, syntheticSeries]);

  /** Al cambiar `display_name` en resúmenes, se vuelven a pedir los datos de gráficas (títulos de facetas / eje X en comparación). */
  const chartDisplayNamesSignature = useMemo(() => {
    return chartJobIds
      .map((jid) => {
        const id = Number(jid);
        const fromSummary = summary && Number(summary.job_id) === id ? summary.display_name : undefined;
        const fromList = allSummaries.find((s) => Number(s.job_id) === id)?.display_name;
        const dn = fromSummary ?? fromList;
        return `${id}:${dn ?? ''}`;
      })
      .join('|');
  }, [chartJobIds, allSummaries, summary]);

  // 3. Fetch chart data when selection or comparison changes
  useEffect(() => {
    if (!chartSelection.tipo) return;
    if (chartJobIds.length === 0) return;

    setLoadingChart(true);
    const isCompare = chartCompareMode !== 'off' && chartJobIds.length > 1;

    const esPorcentaje = chartSelection.viewMode === 'porcentaje';

    if (isCompare && chartCompareMode === 'facet') {
      const params: Record<string, string> = {
        job_ids: chartJobIds.join(','),
        tipo: chartSelection.tipo,
        un: chartSelection.un,
      };
      if (chartSelection.sub_filtro) params.sub_filtro = chartSelection.sub_filtro;
      if (chartSelection.loc) params.loc = chartSelection.loc;
      if (chartSelection.variable) params.variable = chartSelection.variable;
      if (chartSelection.agrupar_por) params.agrupar_por = chartSelection.agrupar_por;
      if (esPorcentaje) params.es_porcentaje = 'true';

      simulationApi
        .getCompareFacetData(params as Parameters<typeof simulationApi.getCompareFacetData>[0])
        .then((data: CompareChartFacetResponse) => {
          setCompareFacetData(data);
          setCompareChartData(null);
          setSingleChartData(null);
          setCompareLineData(null);
          setParetoData(null);
        })
        .catch((err: unknown) => console.error('Error loading compare-facet data', err))
        .finally(() => setLoadingChart(false));
    } else if (isCompare && chartCompareMode === 'by-year') {
      const params: Record<string, string> = {
        job_ids: chartJobIds.join(','),
        tipo: chartSelection.tipo,
        un: chartSelection.un,
        years_to_plot: chartYearsToPlot.join(','),
      };
      if (chartSelection.sub_filtro) params.sub_filtro = chartSelection.sub_filtro;
      if (chartSelection.loc) params.loc = chartSelection.loc;
      if (chartSelection.agrupar_por) params.agrupacion = chartSelection.agrupar_por;
      if (esPorcentaje) params.es_porcentaje = 'true';

      simulationApi
        .getCompareData(params as Parameters<typeof simulationApi.getCompareData>[0])
        .then((data: CompareChartResponse) => {
          setCompareChartData(data);
          setCompareFacetData(null);
          setSingleChartData(null);
          setCompareLineData(null);
          setParetoData(null);
        })
        .catch((err: unknown) => console.error('Error loading compare data', err))
        .finally(() => setLoadingChart(false));
    } else if (isCompare && chartCompareMode === 'by-year-alt') {
      const params: Record<string, string> = {
        job_ids: chartJobIds.join(','),
        tipo: chartSelection.tipo,
        un: chartSelection.un,
        years_to_plot: chartYearsToPlot.join(','),
        group_by: 'scenario',
      };
      if (chartSelection.sub_filtro) params.sub_filtro = chartSelection.sub_filtro;
      if (chartSelection.loc) params.loc = chartSelection.loc;
      if (chartSelection.agrupar_por) params.agrupacion = chartSelection.agrupar_por;
      if (esPorcentaje) params.es_porcentaje = 'true';

      simulationApi
        .getCompareData(params as Parameters<typeof simulationApi.getCompareData>[0])
        .then((data: CompareChartResponse) => {
          setCompareChartData(data);
          setCompareFacetData(null);
          setSingleChartData(null);
          setCompareLineData(null);
          setParetoData(null);
        })
        .catch((err: unknown) => console.error('Error loading compare alt data', err))
        .finally(() => setLoadingChart(false));
    } else if (isCompare && chartCompareMode === 'line-total') {
      const params: Record<string, string> = {
        job_ids: chartJobIds.join(','),
        tipo: chartSelection.tipo,
        un: chartSelection.un,
      };
      if (chartSelection.sub_filtro) params.sub_filtro = chartSelection.sub_filtro;
      if (chartSelection.loc) params.loc = chartSelection.loc;

      simulationApi
        .getCompareLineData(params as Parameters<typeof simulationApi.getCompareLineData>[0])
        .then((data: ChartDataResponse) => {
          setCompareLineData(data);
          setCompareChartData(null);
          setCompareFacetData(null);
          setSingleChartData(null);
          setParetoData(null);
        })
        .catch((err: unknown) => console.error('Error loading compare-line data', err))
        .finally(() => setLoadingChart(false));
    } else {
      const params: Record<string, string> = {
        tipo: chartSelection.tipo,
        un: chartSelection.un,
      };
      if (chartSelection.sub_filtro) params.sub_filtro = chartSelection.sub_filtro;
      if (chartSelection.loc) params.loc = chartSelection.loc;
      if (chartSelection.variable) params.variable = chartSelection.variable;
      if (chartSelection.agrupar_por) params.agrupar_por = chartSelection.agrupar_por;
      if (esPorcentaje) params.es_porcentaje = 'true';

      if (chartSelection.viewMode === 'pareto') {
        const paretoParams: Record<string, string> = {
          tipo: chartSelection.tipo,
          un: chartSelection.un,
        };
        if (chartSelection.sub_filtro) paretoParams.sub_filtro = chartSelection.sub_filtro;
        if (chartSelection.loc) paretoParams.loc = chartSelection.loc;

        simulationApi
          .getParetoData(
            currentRunId,
            paretoParams as Parameters<typeof simulationApi.getParetoData>[1],
          )
          .then((data: ParetoChartResponse) => {
            setParetoData(data);
            setSingleChartData(null);
            setCompareChartData(null);
            setCompareFacetData(null);
            setCompareLineData(null);
          })
          .catch((err: unknown) => console.error('Error loading pareto data', err))
          .finally(() => setLoadingChart(false));
      } else {
        simulationApi
          .getChartData(
            currentRunId,
            params as Parameters<typeof simulationApi.getChartData>[1],
          )
          .then((data: ChartDataResponse) => {
            setSingleChartData(data);
            setCompareChartData(null);
            setCompareFacetData(null);
            setCompareLineData(null);
            setParetoData(null);
          })
          .catch((err: unknown) => console.error('Error loading chart data', err))
          .finally(() => setLoadingChart(false));
      }
    }
  }, [
    currentRunId,
    chartSelection,
    chartCompareMode,
    chartJobIds,
    chartYearsToPlot,
    chartDisplayNamesSignature,
  ]);

  // Cerrar dropdown al hacer clic fuera
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setShowExportMenu(false);
      }
    };
    if (showExportMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showExportMenu]);

  const handleExportSvg = useCallback(async () => {
    setShowExportMenu(false);
    setExportingType('svg');
    try {
      const response = await simulationApi.exportAllCharts(currentRunId, chartSelection.un);
      const blob = new Blob([response.data], {
        type: 'application/zip',
      });
      const disposition = response.headers['content-disposition'] || '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match?.[1] || `Graficas_${currentRunId}_${chartSelection.un}.zip`;
      downloadBlob(blob, filename);
    } catch (err) {
      console.error('Error exporting charts', err);
      alert('Error al generar el archivo. Intenta de nuevo.');
    } finally {
      setExportingType(null);
    }
  }, [currentRunId, chartSelection.un]);

  const handleExportCsvZip = useCallback(async () => {
    setShowExportMenu(false);
    setExportingType('csvzip');
    try {
      const { blob, filename } = await simulationApi.exportResultsCsvZip(currentRunId);
      downloadBlob(blob, filename);
    } catch (err) {
      console.error('Error exporting CSV bundle', err);
      alert('Error al generar el ZIP de CSVs. Intenta de nuevo.');
    } finally {
      setExportingType(null);
    }
  }, [currentRunId]);

  const handleExportExcel = useCallback(async () => {
    setShowExportMenu(false);
    setExportingType('excel');
    try {
      const { blob, filename } = await simulationApi.exportRawData(currentRunId);
      downloadBlob(blob, filename);
    } catch (err: unknown) {
      console.error('Error exporting raw data', err);
      let msg = 'Error descargando los datos crudos.';
      // ApiError normalizado (el interceptor convierte respuestas blob a mensaje genérico)
      if (err && typeof err === 'object' && 'message' in err && typeof (err as { message: string }).message === 'string') {
        msg = (err as { message: string }).message;
      }
      // Si el backend devolvió JSON en un Blob (responseType: blob), intentar extraer detail
      if (err && typeof err === 'object' && 'details' in err) {
        const details = (err as { details?: { response?: unknown } }).details;
        const resp = details?.response;
        if (resp instanceof Blob && resp.type.includes('json')) {
          try {
            const text = await resp.text();
            const parsed = JSON.parse(text);
            if (typeof parsed.detail === 'string') msg = parsed.detail;
          } catch {
            /* ignored */
          }
        }
      }
      alert(msg);
    } finally {
      setExportingType(null);
    }
  }, [currentRunId]);

  const handleFavoriteToggled = useCallback((jobId: number, next: boolean) => {
    setAllSummaries((prev) =>
      prev.map((s) =>
        Number(s.job_id) === Number(jobId) ? { ...s, is_favorite: next } : s,
      ),
    );
    setSummary((prev) =>
      prev && Number(prev.job_id) === Number(jobId)
        ? { ...prev, is_favorite: next }
        : prev,
    );
  }, []);

  const handleDisplayNameSaved = useCallback((jobId: number, displayName: string | null) => {
    const norm = displayName?.trim() || null;
    setAllSummaries((prev) =>
      prev.map((s) =>
        Number(s.job_id) === Number(jobId) ? { ...s, display_name: norm } : s,
      ),
    );
    setSummary((prev) =>
      prev && Number(prev.job_id) === Number(jobId) ? { ...prev, display_name: norm } : prev,
    );
  }, []);

  if (error) {
    return (
      <div className="p-8 text-center">
        <h2 className="text-xl font-bold text-red-400 mb-4">Error</h2>
        <p className="text-slate-400">{error}</p>
        <Link
          to="/app/results"
          className="text-blue-400 hover:underline mt-4 inline-block"
        >
          Volver a Resultados
        </Link>
      </div>
    );
  }

  const selectedCardsGridClass =
    scenarioCardsViewMode === 'list'
      ? 'flex flex-col gap-3'
      : 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4';

  const executionsTotalPages = Math.max(
    1,
    Math.ceil(orderedExecutionRows.length / EXECUTIONS_TABLE_PAGE_SIZE),
  );
  const executionsPageSafe = Math.min(executionsTablePage, executionsTotalPages);
  const executionsSliceStart = (executionsPageSafe - 1) * EXECUTIONS_TABLE_PAGE_SIZE;
  const paginatedSummaries = orderedExecutionRows.slice(
    executionsSliceStart,
    executionsSliceStart + EXECUTIONS_TABLE_PAGE_SIZE,
  );
  const executionsRangeEnd = Math.min(
    executionsSliceStart + EXECUTIONS_TABLE_PAGE_SIZE,
    orderedExecutionRows.length,
  );

  /** Evita duplicar la misma tarjeta KPI arriba y en "KPIs seleccionados" cuando ya hay selección en la comparativa. */
  const showHeroKpiCard =
    Boolean(summary) &&
    (loadingSummaries || allSummaries.length === 0 || selectedCompareColumnJobIds.length === 0);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-6 space-y-6 font-sans">
      {/* ─── HEADER ─── */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Resultados de simulación
          </h1>
          {summary?.display_name?.trim() ? (
            <p className="m-0 mt-2 text-lg font-semibold text-cyan-200/95">
              {summary.display_name.trim()}
            </p>
          ) : summary?.scenario_name?.trim() ? (
            <p className="m-0 mt-2 text-lg font-semibold text-slate-200">
              {summary.scenario_name.trim()}
            </p>
          ) : null}
          <p className="text-[11px] text-slate-600 mt-1 font-mono">
            ID de ejecución · {currentRunId}
          </p>
        </div>
        <div className="flex gap-3 items-center flex-wrap">
          {isOptimal ? (
            <div ref={exportMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setShowExportMenu((v) => !v)}
                disabled={exportingType !== null}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/50 px-4 py-2 text-sm font-medium text-slate-200 backdrop-blur-sm hover:border-slate-600 hover:bg-slate-900 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {exportingType ? (
                  <>
                    <div className="w-4 h-4 rounded-full border-2 border-current/30 border-t-current animate-spin" />
                    {exportingType === 'svg'
                      ? 'Generando ZIP…'
                      : exportingType === 'csvzip'
                        ? 'Generando CSVs…'
                        : 'Generando Excel…'}
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    Exportar
                    <svg className={`w-4 h-4 shrink-0 transition-transform ${showExportMenu ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </>
                )}
              </button>
              {showExportMenu && (
                <div className="absolute right-0 top-full mt-2 flex flex-col gap-1 min-w-[240px] rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-xl backdrop-blur-md z-50">
                  <button
                    type="button"
                    onClick={handleExportSvg}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-slate-200 hover:bg-slate-800/80"
                  >
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-emerald-500/20 bg-emerald-500/10 text-emerald-400">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                    </span>
                    Gráficos (SVG / ZIP)
                  </button>
                  <button
                    type="button"
                    onClick={handleExportExcel}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-slate-200 hover:bg-slate-800/80"
                  >
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-cyan-500/20 bg-cyan-500/10 text-cyan-400">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </span>
                    Datos crudos (Excel)
                  </button>
                  <button
                    type="button"
                    onClick={handleExportCsvZip}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-slate-200 hover:bg-slate-800/80"
                  >
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-amber-500/20 bg-amber-500/10 text-amber-400">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4h6l2 3h8a2 2 0 012 2v9a2 2 0 01-2 2H4a2 2 0 01-2-2V6a2 2 0 012-2z" />
                      </svg>
                    </span>
                    Resultados (CSV OSeMOSYS · ZIP)
                  </button>
                </div>
              )}
            </div>
          ) : null}

          <Link to="/app/results">
            <Button
              variant="ghost"
              className="text-slate-300 hover:text-white hover:bg-slate-800/80 border border-slate-800 text-sm rounded-lg"
            >
              ← Volver a tabla
            </Button>
          </Link>
        </div>
      </div>

      {/* ─── RESUMEN KPI (solo si no está ya cubierto por la zona de comparativa seleccionada) ─── */}
      {loadingSummary ? (
        <div className="animate-pulse rounded-xl border border-slate-800 bg-[#0f172a]/80 h-44" />
      ) : summary && showHeroKpiCard ? (
        <ScenarioCard summary={summary} isCurrent />
      ) : null}

      {isNonOptimal ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-6 flex flex-wrap items-center justify-between gap-4">
          <div className="grid gap-2 text-sm text-rose-100/90 max-w-3xl">
            <strong className="text-rose-50">
              {hasInfeasibilityDetails
                ? 'Esta simulación reporta infactibilidad o un estado no óptimo.'
                : 'Esta simulación no terminó con una solución óptima.'}
            </strong>
            <span className="text-slate-400">
              Estado del solver:{' '}
              <span className="font-mono font-semibold text-slate-200 uppercase">
                {summary?.solver_name?.toUpperCase() ?? runResult?.solver_name?.toUpperCase() ?? 'SOLVER'}{' '}
                {(summary?.solver_status ?? runResult?.solver_status ?? 'unknown').toUpperCase()}
              </span>
            </span>
            {failureMessage ? <span className="text-slate-400">Detalle: {failureMessage}</span> : null}
            {!hasInfeasibilityDetails ? (
              <span className="text-slate-500 text-xs">
                No se pudieron recopilar diagnósticos detallados. Esto suele pasar cuando el worker se
                termina de forma abrupta antes de persistir la infactibilidad.
              </span>
            ) : (
              <span className="text-slate-500 text-xs">
                El análisis detallado (IIS + mapeo a parámetros) se ejecuta bajo demanda;
                usa el botón a la derecha para lanzarlo o ver su estado.
              </span>
            )}
          </div>
          {hasInfeasibilityDetails && runResult?.job_id ? (
            (() => {
              const solver = (runResult.solver_name ?? '').toLowerCase();
              const diag = runResult.infeasibility_diagnostics ?? null;
              // Retrocompat: jobs antiguos no tienen `diagnostic_status` pero sí
              // el reporte enriquecido; los tratamos como SUCCEEDED.
              const hasEnriched = Boolean(
                diag?.iis ||
                  diag?.overview ||
                  (diag?.top_suspects?.length ?? 0) > 0 ||
                  (diag?.constraint_analyses?.length ?? 0) > 0,
              );
              const diagStatus =
                diag?.diagnostic_status ?? (hasEnriched ? 'SUCCEEDED' : 'NONE');
              if (solver !== 'highs') {
                return (
                  <span className="text-xs text-slate-400 italic shrink-0 max-w-xs">
                    Para correr el diagnóstico de infactibilidad (IIS + mapeo a
                    parámetros) es necesario volver a lanzar la simulación con HiGHS.
                  </span>
                );
              }
              if (diagStatus === 'SUCCEEDED') {
                return (
                  <Link
                    to={paths.infeasibilityReport(runResult.job_id)}
                    className="bg-rose-600 hover:bg-rose-500 text-white border border-rose-500/50 rounded-lg shrink-0 px-4 py-2 font-semibold no-underline"
                  >
                    ⚠ Ver reporte de infactibilidad
                  </Link>
                );
              }
              if (diagStatus === 'QUEUED' || diagStatus === 'RUNNING') {
                return (
                  <Link
                    to={paths.infeasibilityReport(runResult.job_id)}
                    className="bg-amber-600/20 hover:bg-amber-600/30 text-amber-200 border border-amber-500/50 rounded-lg shrink-0 px-4 py-2 font-semibold no-underline"
                  >
                    {diagStatus === 'QUEUED'
                      ? 'Diagnóstico en cola…'
                      : 'Diagnosticando…'}
                  </Link>
                );
              }
              // NONE / FAILED → link a la página donde se lanza
              return (
                <Link
                  to={paths.infeasibilityReport(runResult.job_id)}
                  className="bg-rose-600 hover:bg-rose-500 text-white border border-rose-500/50 rounded-lg shrink-0 px-4 py-2 font-semibold no-underline"
                >
                  {diagStatus === 'FAILED'
                    ? '⚠ Reintentar diagnóstico'
                    : '⚠ Correr diagnóstico de infactibilidad'}
                </Link>
              );
            })()
          ) : null}
        </div>
      ) : null}

      {/* ─── COMPARATIVA ─── */}
      {!loadingSummaries && allSummaries.length > 0 && (
        <section className="rounded-xl border border-slate-800 bg-slate-900/30 backdrop-blur-sm overflow-hidden">
          <div className="p-6 border-b border-slate-800 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-1">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                Comparativa de escenarios
              </h2>
              <p className="text-sm text-slate-500 m-0 max-w-2xl">
                Selecciona hasta {MAX_COMPARE_COLUMNS} ejecuciones. Con dos o más, los gráficos las comparan según el modo de vista elegido (facet / por años / líneas totales).
              </p>
            </div>
            {selectedCompareColumnJobIds.length > 0 ? (
              <Button
                type="button"
                variant="ghost"
                className="text-slate-400 hover:text-white border border-slate-800 text-xs shrink-0 rounded-lg"
                onClick={clearCompareColumnSelection}
              >
                Limpiar selección
              </Button>
            ) : null}
          </div>


          {selectedCompareColumnJobIds.length > 0 ? (
            <details className="border-b border-slate-800 bg-slate-950/30 group">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-4 text-sm font-medium text-slate-400 transition-colors hover:text-slate-200 [&::-webkit-details-marker]:hidden">
                <span className="flex items-center gap-2">
                  <svg
                    className="h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-90"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                  <span className="text-xs font-semibold uppercase tracking-[0.08em]">
                    KPIs seleccionados ({selectedCompareColumnJobIds.length})
                  </span>
                </span>
                <span className="shrink-0 text-xs text-slate-600">
                  Click para ver las tarjetas KPI
                </span>
              </summary>
              <div className="border-t border-slate-800/80">
                <div className="p-6 pb-0 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-end">
                  <div
                    className="inline-flex shrink-0 rounded-lg border border-slate-700/80 bg-slate-900/70 p-0.5"
                    role="group"
                    aria-label="Modo de vista de tarjetas"
                  >
                    <button
                      type="button"
                      onClick={() => setScenarioCardsViewMode('grid')}
                      className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-xs font-semibold transition-colors ${
                        scenarioCardsViewMode === 'grid'
                          ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/20'
                          : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      <LayoutGrid className="h-4 w-4" aria-hidden />
                      Cuadrícula
                    </button>
                    <button
                      type="button"
                      onClick={() => setScenarioCardsViewMode('list')}
                      className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-xs font-semibold transition-colors ${
                        scenarioCardsViewMode === 'list'
                          ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/20'
                          : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      <List className="h-4 w-4" aria-hidden />
                      Lista
                    </button>
                  </div>
                </div>
                <div className={`p-6 pt-4 ${selectedCardsGridClass}`}>
                  {selectedCompareColumnJobIds.map((jobId) => {
                    const colSummary = allSummaries.find((x) => Number(x.job_id) === Number(jobId));
                    if (!colSummary) return null;
                    return (
                      <ScenarioCard
                        key={jobId}
                        summary={colSummary}
                        isCurrent={Number(colSummary.job_id) === Number(currentRunId)}
                      />
                    );
                  })}
                </div>
              </div>
            </details>
          ) : null}

          <details open className="border-t border-slate-800">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-4 text-sm font-medium text-slate-400 transition-colors hover:text-slate-200 [&::-webkit-details-marker]:hidden">
              <span>Tabla de ejecuciones</span>
              <span className="shrink-0 text-xs text-slate-600">
                Solo exitosas · Seleccionados + favoritos arriba ·{' '}
                {orderedExecutionRows.length} visibles · {EXECUTIONS_TABLE_PAGE_SIZE} por página
                {anyExecFilterActive ? ' · filtros activos' : ''}
              </span>
            </summary>
            <div className="overflow-x-auto border-t border-slate-800/80 px-0 pb-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/50 text-left">
                    <th className="w-10 p-4 text-center">
                      <span className="sr-only">Comparar</span>
                    </th>
                    <th className="w-10 p-4 text-center text-xs font-semibold uppercase tracking-wider text-slate-500">
                      ★
                    </th>
                    <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-500 min-w-[160px]">
                      Nombre del resultado
                    </th>
                    <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Escenario
                    </th>
                    <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Etiqueta
                    </th>
                    <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Dueño
                    </th>
                    <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Estado
                    </th>
                    <th className="p-4 text-right text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Objective (USD)
                    </th>
                    <th className="p-4 text-right text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Cobertura %
                    </th>
                    <th className="p-4 text-right text-xs font-semibold uppercase tracking-wider text-slate-500">
                      CO₂ (Mt)
                    </th>
                  </tr>
                  <tr className="border-b border-slate-800/80 bg-slate-950/30">
                    <th className="p-2" />
                    <th className="p-2">
                      <select
                        aria-label="Filtrar favoritos"
                        value={execColumnFilters.favorite}
                        onChange={(e) =>
                          setExecColumnFilters((p) => ({
                            ...p,
                            favorite: e.target.value as '' | 'fav' | 'no',
                          }))
                        }
                        className="w-full rounded-md border border-slate-700 bg-slate-950/50 px-1.5 py-1 text-[11px] text-slate-200"
                      >
                        <option value="">Todos</option>
                        <option value="fav">★ Favoritos</option>
                        <option value="no">Sin favorito</option>
                      </select>
                    </th>
                    <th className="p-2">
                      <input
                        type="text"
                        value={execColumnFilters.name}
                        onChange={(e) =>
                          setExecColumnFilters((p) => ({
                            ...p,
                            name: e.target.value,
                          }))
                        }
                        placeholder="Filtrar…"
                        className="w-full rounded-md border border-slate-700 bg-slate-950/50 px-2 py-1 text-[11px] text-slate-200"
                      />
                    </th>
                    <th className="p-2">
                      <input
                        type="text"
                        value={execColumnFilters.scenario}
                        onChange={(e) =>
                          setExecColumnFilters((p) => ({
                            ...p,
                            scenario: e.target.value,
                          }))
                        }
                        placeholder="Filtrar…"
                        className="w-full rounded-md border border-slate-700 bg-slate-950/50 px-2 py-1 text-[11px] text-slate-200"
                      />
                    </th>
                    <th className="p-2">
                      <input
                        type="text"
                        value={execColumnFilters.tag}
                        onChange={(e) =>
                          setExecColumnFilters((p) => ({
                            ...p,
                            tag: e.target.value,
                          }))
                        }
                        placeholder="Filtrar…"
                        className="w-full rounded-md border border-slate-700 bg-slate-950/50 px-2 py-1 text-[11px] text-slate-200"
                      />
                    </th>
                    <th className="p-2">
                      <input
                        type="text"
                        value={execColumnFilters.owner}
                        onChange={(e) =>
                          setExecColumnFilters((p) => ({
                            ...p,
                            owner: e.target.value,
                          }))
                        }
                        placeholder="Filtrar…"
                        className="w-full rounded-md border border-slate-700 bg-slate-950/50 px-2 py-1 text-[11px] text-slate-200"
                      />
                    </th>
                    <th className="p-2">
                      <input
                        type="text"
                        value={execColumnFilters.status}
                        onChange={(e) =>
                          setExecColumnFilters((p) => ({
                            ...p,
                            status: e.target.value,
                          }))
                        }
                        placeholder="Filtrar…"
                        className="w-full rounded-md border border-slate-700 bg-slate-950/50 px-2 py-1 text-[11px] text-slate-200"
                      />
                    </th>
                    <th className="p-2 text-right">
                      {anyExecFilterActive ? (
                        <button
                          type="button"
                          onClick={resetExecFilters}
                          className="rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800"
                        >
                          Limpiar
                        </button>
                      ) : null}
                    </th>
                    <th className="p-2" />
                    <th className="p-2" />
                  </tr>
                </thead>
                <tbody>
                  {paginatedSummaries.map((s) => {
                    const isCurrent = Number(s.job_id) === Number(currentRunId);
                    const isColSelected = selectedCompareColumnJobIds.map(Number).includes(Number(s.job_id));
                    const st = getSolverStatusPresentation(s.solver_status);
                    const rowLabel =
                      s.display_name?.trim() || s.scenario_name?.trim() || `Job ${s.job_id}`;
                    return (
                      <tr
                        key={s.job_id}
                        className={`border-b border-slate-800/80 transition-colors ${
                          isColSelected
                            ? 'bg-cyan-500/[0.05]'
                            : isCurrent
                              ? 'bg-emerald-500/[0.04]'
                              : 'hover:bg-slate-900/50'
                        }`}
                      >
                        <td className="p-4 text-center align-middle">
                          <input
                            type="checkbox"
                            checked={isColSelected}
                            onChange={() => toggleCompareColumnSelection(Number(s.job_id))}
                            aria-label={`Incluir ${rowLabel} en vista columnas`}
                            className="h-4 w-4 cursor-pointer rounded border-slate-600 bg-slate-950 text-emerald-500 focus:ring-emerald-500/40"
                          />
                        </td>
                        <td className="p-4 text-center align-middle">
                          <FavoriteStarButton
                            jobId={Number(s.job_id)}
                            isFavorite={Boolean(s.is_favorite)}
                            onToggled={(next) => handleFavoriteToggled(Number(s.job_id), next)}
                            size={16}
                          />
                        </td>
                        <td className="p-4 align-top min-w-[160px] max-w-[280px]">
                          <RunDisplayNameEditor
                            jobId={s.job_id}
                            value={s.display_name ?? null}
                            onSaved={handleDisplayNameSaved}
                            compact
                          />
                        </td>
                        <td className="p-4 align-middle">
                          <Link
                            to={`/app/results/${s.job_id}`}
                            className={`inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1 font-medium hover:text-emerald-400 hover:underline ${
                              isCurrent ? 'text-emerald-400' : 'text-slate-200'
                            }`}
                          >
                            <span className="min-w-0 break-words">
                              {s.scenario_name?.trim() || '—'}
                            </span>
                            {isCurrent ? (
                              <span className="shrink-0 rounded-md bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-400">
                                Actual
                              </span>
                            ) : null}
                            {isColSelected && !isCurrent ? (
                              <span className="shrink-0 rounded-md bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-cyan-300">
                                Seleccionado
                              </span>
                            ) : null}
                          </Link>
                        </td>
                        <td className="p-4 align-middle">
                          {(() => {
                            const tags =
                              s.scenario_tags && s.scenario_tags.length > 0
                                ? s.scenario_tags
                                : s.scenario_tag
                                ? [s.scenario_tag]
                                : [];
                            if (tags.length === 0) {
                              return <span className="text-slate-600">—</span>;
                            }
                            return (
                              <div className="flex flex-col gap-1">
                                {tags.map((t) => (
                                  <ScenarioTagChip key={t.id} tag={t} size="sm" />
                                ))}
                              </div>
                            );
                          })()}
                        </td>
                        <td className="p-4 align-middle text-slate-300">
                          {s.owner_username ?? '—'}
                        </td>
                        <td className="p-4">
                          <span className={st.badgeClass}>{st.label}</span>
                        </td>
                        <td className="p-4 text-right font-mono text-slate-200 tabular-nums">
                          {formatCompactNumber(s.objective_value, 2)}
                        </td>
                        <td className="p-4 text-right font-mono text-slate-200 tabular-nums">
                          {formatPercent(s.coverage_ratio, 2)}
                        </td>
                        <td className="p-4 text-right font-mono text-slate-200 tabular-nums">
                          {formatCompactNumber(s.total_co2, 2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800/80 px-6 py-3">
                <p className="m-0 text-xs text-slate-500">
                  {orderedExecutionRows.length === 0
                    ? 'Sin filas'
                    : `${executionsSliceStart + 1}–${executionsRangeEnd} de ${orderedExecutionRows.length}`}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={executionsPageSafe <= 1}
                    onClick={() => setExecutionsTablePage((p) => Math.max(1, p - 1))}
                    className="text-xs rounded-lg border border-slate-800 px-3 py-1.5 disabled:opacity-40"
                  >
                    Anterior
                  </Button>
                  <span className="text-xs tabular-nums text-slate-400">
                    Página {executionsPageSafe} / {executionsTotalPages}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={executionsPageSafe >= executionsTotalPages}
                    onClick={() =>
                      setExecutionsTablePage((p) => Math.min(executionsTotalPages, p + 1))
                    }
                    className="text-xs rounded-lg border border-slate-800 px-3 py-1.5 disabled:opacity-40"
                  >
                    Siguiente
                  </Button>
                </div>
              </div>
            </div>
          </details>

          {/* Modo de comparación — aparece debajo de la tabla solo cuando hay ≥2 seleccionados. */}
          {columnCompareJobIds.length >= 2 ? (
            <div className="p-6 border-t border-slate-800">
              <ScenarioComparer
                selectedCount={columnCompareJobIds.length}
                selectedYears={compareYearsToPlot}
                compareViewMode={compareViewMode}
                onChangeViewMode={setCompareViewMode}
                onChangeYears={setCompareYearsToPlot}
              />
            </div>
          ) : null}
        </section>
      )}

      {isOptimal ? (
        <>
          <div className="flex items-center justify-end gap-2">
            {isAddToReportFlow ? (
              <span className="rounded-full border border-cyan-500/40 bg-cyan-500/10 px-3 py-1 text-[11px] font-semibold text-cyan-200">
                Agregando al reporte #{addToReportId}
              </span>
            ) : null}
            {chartCompareMode === 'off' && currentRunId ? (() => {
              const catalogItem = chartCatalog.find((c) => c.id === chartSelection.tipo);
              const baseFilters = catalogItem?.data_explorer_filters ?? null;
              // Variables: prioriza la variable explícita seleccionada por el
              // usuario sobre la default del chart, para que el Data Explorer
              // muestre exactamente lo que el chart está mostrando.
              const explorerVariableNames =
                chartSelection.variable && chartSelection.variable !== 'auto'
                  ? [chartSelection.variable]
                  : baseFilters?.variable_names && baseFilters.variable_names.length > 0
                    ? baseFilters.variable_names
                    : catalogItem
                      ? [catalogItem.variable_default]
                      : undefined;
              const filters: Parameters<typeof paths.resultsDataExplorer>[1] = {};
              if (explorerVariableNames && explorerVariableNames.length > 0) {
                filters.variable_names = explorerVariableNames;
              }
              if (baseFilters?.technology_prefixes && baseFilters.technology_prefixes.length > 0) {
                filters.technology_prefixes = baseFilters.technology_prefixes;
              }
              if (baseFilters?.fuel_prefixes && baseFilters.fuel_prefixes.length > 0) {
                filters.fuel_prefixes = baseFilters.fuel_prefixes;
              }
              if (baseFilters?.fuel_names && baseFilters.fuel_names.length > 0) {
                filters.fuel_names = baseFilters.fuel_names;
              }
              if (baseFilters?.emission_names && baseFilters.emission_names.length > 0) {
                filters.emission_names = baseFilters.emission_names;
              }
              return (
                <Link
                  to={paths.resultsDataExplorer(currentRunId, filters)}
                  className="inline-flex items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-300 hover:bg-sky-500/20"
                  title="Abre el Data Explorer mostrando las filas que se grafican (incluyendo las que se suman bajo cada agrupación)"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-6h13v6M9 11V5h13v6M3 5h2v14H3z" />
                  </svg>
                  Ver Datos de Resultados
                </Link>
              );
            })() : null}
            <button
              type="button"
              onClick={async () => {
                const url = buildChartShareUrl({
                  jobIds: chartJobIds,
                  selection: chartSelection,
                  barOrientation: chartBarOrientation,
                  compareMode: chartCompareMode === "off"
                    ? undefined
                    : chartCompareMode,
                  compareYearsToPlot:
                    chartCompareMode === "by-year"
                      ? compareYearsToPlot
                      : undefined,
                  facetPlacement:
                    chartCompareMode === "facet" ? chartFacetPlacement : undefined,
                  facetLegendMode:
                    chartCompareMode === "facet" ? chartFacetLegendMode : undefined,
                });
                const ok = await copyToClipboard(url);
                setShareLinkToast(
                  ok
                    ? "Enlace copiado al portapapeles."
                    : `No se pudo copiar. URL: ${url}`,
                );
                window.setTimeout(() => setShareLinkToast(null), 3500);
              }}
              className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20"
              title="Copia un enlace que reproduce esta gráfica con todos sus filtros, escenarios y opciones."
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 015.656 0l1.414 1.414a4 4 0 010 5.657l-2.829 2.828a4 4 0 01-5.657 0M10.172 13.828a4 4 0 01-5.656 0l-1.414-1.414a4 4 0 010-5.657l2.829-2.828a4 4 0 015.657 0" />
              </svg>
              Copiar enlace
            </button>
            <button
              type="button"
              onClick={() => setShowSaveChartModal(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/20"
              title={
                isAddToReportFlow
                  ? "Guardar esta gráfica y agregarla automáticamente al reporte"
                  : "Guardar esta gráfica como plantilla reutilizable en reportes"
              }
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
              </svg>
              {isAddToReportFlow ? "Guardar gráfica y agregar al reporte" : "Guardar gráfica"}
            </button>
          </div>

          {/* ── Modificadores de gráfica ──
              Visibles en single y en TODOS los modos de comparación
              (facet, by-year, line-total). Pareto y tabla no aplican. */}
          {chartSelection.viewMode !== 'pareto' && chartSelection.viewMode !== 'table' ? (
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800/60 bg-slate-900/30 px-4 py-2.5 text-xs">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Modificadores
              </span>
              <button
                type="button"
                onClick={() => setSeriesOrderOpen(true)}
                disabled={seriesForModal.length < 2}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                title="Cambia el orden de las series (afecta el stack y la leyenda)"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12" />
                </svg>
                Orden de series
                {customSeriesOrder ? (
                  <span className="rounded-full bg-cyan-500/20 px-1.5 py-0.5 text-[9px] text-cyan-300">
                    custom
                  </span>
                ) : null}
              </button>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] text-slate-500">Eje Y:</span>
                <input
                  type="number"
                  value={yAxisMin ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    setYAxisMin(raw === '' ? null : Number(raw));
                  }}
                  placeholder="auto"
                  className="w-24 rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100 placeholder:text-slate-600"
                  title="Valor mínimo del eje Y (vacío = auto, default 0)"
                />
                <span className="text-slate-600">–</span>
                <input
                  type="number"
                  value={yAxisMax ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    setYAxisMax(raw === '' ? null : Number(raw));
                  }}
                  placeholder="auto"
                  className="w-24 rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100 placeholder:text-slate-600"
                  title="Valor máximo del eje Y (vacío = auto)"
                />
                {(yAxisMin != null || yAxisMax != null) ? (
                  <button
                    type="button"
                    onClick={() => {
                      setYAxisMin(null);
                      setYAxisMax(null);
                    }}
                    className="text-[11px] text-cyan-400 hover:text-cyan-300 underline ml-1"
                  >
                    limpiar
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="rounded-xl border border-slate-800 bg-slate-900/30 backdrop-blur-sm p-6 relative">
            {loadingChart && (
              <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-slate-950/70 backdrop-blur-sm">
                <div className="flex flex-col items-center gap-3">
                  <div className="h-8 w-8 rounded-full border-2 border-slate-700 border-t-emerald-500 animate-spin" />
                  <span className="text-sm font-medium text-slate-400">Renderizando gráfico…</span>
                </div>
              </div>
            )}

            {chartCompareMode === 'facet' && chartJobIds.length > 1 && compareFacetData ? (
              <CompareChartFacet
                data={reorderFacetSeries(compareFacetData, customSeriesOrder)}
                barOrientation={chartBarOrientation}
                facetPlacement={chartFacetPlacement}
                legendMode={chartFacetLegendMode}
                viewMode={chartSelection.viewMode === 'line' ? 'line' : 'column'}
                serverFacetExport={{ jobIds: chartJobIds, selection: chartSelection }}
                yAxisMin={yAxisMin}
                yAxisMax={yAxisMax}
              />
            ) : chartCompareMode === 'by-year' && chartJobIds.length > 1 && compareChartData ? (
              <CompareChart
                data={reorderByYearSeries(compareChartData, customSeriesOrder)}
                barOrientation={chartBarOrientation}
                yAxisMin={yAxisMin}
                yAxisMax={yAxisMax}
              />
            ) : chartCompareMode === 'by-year-alt' && chartJobIds.length > 1 && compareChartData ? (
              <CompareChart
                data={reorderByYearSeries(compareChartData, customSeriesOrder)}
                barOrientation={chartBarOrientation}
                yAxisMin={yAxisMin}
                yAxisMax={yAxisMax}
                sharedYAxis={true}
              />
            ) : chartCompareMode === 'line-total' && chartJobIds.length > 1 && compareLineData ? (
              <LineChart
                data={reorderChartSeries(compareLineData, customSeriesOrder)}
                syntheticSeries={syntheticSeries.filter((s) => s.active !== false)}
                yAxisMin={yAxisMin}
                yAxisMax={yAxisMax}
              />
            ) : chartSelection.viewMode === 'pareto' && paretoData ? (
              <ParetoChart
                data={paretoData}
                serverExport={{ jobId: currentRunId, selection: chartSelection }}
              />
            ) : chartSelection.viewMode === 'table' && singleChartData ? (
              <ChartDataTable
                data={singleChartData}
                periodYears={chartSelection.tablePeriodYears ?? null}
                cumulative={Boolean(chartSelection.tableCumulative)}
                serverExport={{ jobId: currentRunId, selection: chartSelection }}
              />
            ) : singleChartData ? (
              chartSelection.viewMode === 'line'
                ? (
                    <LineChart
                      data={reorderChartSeries(singleChartData, customSeriesOrder)}
                      serverExport={{ jobId: currentRunId, selection: chartSelection }}
                      syntheticSeries={syntheticSeries.filter((s) => s.active !== false)}
                      yAxisMin={yAxisMin}
                      yAxisMax={yAxisMax}
                    />
                  )
                : (
                    <HighchartsChart
                      data={reorderChartSeries(singleChartData, customSeriesOrder)}
                      barOrientation={chartBarOrientation}
                      serverExport={{ jobId: currentRunId, selection: chartSelection }}
                      yAxisMin={yAxisMin}
                      yAxisMax={yAxisMax}
                    />
                  )
            ) : !loadingChart ? (
              <div className="flex h-[400px] flex-col items-center justify-center px-4 text-center text-slate-500">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-slate-800 bg-slate-900/50">
                  <svg className="h-8 w-8 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <h3 className="mb-1 text-base font-medium text-slate-400">Sin datos para mostrar</h3>
                <p className="text-sm text-slate-600">Elige un tipo de gráfico en el panel inferior.</p>
              </div>
            ) : null}
          </div>

          <ChartSelector
            value={chartSelection}
            onChange={setChartSelection}
            hideGroupBy={chartCompareMode === 'line-total'}
            barOrientation={chartBarOrientation}
            onChangeBarOrientation={setChartBarOrientation}
          />

          {/* Series manuales overlay: solo aplican en gráficas de línea. */}
          {(chartSelection.viewMode === 'line' ||
            chartCompareMode === 'line-total') ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900/30 backdrop-blur-sm p-4 flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="m-0 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">
                  Series manuales (overlay)
                </p>
                <p className="m-0 mt-1 text-xs text-slate-500">
                  {syntheticSeries.length === 0
                    ? 'Agrega datos externos (otro estudio, referencia histórica) como línea punteada sobre la gráfica.'
                    : `${syntheticSeries.length} serie${syntheticSeries.length === 1 ? '' : 's'} activa${syntheticSeries.length === 1 ? '' : 's'} — se guardarán con la plantilla cuando persistas la gráfica.`}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowSyntheticEditor(true)}
                className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/20"
              >
                {syntheticSeries.length === 0 ? '+ Agregar serie manual' : 'Editar series manuales'}
              </button>
            </div>
          ) : null}
        </>
      ) : null}

      <SyntheticSeriesEditor
        open={showSyntheticEditor}
        onClose={() => setShowSyntheticEditor(false)}
        value={syntheticSeries}
        onChange={setSyntheticSeries}
        unitLabel={chartSelection.un}
        suggestedYears={
          compareLineData?.categories
            ? compareLineData.categories.map((c) => Number(c)).filter(Number.isFinite)
            : singleChartData?.categories?.map((c) => Number(c)).filter(Number.isFinite)
        }
      />

      <SaveChartModal
        open={showSaveChartModal}
        onClose={() => setShowSaveChartModal(false)}
        selection={chartSelection}
        compareMode={chartJobIds.length > 1 ? chartCompareMode : 'off'}
        numScenarios={chartJobIds.length > 1 ? chartJobIds.length : 1}
        yearsToPlot={chartCompareMode === 'by-year' || chartCompareMode === 'by-year-alt' ? chartYearsToPlot : null}
        syntheticSeries={syntheticSeries.length > 0 ? syntheticSeries : null}
        barOrientation={chartBarOrientation}
        facetPlacement={chartFacetPlacement}
        facetLegendMode={chartFacetLegendMode}
        chartLabel={getChartLabel(chartSelection.tipo) ?? null}
        saveButtonLabel={isAddToReportFlow ? "Guardar gráfica y agregar al reporte" : undefined}
        onSaved={async (tpl) => {
          if (!isAddToReportFlow || addToReportId == null) {
            setSavedChartToast(`"${tpl.name}" guardada. Úsala en el Generador de reportes.`);
            window.setTimeout(() => setSavedChartToast(null), 4000);
            return;
          }
          try {
            const report = await savedChartsApi.getReport(addToReportId);
            const items = Array.isArray(report.items) ? [...report.items] : [];
            const insertAt =
              addAfterIdx != null
                ? Math.max(0, Math.min(items.length, addAfterIdx + 1))
                : items.length;
            const existingIdx = items.indexOf(tpl.id);
            if (existingIdx >= 0) items.splice(existingIdx, 1);
            items.splice(insertAt, 0, tpl.id);
            const layoutUpdate = (() => {
              if (addMode !== "dashboard") return undefined;
              if (!report.layout) return undefined;
              const stripped = {
                ...report.layout,
                categories: report.layout.categories.map((c) => ({
                  ...c,
                  items: c.items.filter((id) => id !== tpl.id),
                  subcategories: c.subcategories.map((s) => ({
                    ...s,
                    items: s.items.filter((id) => id !== tpl.id),
                  })),
                })),
              };
              const nextCategories = stripped.categories.map((c) => {
                if (c.id !== addCatId) return c;
                if (addSubId) {
                  return {
                    ...c,
                    subcategories: c.subcategories.map((s) =>
                      s.id === addSubId ? { ...s, items: [...s.items, tpl.id] } : s,
                    ),
                  };
                }
                return { ...c, items: [...c.items, tpl.id] };
              });
              return { ...stripped, categories: nextCategories };
            })();
            await savedChartsApi.updateReport(addToReportId, {
              items,
              ...(layoutUpdate ? { layout: layoutUpdate } : {}),
            });
            if (addMode === "dashboard") {
              navigateResult(paths.reportDashboard(addToReportId));
            } else {
              navigateResult(`${paths.reports}?load=${addToReportId}`);
            }
          } catch (err) {
            setSavedChartToast(
              `"${tpl.name}" guardada, pero no se pudo agregar al reporte: ` +
                (err instanceof Error ? err.message : "error desconocido"),
            );
            window.setTimeout(() => setSavedChartToast(null), 6000);
          }
        }}
      />

      <SeriesOrderModal
        open={seriesOrderOpen}
        onClose={() => setSeriesOrderOpen(false)}
        series={seriesForModal}
        currentOrder={customSeriesOrder}
        onApply={(next) => setCustomSeriesOrder(next)}
      />

      {savedChartToast ? (
        <div
          className="fixed bottom-6 right-6 z-[300] rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200 shadow-2xl backdrop-blur-md"
          role="status"
        >
          {savedChartToast}
        </div>
      ) : null}

      {shareLinkToast ? (
        <div
          className="fixed bottom-6 right-6 z-[300] max-w-md rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100 shadow-2xl backdrop-blur-md"
          role="status"
        >
          {shareLinkToast}
        </div>
      ) : null}
    </div>
  );
}
