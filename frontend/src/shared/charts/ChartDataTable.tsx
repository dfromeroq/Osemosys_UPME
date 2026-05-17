/**
 * ChartDataTable — renderiza un `ChartDataResponse` como tabla HTML.
 *
 * Es la "view_mode = table". Reusa el mismo dato que un chart de columnas
 * (`simulationApi.getChartData`) y aplica dos transformaciones opcionales en
 * cliente — paralelas a las del backend (`apply_period_years` y
 * `apply_cumulative_series` en `chart_service.py`):
 *   • `cumulative=true`  → cada serie muestra suma acumulada por categoría.
 *   • `periodYears=N`    → solo se muestran categorías cada N años.
 *
 * Las transformaciones en cliente garantizan que el render del visor sea
 * coherente con lo que se exporta vía `/export-chart` (ambos lados aplican
 * la misma lógica). Para PNG/SVG/CSV/XLSX descarga al backend con los mismos
 * parámetros vía `serverChartExport`.
 */
import React, { useEffect, useMemo, useState } from 'react';
import type {
  ChartDataResponse,
  ChartSeries,
  ResultTablePresentation,
} from '../../types/domain';
import type { ChartSelection } from './ChartSelector';
import { formatAxis3Sig } from './numberFormat';
import { downloadChartFromServer } from './serverChartExport';

interface Props {
  data: ChartDataResponse;
  /** Filtra categorías-año cada N. `null`/undefined = todos. */
  periodYears?: number | null;
  /** Si true, los valores se muestran como suma acumulada por serie. */
  cumulative?: boolean;
  /** Para descargar PNG/SVG/CSV/XLSX desde el backend. */
  serverExport?: { jobId: number; selection: ChartSelection };
  /** Sustituye el título proveniente de chart-data. */
  titleOverride?: string | null;
  /** Orden de filas por nombre de serie (misma semántica que plantillas guardadas). */
  customSeriesOrder?: string[] | null;
  /** Reglas admin: visibilidad, orden, colores, etiquetas, grupos, columnas. */
  presentation?: ResultTablePresentation | null;
}

/** Espejo de `_year_keep_indices` en backend. Categorías no-año se preservan. */
function yearKeepIndices(
  categories: ReadonlyArray<string | number>,
  period: number | null | undefined,
): number[] {
  if (!period || period < 2) return categories.map((_, i) => i);
  // Buscar índices que sean años parseables y aplicar el paso.
  const yearIdx: number[] = [];
  const yearVal: number[] = [];
  for (let i = 0; i < categories.length; i += 1) {
    const raw = categories[i];
    const y = typeof raw === 'number' ? raw : parseInt(String(raw), 10);
    if (!Number.isNaN(y)) {
      yearIdx.push(i);
      yearVal.push(y);
    }
  }
  if (yearIdx.length === 0) return categories.map((_, i) => i);
  const base = yearVal[0]!;
  const keep = new Set<number>();
  // Categorías no-año siempre se preservan.
  for (let i = 0; i < categories.length; i += 1) {
    if (!yearIdx.includes(i)) keep.add(i);
  }
  for (let k = 0; k < yearIdx.length; k += 1) {
    if ((yearVal[k]! - base) % period === 0) keep.add(yearIdx[k]!);
  }
  // Garantizar el último año.
  keep.add(yearIdx[yearIdx.length - 1]!);
  return Array.from(keep).sort((a, b) => a - b);
}

/** Espejo de `apply_cumulative_series` en backend (no muta la entrada). */
function applyCumulative(data: (number | null)[]): number[] {
  let running = 0;
  return data.map((v) => {
    const f = typeof v === 'number' && Number.isFinite(v) ? v : 0;
    running += f;
    return running;
  });
}

function reorderSeriesByNames(
  series: ChartSeries[],
  order: string[] | null | undefined,
): ChartSeries[] {
  if (!order || order.length === 0) return series;
  const m = new Map(series.map((s) => [s.name, s]));
  const out: ChartSeries[] = [];
  for (const n of order) {
    const s = m.get(n);
    if (s) {
      out.push(s);
      m.delete(n);
    }
  }
  for (const s of series) {
    if (m.has(s.name)) out.push(s);
  }
  return out;
}

type DisplayRow =
  | { kind: 'group'; label: string }
  | { kind: 'series'; series: ChartSeries; displayName: string };

