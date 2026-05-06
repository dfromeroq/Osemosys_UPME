/**
 * Tarjeta de gráfica para el dashboard del reporte:
 *   - Resuelve job_ids slot-a-slot desde los escenarios globales.
 *   - Pide los datos al backend (chart-data o compare-facet) según
 *     `template.compare_mode`.
 *   - Renderiza con `HighchartsChart` o `CompareChartFacet`.
 *   - Indica claramente cuando faltan escenarios o no hay datos.
 */
import { useEffect, useMemo, useState } from "react";
import { simulationApi } from "@/features/simulation/api/simulationApi";
import { HighchartsChart } from "@/shared/charts/HighchartsChart";
import { CompareChart } from "@/shared/charts/CompareChart";
import { CompareChartFacet } from "@/shared/charts/CompareChartFacet";
import { LineChart } from "@/shared/charts/LineChart";
import { ParetoChart } from "@/shared/charts/ParetoChart";
import { ChartDataTable } from "@/shared/charts/ChartDataTable";
import type {
  ChartDataResponse,
  CompareChartFacetResponse,
  CompareChartResponse,
  ParetoChartResponse,
  SavedChartTemplate,
} from "@/types/domain";
import type { ChartSelection } from "@/shared/charts/ChartSelector";
import {
  reorderChartSeries,
  reorderFacetSeries,
  reorderByYearSeries,
} from "@/shared/charts/SeriesOrderModal";
import { EditChartCardModal } from "./EditChartCardModal";

function templateToSelection(t: SavedChartTemplate): ChartSelection {
  const sel: ChartSelection = { tipo: t.tipo, un: t.un };
  if (t.sub_filtro) sel.sub_filtro = t.sub_filtro;
  if (t.loc) sel.loc = t.loc;
  if (t.variable) sel.variable = t.variable;
  if (t.agrupar_por) sel.agrupar_por = t.agrupar_por;
  if (t.view_mode) sel.viewMode = t.view_mode;
  // Propagamos los parámetros de tabla para que el endpoint de export
  // (`/export-chart?view_mode=table&...`) reciba el período y acumulado
  // configurados en la plantilla.
  if (t.view_mode === "table") {
    if (typeof t.table_period_years === "number") {
      sel.tablePeriodYears = t.table_period_years;
    }
    if (typeof t.table_cumulative === "boolean") {
      sel.tableCumulative = t.table_cumulative;
    }
  }
  // Modificadores universales — fluyen al endpoint de export (B) cuando se
  // descarga PNG/SVG/CSV/XLSX directo desde el dashboard.
  if (t.custom_series_order && t.custom_series_order.length > 0) {
    sel.customSeriesOrder = t.custom_series_order;
  }
  if (typeof t.y_axis_min === "number") sel.yAxisMin = t.y_axis_min;
  if (typeof t.y_axis_max === "number") sel.yAxisMax = t.y_axis_max;
  return sel;
}

type Props = {
  template: SavedChartTemplate;
  jobIds: number[];
  /** Si true, los controles del facet se compactan en un menú "⋯". */
  compactToolbar?: boolean;
  /**
   * Sufijo a agregar al título cuando la gráfica de un solo escenario vive en
   * un reporte multi-escenario (e.g. "Alto", "Bajo"). El componente antepone
   * " — " automáticamente.
   */
  scenarioAliasSuffix?: string | undefined;
  /**
   * Nombres (alias) a usar por escenario, paralelos a `jobIds`. Se aplican
   * como override al nombre/leyenda de series/facets en multi-escenario.
   */
  scenarioNames?: string[] | undefined;
  /** Filtro de rango de años aplicado en cliente al recibir los datos. */
  yearFrom?: number | null | undefined;
  yearTo?: number | null | undefined;
  /**
   * Habilita el botón "Editar gráfica" en este card. Cuando el usuario es
   * dueño del template, el PATCH se aplica directo. Si no es dueño, se
   * emite ``onTemplateReplaced(oldId, newTemplate)`` para que la página
   * padre (ReportDashboardPage) reemplace la referencia en el reporte.
   */
  onTemplateUpdated?: (updated: SavedChartTemplate) => void;
  onTemplateReplaced?: (oldId: number, newTemplate: SavedChartTemplate) => void;
};

