/**
 * Editor de series sintéticas (overlays manuales) para gráficas de línea.
 *
 * Features:
 *   - Lista de series con nombre, color, **estilo de línea**, **marker** y **grosor**.
 *   - Tabla (año, valor) por serie con add/remove filas.
 *   - **Paste tipo Excel**: al pegar desde Excel/Google Sheets se detectan tabs/
 *     saltos de línea y se expanden filas automáticamente. Soporta:
 *       • celda única (paste normal)
 *       • fila completa (ej. "2020\t100" en celda año)
 *       • columna completa (ej. "100\n200\n300" en celda valor)
 *       • matriz completa (2 cols: año, valor → todas las filas)
 *
 * Uso típico: overlay de datos externos (estudio comparable, referencia
 * histórica, escenario teórico) sobre una gráfica de líneas totales.
 */
import {
  useEffect,
  useMemo,
  useState,
  type ClipboardEvent,
} from "react";
import { Plus, Trash2, X } from "lucide-react";
import { Modal } from "@/shared/components/Modal";
import { Button } from "@/shared/components/Button";
import { parseNumber, parseTabular } from "./tabularUtils";
import type {
  SyntheticLineStyle,
  SyntheticMarkerSymbol,
  SyntheticSeries,
} from "@/types/domain";

type Props = {
  open: boolean;
  onClose: () => void;
  value: SyntheticSeries[];
  onChange: (next: SyntheticSeries[]) => void;
  /** Unidad del chart (se muestra como hint en la tabla). */
  unitLabel?: string | undefined;
  /** Años sugeridos para autocompletar una serie nueva. */
  suggestedYears?: number[] | undefined;
};