function applyPresentationLayout(
  view: { cats: string[]; series: ChartSeries[]; totals: number[] },
  presentation: ResultTablePresentation | null | undefined,
): { cats: string[]; series: ChartSeries[]; totals: number[]; rows: DisplayRow[] } {
  if (!presentation || (!presentation.columns?.length && !presentation.series?.length)) {
    const rows: DisplayRow[] = view.series.map((s) => ({
      kind: 'series',
      series: s,
      displayName: s.name,
    }));
    return { ...view, rows };
  }

  const colRules = new Map((presentation.columns ?? []).map((c) => [c.id, c]));
  let orderedCatIds: string[];
  if (!presentation.columns?.length) {
    orderedCatIds = view.cats.map((c) => String(c));
  } else {
    const withMeta = view.cats.map((c, i) => ({
      id: String(c),
      i,
      rule: colRules.get(String(c)),
    }));
    const visible = withMeta.filter((x) => !x.rule?.hidden);
    const explicit = visible
      .filter((x) => x.rule != null && typeof x.rule.sort_order === 'number')
      .sort((a, b) => (a.rule!.sort_order! as number) - (b.rule!.sort_order! as number));
    const implicit = visible
      .filter((x) => !x.rule || typeof x.rule.sort_order !== 'number')
      .sort((a, b) => a.i - b.i);
    orderedCatIds = [...explicit, ...implicit].map((x) => x.id);
  }

  const oldIndices = orderedCatIds
    .map((id) => view.cats.findIndex((c) => String(c) === id))
    .filter((i) => i >= 0);
  const cats = oldIndices.map((i) => view.cats[i]!);
  const sliceData = (s: ChartSeries) =>
    oldIndices.map((i) => (i < s.data.length ? s.data[i]! : 0));
  let series = view.series.map((s) => ({ ...s, data: sliceData(s) }));

  const ruleByName = new Map((presentation.series ?? []).map((r) => [r.match, r]));
  series = series.filter((s) => !ruleByName.get(s.name)?.hidden);

  const totals =
    series.length === 0
      ? cats.map(() => 0)
      : cats.map((_, colIdx) =>
          series.reduce(
            (acc, s) => acc + (Number.isFinite(s.data[colIdx]) ? s.data[colIdx]! : 0),
            0,
          ),
        );

  const withOrder = series.map((s, origIdx) => {
    const r = ruleByName.get(s.name);
    const si = r?.sort_index;
    const sortKey = typeof si === 'number' ? si : 1_000_000 + origIdx;
    let color = s.color;
    if (r?.color && r.color.trim()) color = r.color.trim();
    return { s: { ...s, color }, sortKey, rule: r };
  });
  withOrder.sort((a, b) => a.sortKey - b.sortKey);

  const rows: DisplayRow[] = [];
  let lastG: string | null = null;
  for (const { s, rule } of withOrder) {
    const g = rule?.group_key?.trim() || null;
    if (g) {
      if (g !== lastG) rows.push({ kind: 'group', label: g });
      lastG = g;
    } else {
      lastG = null;
    }
    const displayName = rule?.display_label?.trim() || s.name;
    rows.push({ kind: 'series', series: s, displayName });
  }

  return { cats, series: withOrder.map((x) => x.s), totals, rows };
}