/** Filtra in-place categorías-año y datos paralelos por [yearFrom, yearTo]. */
function _yearKeepIndices(
  categories: ReadonlyArray<string | number>,
  yearFrom: number | null | undefined,
  yearTo: number | null | undefined,
): number[] {
  if ((yearFrom == null) && (yearTo == null)) {
    return categories.map((_, i) => i);
  }
  const keep: number[] = [];
  for (let i = 0; i < categories.length; i += 1) {
    const raw = categories[i];
    const y = typeof raw === "number" ? raw : parseInt(String(raw), 10);
    if (Number.isNaN(y)) {
      keep.push(i);
      continue;
    }
    if (yearFrom != null && y < yearFrom) continue;
    if (yearTo != null && y > yearTo) continue;
    keep.push(i);
  }
  return keep;
}

function _applyYearRangeChart<
  T extends ChartDataResponse,
>(d: T, yearFrom: number | null | undefined, yearTo: number | null | undefined): T {
  if (yearFrom == null && yearTo == null) return d;
  const cats = d.categories;
  const series = d.series;
  if (!cats || !series) return d;
  const keep = _yearKeepIndices(cats, yearFrom, yearTo);
  d.categories = keep.map((i) => String(cats[i]));
  d.series = series.map((s) => ({
    ...s,
    data: keep.map((i) => (i < s.data.length ? (s.data[i] as number) : 0)),
  }));
  return d;
}

function _applyYearRangeFacet(
  d: CompareChartFacetResponse,
  yearFrom: number | null | undefined,
  yearTo: number | null | undefined,
): CompareChartFacetResponse {
  if (yearFrom == null && yearTo == null) return d;
  d.facets = d.facets.map((f) => {
    const keep = _yearKeepIndices(f.categories, yearFrom, yearTo);
    return {
      ...f,
      categories: keep.map((i) => f.categories[i] as string),
      series: f.series.map((s) => ({
        ...s,
        data: keep.map((i) => (i < s.data.length ? (s.data[i] as number) : 0)),
      })),
    };
  });
  return d;
}

