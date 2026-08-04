/**
 * Modal para reordenar manualmente las series de un chart apilado
 * (columnas / áreas / facet). Devuelve un nuevo array de nombres de
 * serie en el orden deseado.
 *
 * Convención visual del proyecto:
 *   - El primer elemento del array de series queda **abajo** del stack
 *     (Highcharts por defecto, ``yAxis.reversedStacks=false``), y aparece
 *     primero en la leyenda (no se invierte la leyenda). La leyenda se lee
 *     de abajo→arriba igual que el stack.
 *   - "Invertir orden" intercambia top↔bottom del stack.
 */
import { useEffect, useMemo, useState } from "react";

interface SeriesOrderModalProps {
  open: boolean;
  onClose: () => void;
  /** Series presentes en la gráfica actual (orden actual). */
  series: { name: string; color?: string | null | undefined }[];
  /** Orden custom actual (lista de nombres). null = orden natural. */
  currentOrder: string[] | null;
  /** Aplica el nuevo orden. Pasar null para volver al orden natural. */
  onApply: (next: string[] | null) => void;
}

export function SeriesOrderModal({
  open,
  onClose,
  series,
  currentOrder,
  onApply,
}: SeriesOrderModalProps) {
  const naturalNames = useMemo(() => series.map((s) => s.name), [series]);

  /** Reconcilia el orden custom con las series presentes. */
  const initialOrder = useMemo(() => {
    if (!currentOrder || currentOrder.length === 0) return naturalNames;
    const seen = new Set<string>();
    const ordered: string[] = [];
    for (const n of currentOrder) {
      if (naturalNames.includes(n) && !seen.has(n)) {
        ordered.push(n);
        seen.add(n);
      }
    }
    // Cualquier serie nueva que apareciera y no esté en el custom order, se
    // añade al final manteniendo su orden natural.
    for (const n of naturalNames) {
      if (!seen.has(n)) ordered.push(n);
    }
    return ordered;
  }, [currentOrder, naturalNames]);

  const [draft, setDraft] = useState<string[]>(initialOrder);
  useEffect(() => {
    if (open) setDraft(initialOrder);
  }, [open, initialOrder]);

  // Estado del drag & drop. ``dragIndex`` = índice de la fila que el usuario
  // está arrastrando; ``hoverIndex`` = posición de inserción mostrada (entre
  // dos filas). Mantenerlos como estado dispara re-render para pintar el
  // indicador visual mientras se arrastra.
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  if (!open) return null;

  const move = (idx: number, delta: -1 | 1) => {
    setDraft((prev) => {
      const next = [...prev];
      const target = idx + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[idx], next[target]] = [next[target]!, next[idx]!];
      return next;
    });
  };

  const reorderByDrag = (from: number, insertAt: number) => {
    setDraft((prev) => {
      if (from === insertAt || from === insertAt - 1) return prev;
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      // Si quitamos un ítem antes de la posición de inserción, el índice
      // destino baja en 1 para mantener la posición visual prometida.
      const adjusted = from < insertAt ? insertAt - 1 : insertAt;
      next.splice(adjusted, 0, moved!);
      return next;
    });
  };

  const invert = () => setDraft((prev) => [...prev].reverse());
  const resetNatural = () => setDraft(naturalNames);

  const colorByName = new Map<string, string | undefined>();
  for (const s of series) {
    colorByName.set(s.name, s.color || undefined);
  }

  const isCustom = draft.some((n, i) => n !== naturalNames[i]);

  const apply = () => {
    onApply(isCustom ? draft : null);
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[400] flex items-center justify-center bg-slate-950/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md max-h-[85vh] overflow-hidden rounded-xl border border-slate-700 bg-slate-900 text-slate-100 shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-800 px-5 py-3">
          <div>
            <h3 className="m-0 text-base font-semibold">Orden de series</h3>
            <p className="m-0 text-xs text-slate-400">
              El primer elemento queda <strong>arriba</strong> del stack.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-2xl leading-none text-slate-500 hover:text-slate-200"
            aria-label="Cerrar"
          >
            ×
          </button>
        </div>

        <div className="flex flex-wrap gap-2 border-b border-slate-800 px-5 py-2">
          <button
            type="button"
            onClick={invert}
            className="rounded border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-medium text-slate-100 hover:bg-slate-700"
          >
            ⇅ Invertir orden completo
          </button>
          <button
            type="button"
            onClick={resetNatural}
            className="rounded border border-slate-700 bg-slate-800/40 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700"
          >
            ↺ Restaurar natural
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-3">
          {draft.length === 0 ? (
            <p className="text-xs text-slate-500">No hay series.</p>
          ) : (
            <>
              <p className="m-0 mb-2 text-[11px] text-slate-500">
                Arrastra una fila desde el manejador <span className="font-mono">⋮⋮</span> para reordenar, o usa los botones ▲▼.
              </p>
              <ul
                className="space-y-1"
                onDragOver={(e) => {
                  // Permite drop en la lista (necesario para que onDrop dispare
                  // si el cursor cae fuera de cualquier fila pero dentro de la
                  // lista — ej. al final).
                  if (dragIndex !== null) e.preventDefault();
                }}
                onDrop={(e) => {
                  if (dragIndex === null) return;
                  e.preventDefault();
                  // Fallback: drop al final de la lista si no hay hoverIndex
                  // específico (cursor sobre el padding inferior).
                  const insertAt = hoverIndex ?? draft.length;
                  reorderByDrag(dragIndex, insertAt);
                  setDragIndex(null);
                  setHoverIndex(null);
                }}
              >
                {draft.map((name, idx) => {
                  const isDragging = dragIndex === idx;
                  const showTopIndicator = hoverIndex === idx && dragIndex !== null && dragIndex !== idx && dragIndex !== idx - 1;
                  const showBottomIndicator = idx === draft.length - 1 && hoverIndex === draft.length && dragIndex !== null && dragIndex !== idx;
                  return (
                    <li
                      key={name}
                      draggable
                      onDragStart={(e) => {
                        setDragIndex(idx);
                        setHoverIndex(idx);
                        e.dataTransfer.effectAllowed = "move";
                        // Algunos navegadores requieren setData para que el
                        // drag se inicie correctamente.
                        try { e.dataTransfer.setData("text/plain", name); } catch { /* noop */ }
                      }}
                      onDragEnter={(e) => {
                        if (dragIndex === null) return;
                        e.preventDefault();
                      }}
                      onDragOver={(e) => {
                        if (dragIndex === null) return;
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "move";
                        // Mitad superior → insertar antes de esta fila;
                        // mitad inferior → insertar después.
                        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                        const before = e.clientY < rect.top + rect.height / 2;
                        setHoverIndex(before ? idx : idx + 1);
                      }}
                      onDragEnd={() => {
                        setDragIndex(null);
                        setHoverIndex(null);
                      }}
                      className={[
                        "relative flex items-center gap-2 rounded border bg-slate-950/40 px-2 py-1.5 transition-opacity",
                        isDragging
                          ? "border-emerald-500/50 opacity-50"
                          : "border-slate-800",
                      ].join(" ")}
                      style={{
                        cursor: dragIndex !== null ? "grabbing" : undefined,
                      }}
                    >
                      {showTopIndicator ? (
                        <span
                          aria-hidden
                          className="pointer-events-none absolute -top-[3px] left-0 right-0 h-[3px] rounded-full bg-emerald-400"
                        />
                      ) : null}
                      {showBottomIndicator ? (
                        <span
                          aria-hidden
                          className="pointer-events-none absolute -bottom-[3px] left-0 right-0 h-[3px] rounded-full bg-emerald-400"
                        />
                      ) : null}
                      <span
                        title="Arrastra para reordenar"
                        className="inline-flex h-5 w-4 shrink-0 cursor-grab select-none items-center justify-center text-base leading-none text-slate-500 hover:text-slate-200 active:cursor-grabbing"
                        aria-hidden
                      >
                        ⋮⋮
                      </span>
                      <span
                        className="inline-block h-4 w-4 shrink-0 rounded-sm border border-slate-700"
                        style={{ background: colorByName.get(name) || "#94a3b8" }}
                        aria-hidden
                      />
                      <span className="flex-1 min-w-0 truncate text-xs">
                        <span className="text-slate-500 mr-2 font-mono">
                          {String(idx + 1).padStart(2, "0")}
                        </span>
                        {name}
                      </span>
                      <div className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          onClick={() => move(idx, -1)}
                          disabled={idx === 0}
                          className="rounded border border-slate-700 px-2 py-0.5 text-xs disabled:opacity-30 hover:bg-slate-700"
                          aria-label="Subir"
                        >
                          ▲
                        </button>
                        <button
                          type="button"
                          onClick={() => move(idx, 1)}
                          disabled={idx === draft.length - 1}
                          className="rounded border border-slate-700 px-2 py-0.5 text-xs disabled:opacity-30 hover:bg-slate-700"
                          aria-label="Bajar"
                        >
                          ▼
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-800 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-700 bg-slate-800/40 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={apply}
            className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500"
          >
            Aplicar
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Helper: reordena las series de un ChartDataResponse según una lista de
 * nombres. Series no listadas se añaden al final en orden natural. Devuelve
 * un nuevo objeto sin mutar el original.
 */
export function reorderChartSeries<
  T extends { series: { name: string }[] },
>(data: T, order: string[] | null): T {
  if (!order || order.length === 0) return data;
  const byName = new Map<string, T["series"][number]>();
  for (const s of data.series) byName.set(s.name, s);
  const ordered: T["series"][number][] = [];
  const used = new Set<string>();
  for (const n of order) {
    const s = byName.get(n);
    if (s && !used.has(n)) {
      ordered.push(s);
      used.add(n);
    }
  }
  for (const s of data.series) {
    if (!used.has(s.name)) ordered.push(s);
  }
  return { ...data, series: ordered };
}

/** Reordena las series de un CompareChartFacetResponse (uno por facet). */
export function reorderFacetSeries<
  T extends { facets: { series: { name: string }[] }[] },
>(data: T, order: string[] | null): T {
  if (!order || order.length === 0) return data;
  return {
    ...data,
    facets: data.facets.map((f) => reorderChartSeries(f, order)),
  };
}

/** Reordena las series de un CompareChartResponse (uno por subplot). */
export function reorderByYearSeries<
  T extends { subplots: { series: { name: string }[] }[] },
>(data: T, order: string[] | null): T {
  if (!order || order.length === 0) return data;
  return {
    ...data,
    subplots: data.subplots.map((sp) => reorderChartSeries(sp, order)),
  };
}