export const ChartDataTable: React.FC<Props> = ({
  data,
  periodYears,
  cumulative,
  serverExport,
  titleOverride,
  customSeriesOrder,
  presentation,
}) => {
  const [downloading, setDownloading] = useState<null | 'png' | 'svg' | 'csv' | 'xlsx'>(
    null,
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);

  // Selección por defecto: todas las series y todos los años visibles.
  const [selectedSeries, setSelectedSeries] = useState<Set<string>>(
    () => new Set(data.series.map((s) => s.name)),
  );
  const [selectedYears, setSelectedYears] = useState<Set<string>>(
    () => new Set(data.categories.map((c) => String(c))),
  );

  // Re-sincroniza la selección cuando cambian las series/categorías base
  // (cambio de variable, agrupación, unidad, etc.). Mantiene lo previamente
  // marcado si sigue presente; lo nuevo se marca también para no sorprender.
  useEffect(() => {
    setSelectedSeries((prev) => {
      const next = new Set<string>();
      for (const s of data.series) {
        if (prev.size === 0 || prev.has(s.name)) next.add(s.name);
      }
      // Si la selección previa estaba "todo", el conjunto anterior cubría todo;
      // como ya copiamos, está bien. Si estaba parcial pero ahora no queda
      // ninguna coincidencia, restablece a todas.
      return next.size > 0 ? next : new Set(data.series.map((s) => s.name));
    });
  }, [data.series]);

  useEffect(() => {
    setSelectedYears((prev) => {
      const next = new Set<string>();
      for (const c of data.categories) {
        const key = String(c);
        if (prev.size === 0 || prev.has(key)) next.add(key);
      }
      return next.size > 0 ? next : new Set(data.categories.map((c) => String(c)));
    });
  }, [data.categories]);

  const view = useMemo(() => {
    const ordered = reorderSeriesByNames(data.series, customSeriesOrder ?? null);
    // 1) Acumular (si aplica) sobre TODAS las categorías originales.
    const seriesCum = ordered.map((s) => ({
      ...s,
      data: cumulative ? applyCumulative(s.data) : s.data.slice(),
    }));
    // 2) Filtrar columnas por período.
    const keep = yearKeepIndices(data.categories, periodYears ?? null);
    const cats = keep.map((i) => String(data.categories[i]!));
    const series = seriesCum.map((s) => ({
      ...s,
      data: keep.map((i) => (i < s.data.length ? s.data[i]! : 0)),
    }));
    // 3) Totales por columna.
    const totals = cats.map((_, colIdx) =>
      series.reduce((acc, s) => acc + (Number.isFinite(s.data[colIdx]) ? s.data[colIdx]! : 0), 0),
    );
    return applyPresentationLayout({ cats, series, totals }, presentation ?? null);
  }, [data, cumulative, periodYears, customSeriesOrder, presentation]);

  const displayTitle = titleOverride?.trim() || data.title;
  // ¿La selección actual cubre todo? Si sí, no enviamos filtros al backend.
  const allSeriesSelected = selectedSeries.size === data.series.length;
  const allYearsSelected = selectedYears.size === data.categories.length;

  const handleDownload = async (fmt: 'png' | 'svg' | 'csv' | 'xlsx') => {
    if (!serverExport) return;
    setDownloading(fmt);
    setMenuOpen(false);
    try {
      const filters: { series?: string[]; years?: (string | number)[] } = {};
      if (!allSeriesSelected) filters.series = Array.from(selectedSeries);
      if (!allYearsSelected) filters.years = Array.from(selectedYears);
      await downloadChartFromServer(
        serverExport.jobId,
        serverExport.selection,
        fmt,
        filters,
      );
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('[ChartDataTable] download error', err);
      alert('No se pudo descargar la tabla.');
    } finally {
      setDownloading(null);
    }
  };

  const toggleSeries = (name: string) => {
    setSelectedSeries((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };
  const toggleYear = (year: string) => {
    setSelectedYears((prev) => {
      const next = new Set(prev);
      if (next.has(year)) next.delete(year);
      else next.add(year);
      return next;
    });
  };

  return (
    <div className="w-full">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0">
          <h3 className="m-0 text-sm font-semibold text-slate-100 break-words">
            {displayTitle}
          </h3>
          <p className="m-0 text-[11px] text-slate-500">
            {data.yAxisLabel}
            {periodYears && periodYears >= 2 ? ` · cada ${periodYears} años` : ''}
            {cumulative ? ' · acumulado' : ''}
          </p>
        </div>
        {serverExport ? (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setFiltersOpen((v) => !v)}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700"
              title="Elige tecnologías y años a incluir en la exportación"
            >
              {`Filtrar exportación${
                allSeriesSelected && allYearsSelected
                  ? ''
                  : ` · ${selectedSeries.size}/${data.series.length} tec, ${selectedYears.size}/${data.categories.length} años`
              }`}
            </button>
            <div className="relative">
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700"
                disabled={downloading != null}
              >
                {downloading ? 'Descargando…' : 'Descargar ▾'}
              </button>
              {menuOpen ? (
                <div className="absolute right-0 top-full z-30 mt-1 w-40 rounded-lg border border-slate-700 bg-slate-900 shadow-2xl">
                  {(['png', 'svg', 'csv', 'xlsx'] as const).map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => void handleDownload(f)}
                      className="block w-full px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800"
                    >
                      Descargar {f.toUpperCase()}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      {serverExport && filtersOpen ? (
        <div className="mb-2 grid grid-cols-1 md:grid-cols-2 gap-3 rounded-lg border border-slate-700 bg-slate-900/60 p-3">
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px] font-semibold text-slate-200">
                Tecnologías ({selectedSeries.size}/{data.series.length})
              </span>
              <div className="flex gap-1">
                <button
                  type="button"
                  className="text-[10px] text-slate-400 hover:text-slate-200 underline"
                  onClick={() =>
                    setSelectedSeries(new Set(data.series.map((s) => s.name)))
                  }
                >
                  Todas
                </button>
                <button
                  type="button"
                  className="text-[10px] text-slate-400 hover:text-slate-200 underline"
                  onClick={() => setSelectedSeries(new Set())}
                >
                  Ninguna
                </button>
              </div>
            </div>
            <div className="max-h-44 overflow-auto rounded border border-slate-800 p-2">
              {data.series.map((s) => (
                <label
                  key={s.name}
                  className="flex items-center gap-2 py-0.5 text-[11px] text-slate-200 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedSeries.has(s.name)}
                    onChange={() => toggleSeries(s.name)}
                  />
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-sm flex-shrink-0"
                    style={{ background: s.color }}
                  />
                  <span className="truncate" title={s.name}>
                    {s.name}
                  </span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px] font-semibold text-slate-200">
                Años ({selectedYears.size}/{data.categories.length})
              </span>
              <div className="flex gap-1">
                <button
                  type="button"
                  className="text-[10px] text-slate-400 hover:text-slate-200 underline"
                  onClick={() =>
                    setSelectedYears(new Set(data.categories.map((c) => String(c))))
                  }
                >
                  Todos
                </button>
                <button
                  type="button"
                  className="text-[10px] text-slate-400 hover:text-slate-200 underline"
                  onClick={() => setSelectedYears(new Set())}
                >
                  Ninguno
                </button>
              </div>
            </div>
            <div className="max-h-44 overflow-auto rounded border border-slate-800 p-2 grid grid-cols-3 gap-x-2 gap-y-0.5">
              {data.categories.map((c) => {
                const key = String(c);
                return (
                  <label
                    key={key}
                    className="flex items-center gap-1.5 text-[11px] text-slate-200 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedYears.has(key)}
                      onChange={() => toggleYear(key)}
                    />
                    <span>{key}</span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}

      <div className="overflow-auto rounded-lg border border-slate-800 max-h-[60vh]">
        <table className="min-w-full border-collapse text-xs text-slate-200">
          <thead className="bg-slate-800 sticky top-0 z-10">
            <tr>
              <th
                className="px-3 py-2 text-left font-semibold uppercase tracking-wider text-[10px] text-slate-300 border-r border-slate-700"
                style={{ minWidth: 200, maxWidth: 280 }}
              >
                Tecnología
              </th>
              {view.cats.map((c, i) => (
                <th
                  key={`h-${i}`}
                  className="px-3 py-2 text-right font-semibold uppercase tracking-wider text-[10px] text-slate-300"
                >
                  {String(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(() => {
              let stripe = 0;
              return view.rows.map((row, rIdx) => {
                if (row.kind === 'group') {
                  return (
                    <tr key={`g-${rIdx}-${row.label}`} className="bg-slate-800/90">
                      <td
                        colSpan={view.cats.length + 1}
                        className="px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-300"
                      >
                        {row.label}
                      </td>
                    </tr>
                  );
                }
                const s = row.series;
                const cls = stripe % 2 === 0 ? 'bg-slate-900/40' : 'bg-slate-900/20';
                stripe += 1;
                return (
                  <tr key={`r-${rIdx}-${s.name}`} className={cls}>
                    <td
                      className="px-3 py-1.5 font-semibold text-white border-r border-slate-700/60 break-words"
                      style={{
                        background: s.color,
                        minWidth: 200,
                        maxWidth: 280,
                        width: 240,
                        whiteSpace: 'normal',
                        wordBreak: 'break-word',
                        lineHeight: 1.25,
                      }}
                      title={s.name}
                    >
                      {row.displayName}
                    </td>
                    {view.cats.map((_c, cIdx) => (
                      <td
                        key={`c-${rIdx}-${cIdx}`}
                        className="px-3 py-1.5 text-right tabular-nums text-slate-100 whitespace-nowrap"
                      >
                        {formatAxis3Sig(s.data[cIdx])}
                      </td>
                    ))}
                  </tr>
                );
              });
            })()}
            {view.series.length > 0 ? (
              <tr className="bg-slate-700/60 font-semibold">
                <td
                  className="px-3 py-1.5 text-white border-r border-slate-700/60"
                  style={{ minWidth: 200, maxWidth: 280, width: 240 }}
                >
                  Total
                </td>
                {view.totals.map((t, cIdx) => (
                  <td
                    key={`t-${cIdx}`}
                    className="px-3 py-1.5 text-right tabular-nums text-white whitespace-nowrap"
                  >
                    {formatAxis3Sig(t)}
                  </td>
                ))}
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
};