export function DashboardChartCard({
  template,
  jobIds,
  compactToolbar = false,
  scenarioAliasSuffix,
  scenarioNames,
  yearFrom,
  yearTo,
  onTemplateUpdated,
  onTemplateReplaced,
}: Props) {
  const [single, setSingle] = useState<ChartDataResponse | null>(null);
  const [facet, setFacet] = useState<CompareChartFacetResponse | null>(null);
  const [byYear, setByYear] = useState<CompareChartResponse | null>(null);
  const [lineTotal, setLineTotal] = useState<ChartDataResponse | null>(null);
  const [pareto, setPareto] = useState<ParetoChartResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);

  // Lista de series visibles AHORA, para el modal de orden.
  const seriesNamesForEdit = useMemo<{ name: string; color?: string | null | undefined }[]>(() => {
    const seen = new Map<string, string | null | undefined>();
    const push = (name: string, color?: string | null) => {
      if (!seen.has(name)) seen.set(name, color);
    };
    if (facet) {
      for (const f of facet.facets) for (const s of f.series) push(s.name, s.color);
    } else if (byYear) {
      for (const sp of byYear.subplots) for (const s of sp.series) push(s.name, s.color);
    } else if (lineTotal) {
      for (const s of lineTotal.series) push(s.name, s.color);
    } else if (single) {
      for (const s of single.series) push(s.name, s.color);
    }
    return Array.from(seen.entries()).map(([name, color]) => ({ name, color }));
  }, [single, facet, byYear, lineTotal]);
  const canEdit = onTemplateUpdated != null || onTemplateReplaced != null;
  // Pareto y "table" no soportan reorder en este modal por ahora; el botón
  // se oculta para evitar confusión. Una iteración futura podría añadir
  // edición específica para esos modos.
  const editSupported = template.view_mode !== "pareto" && template.view_mode !== "table";

  const ready =
    jobIds.length === template.num_scenarios && jobIds.every((j) => j != null);

  // Fingerprint estable para evitar re-fetch redundante.
  // Incluimos el rango de años para invalidar el render cuando cambie.
  const fingerprint = `${template.id}|${template.compare_mode}|${jobIds.join(",")}|${(template.years_to_plot ?? []).join(",")}|yf=${yearFrom ?? ""}|yt=${yearTo ?? ""}`;

  useEffect(() => {
    if (!ready) {
      setSingle(null);
      setFacet(null);
      setByYear(null);
      setLineTotal(null);
      setPareto(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    const reportTitleOverride = template.report_title?.trim() || null;
    const suffix = scenarioAliasSuffix?.trim() || null;
    const applyTitle = <T extends { title?: string | null }>(d: T): T => {
      const base = reportTitleOverride ?? (d.title ?? "");
      const finalTitle = suffix ? `${base} — ${suffix}` : base;
      if (reportTitleOverride || suffix) {
        (d as { title?: string }).title = finalTitle;
      }
      return d;
    };
    /** Aplica los aliases (paralelos a jobIds) al nombre de series/facets. */
    const aliasOf = (i: number): string | null => {
      const v = scenarioNames?.[i]?.trim();
      return v && v.length > 0 ? v : null;
    };
    const applyFacetAliases = (d: CompareChartFacetResponse) => {
      d.facets = d.facets.map((f, i) => {
        const a = aliasOf(i);
        return a
          ? {
              ...f,
              display_name: a,
              scenario_name: a,
              // Cuando el alias reemplaza el nombre del escenario, limpiamos
              // la etiqueta para que el subtítulo quede "Alias" y no "Alias — Tag".
              scenario_tag_name: null,
            }
          : f;
      });
      return d;
    };
    const applySeriesAliases = <T extends { series: { name: string }[] }>(d: T): T => {
      d.series = d.series.map((s, i) => {
        const a = aliasOf(i);
        return a ? { ...s, name: a } : s;
      });
      return d;
    };
    const applyByYearAliases = (d: CompareChartResponse): CompareChartResponse => {
      d.subplots = d.subplots.map((sub) => ({
        ...sub,
        series: sub.series.map((s, i) => {
          const a = aliasOf(i);
          return a ? { ...s, name: a } : s;
        }),
      }));
      return d;
    };

    const esPorcentaje = template.view_mode === "porcentaje";

    if (template.view_mode === "pareto" && template.compare_mode === "off") {
      const params: Record<string, string> = {
        tipo: template.tipo,
        un: template.un,
      };
      if (template.sub_filtro) params.sub_filtro = template.sub_filtro;
      if (template.loc) params.loc = template.loc;
      const jobId = jobIds[0]!;
      simulationApi
        .getParetoData(
          jobId,
          params as Parameters<typeof simulationApi.getParetoData>[1],
        )
        .then((data) => {
          if (cancelled) return;
          setPareto(applyTitle(data));
          setSingle(null);
          setFacet(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : "Error cargando gráfica.");
        })
        .finally(() => !cancelled && setLoading(false));
      return () => {
        cancelled = true;
      };
    }

    if (template.compare_mode === "facet") {
      const params: Record<string, string> = {
        job_ids: jobIds.join(","),
        tipo: template.tipo,
        un: template.un,
      };
      if (template.sub_filtro) params.sub_filtro = template.sub_filtro;
      if (template.loc) params.loc = template.loc;
      if (template.variable) params.variable = template.variable;
      if (template.agrupar_por) params.agrupar_por = template.agrupar_por;
      if (esPorcentaje) params.es_porcentaje = "true";
      simulationApi
        .getCompareFacetData(
          params as Parameters<typeof simulationApi.getCompareFacetData>[0],
        )
        .then((data) => {
          if (cancelled) return;
          setFacet(
            applyTitle(
              applyFacetAliases(_applyYearRangeFacet(data, yearFrom, yearTo)),
            ),
          );
          setSingle(null);
          setByYear(null);
          setLineTotal(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : "Error cargando gráfica.");
        })
        .finally(() => !cancelled && setLoading(false));
    } else if (template.compare_mode === "by-year") {
      // Recortar la lista de años explícita al rango si está activo.
      const allYears = template.years_to_plot ?? [];
      const filteredYears = (yearFrom != null || yearTo != null)
        ? allYears.filter(
            (y) =>
              (yearFrom == null || y >= yearFrom) &&
              (yearTo == null || y <= yearTo),
          )
        : allYears;
      const params: Record<string, string> = {
        job_ids: jobIds.join(","),
        tipo: template.tipo,
        un: template.un,
        years_to_plot: filteredYears.join(","),
      };
      if (template.sub_filtro) params.sub_filtro = template.sub_filtro;
      if (template.loc) params.loc = template.loc;
      if (template.agrupar_por) params.agrupacion = template.agrupar_por;
      if (esPorcentaje) params.es_porcentaje = "true";

      simulationApi
        .getCompareData(
          params as Parameters<typeof simulationApi.getCompareData>[0],
        )
        .then((data) => {
          if (cancelled) return;
          setByYear(applyTitle(applyByYearAliases(data)));
          setSingle(null);
          setFacet(null);
          setLineTotal(null);
        })
    } else if (template.compare_mode === "by-year-alt") {
      // Recortar la lista de años explícita al rango si está activo.
      const allYears = template.years_to_plot ?? [];
      const filteredYears = (yearFrom != null || yearTo != null)
        ? allYears.filter(
            (y) =>
              (yearFrom == null || y >= yearFrom) &&
              (yearTo == null || y <= yearTo),
          )
        : allYears;
      const params: Record<string, string> = {
        job_ids: jobIds.join(","),
        tipo: template.tipo,
        un: template.un,
        years_to_plot: filteredYears.join(","),
        group_by: "scenario",
      };
      if (template.sub_filtro) params.sub_filtro = template.sub_filtro;
      if (template.loc) params.loc = template.loc;
      if (template.agrupar_por) params.agrupacion = template.agrupar_por;
      if (esPorcentaje) params.es_porcentaje = "true";

      simulationApi
        .getCompareData(
          params as Parameters<typeof simulationApi.getCompareData>[0],
        )
        .then((data) => {
          if (cancelled) return;
          setByYear(applyTitle(applyByYearAliases(data)));
          setSingle(null);
          setFacet(null);
          setLineTotal(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : "Error cargando gráfica.");
        })
        .finally(() => !cancelled && setLoading(false));
    } else if (template.compare_mode === "line-total") {
      const params: Record<string, string> = {
        job_ids: jobIds.join(","),
        tipo: template.tipo,
        un: template.un,
      };
      if (template.sub_filtro) params.sub_filtro = template.sub_filtro;
      if (template.loc) params.loc = template.loc;
      simulationApi
        .getCompareLineData(
          params as Parameters<typeof simulationApi.getCompareLineData>[0],
        )
        .then((data) => {
          if (cancelled) return;
          setLineTotal(
            applyTitle(
              applySeriesAliases(_applyYearRangeChart(data, yearFrom, yearTo)),
            ),
          );
          setSingle(null);
          setFacet(null);
          setByYear(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : "Error cargando gráfica.");
        })
        .finally(() => !cancelled && setLoading(false));
    } else {
      const params: Record<string, string> = {
        tipo: template.tipo,
        un: template.un,
      };
      if (template.sub_filtro) params.sub_filtro = template.sub_filtro;
      if (template.loc) params.loc = template.loc;
      if (template.variable) params.variable = template.variable;
      if (template.agrupar_por) params.agrupar_por = template.agrupar_por;
      if (esPorcentaje) params.es_porcentaje = "true";
      const jobId = jobIds[0]!;
      simulationApi
        .getChartData(
          jobId,
          params as Parameters<typeof simulationApi.getChartData>[1],
        )
        .then((data) => {
          if (cancelled) return;
          setSingle(applyTitle(_applyYearRangeChart(data, yearFrom, yearTo)));
          setFacet(null);
          setByYear(null);
          setLineTotal(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : "Error cargando gráfica.");
        })
        .finally(() => !cancelled && setLoading(false));
    }

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    fingerprint,
    scenarioAliasSuffix,
    template.report_title,
    scenarioNames?.join("|"),
  ]);

  const selection = useMemo(() => templateToSelection(template), [template]);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3 min-h-[360px] relative">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="m-0 text-sm font-semibold text-white break-words">
            {template.report_title || template.name}
          </h3>
          {template.report_title ? (
            <p className="m-0 text-[11px] text-slate-500 break-words">
              <span className="text-slate-600">Gráfica oficial:</span>{" "}
              {template.name}
            </p>
          ) : null}
          <p className="m-0 text-[11px] text-slate-500">
            {template.tipo} · {template.un}
            {template.compare_mode === "facet"
              ? ` · facet × ${template.num_scenarios}`
              : template.compare_mode === "by-year"
              ? ` · por año × ${template.num_scenarios}`
              : template.compare_mode === "line-total"
              ? ` · líneas totales × ${template.num_scenarios}`
              : ""}
          </p>
        </div>
        {canEdit && editSupported ? (
          <button
            type="button"
            onClick={() => setEditOpen(true)}
            disabled={!ready || seriesNamesForEdit.length === 0}
            className="inline-flex shrink-0 items-center gap-1 rounded border border-cyan-500/30 bg-cyan-500/5 px-2 py-1 text-[11px] font-semibold text-cyan-300 hover:bg-cyan-500/15 disabled:opacity-40 disabled:cursor-not-allowed"
            title={
              template.is_owner
                ? "Editar configuración (orden de series, eje Y) — afecta a todos los reportes que la usen"
                : "Crear copia con tu configuración personal (no modifica la original)"
            }
          >
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            Editar
            {!template.is_owner ? (
              <span className="ml-0.5 rounded-full bg-amber-500/30 px-1 py-0.5 text-[8px] uppercase text-amber-200">
                copia
              </span>
            ) : null}
          </button>
        ) : null}
      </div>

      <div className="rounded-lg border border-slate-800/70 bg-slate-950/30 p-3 min-h-[280px] relative">
        {loading ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-slate-950/70 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-2">
              <div className="h-6 w-6 rounded-full border-2 border-slate-700 border-t-emerald-500 animate-spin" />
              <span className="text-xs text-slate-400">Cargando…</span>
            </div>
          </div>
        ) : null}

        {error ? (
          <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-200">
            {error}
          </div>
        ) : !ready ? (
          <div className="flex h-[260px] items-center justify-center text-xs text-slate-500 text-center px-4">
            Selecciona{" "}
            {template.num_scenarios === 1
              ? "un escenario"
              : `${template.num_scenarios} escenarios`}{" "}
            arriba para ver esta gráfica.
          </div>
        ) : template.compare_mode === "facet" && facet ? (
          <CompareChartFacet
            data={reorderFacetSeries(facet, template.custom_series_order ?? null)}
            barOrientation={
              (template.bar_orientation ?? "vertical") as "vertical" | "horizontal"
            }
            facetPlacement={
              (template.facet_placement ?? "inline") as "inline" | "stacked"
            }
            legendMode={
              (template.facet_legend_mode ?? "shared") as "shared" | "perFacet"
            }
            viewMode={template.view_mode === "line" ? "line" : "column"}
            serverFacetExport={{ jobIds, selection }}
            compactToolbar={compactToolbar}
            yAxisMin={template.y_axis_min ?? null}
            yAxisMax={template.y_axis_max ?? null}
          />
        ) : (template.compare_mode === "by-year" || template.compare_mode === "by-year-alt") && byYear ? (
          <CompareChart
            data={reorderByYearSeries(byYear, template.custom_series_order ?? null)}
            barOrientation={
              (template.bar_orientation ?? "vertical") as "vertical" | "horizontal"
            }
            yAxisMin={template.y_axis_min ?? null}
            yAxisMax={template.y_axis_max ?? null}
          />
        ) : template.compare_mode === "line-total" && lineTotal ? (
          <LineChart
            data={reorderChartSeries(lineTotal, template.custom_series_order ?? null)}
            syntheticSeries={
              template.synthetic_series
                ? template.synthetic_series.filter((s) => s.active !== false)
                : undefined
            }
            yAxisMin={template.y_axis_min ?? null}
            yAxisMax={template.y_axis_max ?? null}
          />
        ) : template.view_mode === "pareto" && pareto ? (
          <ParetoChart
            data={pareto}
            serverExport={{ jobId: jobIds[0]!, selection }}
          />
        ) : template.view_mode === "table" && single ? (
          <ChartDataTable
            data={single}
            periodYears={template.table_period_years ?? null}
            cumulative={Boolean(template.table_cumulative)}
            serverExport={{ jobId: jobIds[0]!, selection }}
          />
        ) : template.view_mode === "line" && single ? (
          <LineChart
            data={reorderChartSeries(single, template.custom_series_order ?? null)}
            serverExport={{ jobId: jobIds[0]!, selection }}
            syntheticSeries={
              template.synthetic_series
                ? template.synthetic_series.filter((s) => s.active !== false)
                : undefined
            }
            yAxisMin={template.y_axis_min ?? null}
            yAxisMax={template.y_axis_max ?? null}
          />
        ) : single ? (
          <HighchartsChart
            data={reorderChartSeries(single, template.custom_series_order ?? null)}
            barOrientation={
              (template.bar_orientation ?? "vertical") as "vertical" | "horizontal"
            }
            serverExport={{ jobId: jobIds[0]!, selection }}
            stackType={template.view_mode === "area" ? "area" : "column"}
            yAxisMin={template.y_axis_min ?? null}
            yAxisMax={template.y_axis_max ?? null}
          />
        ) : !loading ? (
          <div className="flex h-[260px] items-center justify-center text-xs text-slate-500">
            Sin datos.
          </div>
        ) : null}
      </div>

      <EditChartCardModal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        template={template}
        seriesNames={seriesNamesForEdit}
        onTemplateUpdated={(updated) => {
          onTemplateUpdated?.(updated);
        }}
        onTemplateReplaced={(oldId, newTpl) => {
          onTemplateReplaced?.(oldId, newTpl);
        }}
      />
    </div>
  );
}