function makeId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `ss-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

const DEFAULT_COLORS = [
  "#ec4899",
  "#f97316",
  "#eab308",
  "#22c55e",
  "#06b6d4",
  "#8b5cf6",
  "#f43f5e",
  "#14b8a6",
];

function pickDefaultColor(existing: SyntheticSeries[]): string {
  const used = new Set(existing.map((s) => s.color.toLowerCase()));
  const first = DEFAULT_COLORS.find((c) => !used.has(c.toLowerCase()));
  return first ?? DEFAULT_COLORS[(existing.length * 3) % DEFAULT_COLORS.length]!;
}

const LINE_STYLE_OPTIONS: Array<{ value: SyntheticLineStyle; label: string }> = [
  { value: "Solid", label: "Sólida" },
  { value: "Dash", label: "Dash" },
  { value: "ShortDash", label: "Dash corto" },
  { value: "Dot", label: "Puntos" },
  { value: "DashDot", label: "Dash-punto" },
];

const MARKER_OPTIONS: Array<{ value: SyntheticMarkerSymbol; label: string }> = [
  { value: "circle", label: "● Círculo" },
  { value: "diamond", label: "◆ Diamante" },
  { value: "square", label: "■ Cuadrado" },
  { value: "triangle", label: "▲ Triángulo" },
  { value: "triangle-down", label: "▼ Triángulo inv." },
  { value: "none", label: "— Sin marker" },
];

export function SyntheticSeriesEditor({
  open,
  onClose,
  value,
  onChange,
  unitLabel,
  suggestedYears,
}: Props) {
  const [draft, setDraft] = useState<SyntheticSeries[]>(value);

  useEffect(() => {
    if (open) {
      setDraft(
        value.map((s) => ({
          ...s,
          data: s.data.map((p) => [...p] as [number, number]),
        })),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const addSeries = () => {
    const initialPoints: Array<[number, number]> =
      suggestedYears && suggestedYears.length > 0
        ? suggestedYears.map((y) => [y, 0])
        : [[2025, 0]];
    setDraft((prev) => [
      ...prev,
      {
        id: makeId(),
        name: `Serie manual ${prev.length + 1}`,
        description: "",
        active: true,
        color: pickDefaultColor(prev),
        data: initialPoints,
        lineStyle: "ShortDash",
        markerSymbol: "diamond",
        markerRadius: 5,
        lineWidth: 2,
      },
    ]);
  };

  const removeSeries = (id: string) => {
    setDraft((prev) => prev.filter((s) => s.id !== id));
  };

  const updateSeries = (id: string, patch: Partial<SyntheticSeries>) => {
    setDraft((prev) =>
      prev.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    );
  };

  const addPoint = (id: string) => {
    setDraft((prev) =>
      prev.map((s) => {
        if (s.id !== id) return s;
        const last = s.data.at(-1);
        const nextYear = last ? last[0] + 1 : new Date().getFullYear();
        return { ...s, data: [...s.data, [nextYear, 0]] };
      }),
    );
  };

  const removePoint = (id: string, idx: number) => {
    setDraft((prev) =>
      prev.map((s) =>
        s.id === id ? { ...s, data: s.data.filter((_, i) => i !== idx) } : s,
      ),
    );
  };

  const updatePoint = (
    id: string,
    idx: number,
    field: 0 | 1,
    val: number,
  ) => {
    setDraft((prev) =>
      prev.map((s) => {
        if (s.id !== id) return s;
        const next = s.data.map((p, i) => {
          if (i !== idx) return p;
          const copy: [number, number] = [p[0], p[1]];
          copy[field] = val;
          return copy;
        });
        return { ...s, data: next };
      }),
    );
  };

  /**
   * Handler de paste tipo Excel. Detecta si el texto contiene separadores
   * (tab/newline) y, si sí, hace paste multi-celda expandiendo filas. Si es un
   * único valor sin separadores, deja pasar el paste nativo al input.
   */
  const handlePaste = (
    e: ClipboardEvent<HTMLInputElement>,
    seriesId: string,
    rowIdx: number,
    startCol: 0 | 1,
  ) => {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const grid = parseTabular(text);
    if (grid.length === 0) return;
    setDraft((prev) =>
      prev.map((s) => {
        if (s.id !== seriesId) return s;
        const newData = s.data.map((p) => [...p] as [number, number]);
        for (let i = 0; i < grid.length; i++) {
          const r = rowIdx + i;
          while (newData.length <= r) newData.push([0, 0]);
          const row = grid[i]!;
          for (let j = 0; j < row.length; j++) {
            const col = startCol + j;
            if (col > 1) break;
            const val = parseNumber(row[j]);
            if (Number.isFinite(val)) {
              newData[r]![col as 0 | 1] = val;
            }
          }
        }
        return { ...s, data: newData };
      }),
    );
  };

  /** "Pegar desde portapapeles" — botón útil si el cursor no está en una celda. */
  const handlePasteFromClipboard = async (seriesId: string) => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text) return;
      const grid = parseTabular(text);
      if (grid.length === 0) return;
      setDraft((prev) =>
        prev.map((s) => {
          if (s.id !== seriesId) return s;
          // Reemplaza toda la data si el grid tiene 2 columnas (año + valor).
          // Si solo tiene 1 columna, se asume que son valores y se conservan los años.
          const newData: Array<[number, number]> = [];
          const hasYearCol = grid.some((r) => r.length >= 2);
          for (let i = 0; i < grid.length; i++) {
            const row = grid[i]!;
            if (hasYearCol) {
              const y = parseNumber(row[0]);
              const v = parseNumber(row[1]);
              if (Number.isFinite(y) && Number.isFinite(v)) newData.push([y, v]);
            } else {
              const v = parseNumber(row[0]);
              const existing = s.data[i];
              const year = existing ? existing[0] : new Date().getFullYear() + i;
              if (Number.isFinite(v)) newData.push([year, v]);
            }
          }
          if (newData.length === 0) return s;
          return { ...s, data: newData };
        }),
      );
    } catch (err) {
      console.warn("No se pudo leer portapapeles", err);
    }
  };

  const clearPoints = (id: string) => {
    setDraft((prev) =>
      prev.map((s) => (s.id === id ? { ...s, data: [] } : s)),
    );
  };

  const handleSave = () => {
    const cleaned = draft
      .map((s) => ({
        ...s,
        name: s.name.trim() || "Serie manual",
        data: s.data
          .filter(([y, v]) => Number.isFinite(y) && Number.isFinite(v))
          .slice()
          .sort((a, b) => a[0] - b[0]),
      }))
      .filter((s) => s.data.length > 0);
    onChange(cleaned);
    onClose();
  };

  const totalPoints = useMemo(
    () => draft.reduce((acc, s) => acc + s.data.length, 0),
    [draft],
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Series manuales (overlay)"
      wide
      footer={
        <div className="flex w-full items-center justify-between gap-2">
          <p className="m-0 text-[11px] text-slate-500">
            {draft.length} serie{draft.length === 1 ? "" : "s"} · {totalPoints} punto
            {totalPoints === 1 ? "" : "s"} en total
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={handleSave}>
              Aplicar
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="rounded-md border border-slate-800/70 bg-slate-950/40 p-3 text-xs text-slate-400">
          <p className="m-0">
            <b className="text-slate-300">Paste tipo Excel:</b> copia celdas desde
            Excel / Google Sheets y pégalas directamente en la tabla.
          </p>
          <p className="m-0 mt-1">
            Se aceptan: una celda, una fila (<code>2020&nbsp;→&nbsp;100</code>),
            una columna (<code>100 / 200 / 300</code>) o una matriz
            (<code>año &nbsp;valor</code>). Las filas se expanden automáticamente.
          </p>
          <p className="m-0 mt-1">
            <b className="text-slate-300">Decimales:</b> se aceptan tanto{" "}
            <code>.</code> como <code>,</code>.
            {unitLabel ? (
              <>
                {" "}
                <b className="text-slate-300">Unidad del chart:</b> {unitLabel}.
              </>
            ) : null}
          </p>
        </div>

        {draft.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-700 p-6 text-center text-sm text-slate-500">
            No hay series manuales. Haz clic en "+ Agregar serie" para crear una.
          </div>
        ) : null}

        {draft.map((s) => {
          const isActive = s.active !== false;
          return (
          <div
            key={s.id}
            className={`rounded-lg border p-3 space-y-3 transition-colors ${
              isActive
                ? "border-slate-800 bg-slate-900/40"
                : "border-slate-800/60 bg-slate-900/20 opacity-70"
            }`}
          >
            {/* Fila 1: active + color + nombre + eliminar */}
            <div className="flex flex-wrap items-center gap-2">
              <label
                className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-300 hover:bg-slate-900/80"
                title={isActive ? "Desactivar — no se dibuja" : "Activar — se dibuja en la gráfica"}
              >
                <input
                  type="checkbox"
                  checked={isActive}
                  onChange={(e) => updateSeries(s.id, { active: e.target.checked })}
                  className="h-3.5 w-3.5 cursor-pointer accent-emerald-500"
                />
                <span>{isActive ? "Activa" : "Inactiva"}</span>
              </label>
              <input
                type="color"
                value={s.color}
                onChange={(e) => updateSeries(s.id, { color: e.target.value })}
                className="h-8 w-10 shrink-0 cursor-pointer rounded border border-slate-700 bg-transparent"
                title="Color de la serie"
              />
              <input
                type="text"
                value={s.name}
                onChange={(e) => updateSeries(s.id, { name: e.target.value })}
                maxLength={120}
                className="flex-1 min-w-[140px] rounded border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-sm text-slate-100"
                placeholder="Nombre de la serie"
              />
              <Button
                type="button"
                variant="ghost"
                onClick={() => removeSeries(s.id)}
                className="inline-flex items-center gap-1 rounded-md border border-rose-500/30 px-2 py-1 text-xs text-rose-200 hover:bg-rose-500/10"
                title="Eliminar serie"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden />
                Eliminar
              </Button>
            </div>

            {/* Descripción opcional */}
            <textarea
              value={s.description ?? ""}
              onChange={(e) => updateSeries(s.id, { description: e.target.value })}
              maxLength={1000}
              rows={2}
              placeholder="Descripción / fuente de los datos (opcional). Ej: Estudio XYZ 2024, valores promedio por escenario base."
              className="w-full rounded border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-300 placeholder:text-slate-600"
            />

            {/* Fila 2: estilo de línea / marker / grosor */}
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-1.5 text-xs text-slate-400">
                <span>Línea:</span>
                <select
                  value={s.lineStyle ?? "ShortDash"}
                  onChange={(e) =>
                    updateSeries(s.id, { lineStyle: e.target.value as SyntheticLineStyle })
                  }
                  className="rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100"
                >
                  {LINE_STYLE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex items-center gap-1.5 text-xs text-slate-400">
                <span>Marker:</span>
                <select
                  value={s.markerSymbol ?? "diamond"}
                  onChange={(e) =>
                    updateSeries(s.id, {
                      markerSymbol: e.target.value as SyntheticMarkerSymbol,
                    })
                  }
                  className="rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100"
                >
                  {MARKER_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex items-center gap-1.5 text-xs text-slate-400">
                <span>Tamaño marker:</span>
                <input
                  type="number"
                  min={0}
                  max={20}
                  step={1}
                  value={s.markerRadius ?? 5}
                  disabled={(s.markerSymbol ?? "diamond") === "none"}
                  onChange={(e) =>
                    updateSeries(s.id, { markerRadius: Number(e.target.value) })
                  }
                  className="w-16 rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100 tabular-nums disabled:opacity-50"
                />
              </label>

              <label className="flex items-center gap-1.5 text-xs text-slate-400">
                <span>Grosor línea:</span>
                <input
                  type="number"
                  min={0}
                  max={10}
                  step={0.5}
                  value={s.lineWidth ?? 2}
                  onChange={(e) =>
                    updateSeries(s.id, { lineWidth: Number(e.target.value) })
                  }
                  className="w-16 rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100 tabular-nums"
                />
              </label>
            </div>

            {/* Tabla (año, valor) */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="w-24 py-1 pr-2">Año</th>
                    <th className="py-1 pr-2">
                      Valor {unitLabel ? `(${unitLabel})` : ""}
                    </th>
                    <th className="w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {s.data.map(([y, v], idx) => (
                    <tr key={idx} className="border-t border-slate-800/60">
                      <td className="py-1 pr-2">
                        <input
                          type="number"
                          value={y}
                          onChange={(e) =>
                            updatePoint(s.id, idx, 0, Number(e.target.value))
                          }
                          onPaste={(e) => handlePaste(e, s.id, idx, 0)}
                          className="w-24 rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-sm text-slate-100 tabular-nums"
                        />
                      </td>
                      <td className="py-1 pr-2">
                        <input
                          type="number"
                          step="any"
                          value={v}
                          onChange={(e) =>
                            updatePoint(s.id, idx, 1, Number(e.target.value))
                          }
                          onPaste={(e) => handlePaste(e, s.id, idx, 1)}
                          className="w-full max-w-[220px] rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-sm text-slate-100 tabular-nums"
                        />
                      </td>
                      <td className="py-1">
                        <button
                          type="button"
                          onClick={() => removePoint(s.id, idx)}
                          className="inline-flex h-7 w-7 items-center justify-center rounded text-slate-500 hover:bg-slate-800/60 hover:text-rose-300"
                          title="Eliminar fila"
                        >
                          <X className="h-4 w-4" aria-hidden />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="mt-2 flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => addPoint(s.id)}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800/60"
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden />
                  Agregar fila
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => void handlePasteFromClipboard(s.id)}
                  className="inline-flex items-center gap-1 rounded-md border border-cyan-500/30 bg-cyan-500/5 px-2 py-1 text-xs text-cyan-200 hover:bg-cyan-500/15"
                  title="Pega tabla desde portapapeles (TSV / Excel) — reemplaza puntos"
                >
                  📋 Pegar desde portapapeles
                </Button>
                {s.data.length > 0 ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => clearPoints(s.id)}
                    className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-400 hover:bg-slate-800/60"
                    title="Vacía todos los puntos de esta serie"
                  >
                    Vaciar puntos
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
          );
        })}

        <Button
          type="button"
          variant="ghost"
          onClick={addSeries}
          className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-300 hover:bg-emerald-500/20"
        >
          <Plus className="h-4 w-4" aria-hidden />
          Agregar serie manual
        </Button>
      </div>
    </Modal>
  );
}
