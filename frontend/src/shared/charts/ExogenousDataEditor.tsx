/**
 * Editor de datos exógenos para gráficas de emisiones.
 *
 * Permite ingresar valores por año y por escenario (una columna por escenario).
 * Los datos se muestran como una nueva categoría "Refinerías" en la gráfica
 * (para facet/by-year/by-year-alt) o se suman a la línea del escenario (line-total).
 *
 * Reutiliza parseTabular/parseNumber de tabularUtils para paste tipo Excel.
 */
import { useEffect, useState, useMemo, type ClipboardEvent } from "react";
import { Plus, X } from "lucide-react";
import { Modal } from "@/shared/components/Modal";
import { Button } from "@/shared/components/Button";
import { parseNumber, parseTabular } from "./tabularUtils";
import type { ExogenousDataConfig } from "@/types/domain";

const DEFAULT_COLOR = "#27ae60";
const DEFAULT_CATEGORY_LABEL = "Refinerías";
const DEFAULT_YEARS_RANGE: number[] = Array.from(
  { length: 2054 - 2022 + 1 },
  (_, i) => 2022 + i,
);

type ScenarioInfo = {
  jobId: number;
  name: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
  value: ExogenousDataConfig | null;
  onChange: (next: ExogenousDataConfig | null) => void;
  /** Escenarios comparados. */
  scenarios: ScenarioInfo[];
  unitLabel?: string | undefined;
  suggestedYears?: number[] | undefined;
};

/** Fila del editor: año + un valor por escenario. */
type Row = {
  year: number;
  values: number[];
};

function buildInitialRows(
  scenarios: ScenarioInfo[],
  suggestedYears?: number[],
): Row[] {
  const years =
    suggestedYears && suggestedYears.length > 0
      ? suggestedYears
      : DEFAULT_YEARS_RANGE;
  return years.map((year) => ({
    year,
    values: scenarios.map(() => 0),
  }));
}

function rowsToConfig(
  rows: Row[],
  scenarios: ScenarioInfo[],
  active: boolean,
  color: string,
  label: string,
): ExogenousDataConfig {
  const validRows = rows.filter(
    (r) => Number.isFinite(r.year) && r.values.some((v) => Number.isFinite(v)),
  );
  if (validRows.length === 0) {
    return {
      active: false,
      categoryLabel: label,
      color,
      scenarios: scenarios.map((s) => ({ jobId: s.jobId, scenarioName: s.name, data: [] })),
    };
  }
  return {
    active,
    categoryLabel: label,
    color,
    scenarios: scenarios.map((s, si) => ({
      jobId: s.jobId,
      scenarioName: s.name,
      data: validRows
        .map((r) => [r.year, r.values[si]] as [number, number])
        .filter(([, v]) => Number.isFinite(v)),
    })),
  };
}

function configToRows(
  config: ExogenousDataConfig | null,
  scenarios: ScenarioInfo[],
): Row[] {
  if (!config || !config.active) return buildInitialRows(scenarios);
  const yearsSet = new Set<number>();
  for (const sc of config.scenarios) {
    for (const [y] of sc.data) yearsSet.add(y);
  }
  const years = Array.from(yearsSet).sort((a, b) => a - b);
  if (years.length === 0) return buildInitialRows(scenarios);

  const dataMap: Map<number, (number | null)[]> = new Map();
  for (const y of years) {
    dataMap.set(y, scenarios.map(() => null));
  }
  for (let si = 0; si < config.scenarios.length; si++) {
    const sc = config.scenarios[si];
    if (!sc) continue;
    for (const [y, v] of sc.data) {
      const vals = dataMap.get(y);
      if (vals) vals[si] = v;
    }
  }
  return years.map((year, _yi) => ({
    year,
    values: scenarios.map((_, si) => {
      const v = dataMap.get(year)?.[si];
      return v != null ? v : 0;
    }),
  }));
}

export function ExogenousDataEditor({
  open,
  onClose,
  value,
  onChange,
  scenarios,
  unitLabel,
  suggestedYears,
}: Props) {
  const [draftRows, setDraftRows] = useState<Row[]>(() =>
    configToRows(value, scenarios),
  );
  const [isActive, setIsActive] = useState(value?.active ?? true);
  const [color, setColor] = useState(value?.color ?? DEFAULT_COLOR);

  useEffect(() => {
    if (open) {
      setDraftRows(configToRows(value, scenarios));
      setIsActive(value?.active ?? true);
      setColor(value?.color ?? DEFAULT_COLOR);
    }
  }, [open, value, scenarios]);

  const addRow = () => {
    setDraftRows((prev) => {
      const last = prev.at(-1);
      const nextYear = last ? last.year + 1 : new Date().getFullYear();
      return [...prev, { year: nextYear, values: scenarios.map(() => 0) }];
    });
  };

  const removeRow = (idx: number) => {
    setDraftRows((prev) => prev.filter((_, i) => i !== idx));
  };

  const updateYear = (idx: number, year: number) => {
    setDraftRows((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, year } : r)),
    );
  };

  const updateValue = (rowIdx: number, colIdx: number, val: number) => {
    setDraftRows((prev) =>
      prev.map((r, i) => {
        if (i !== rowIdx) return r;
        const next = [...r.values];
        next[colIdx] = val;
        return { ...r, values: next };
      }),
    );
  };

  const handlePaste = (
    e: ClipboardEvent<HTMLInputElement>,
    rowIdx: number,
    colIdx: number,
  ) => {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const grid = parseTabular(text);
    if (grid.length === 0) return;
    setDraftRows((prev) => {
      const next = prev.map((r) => ({ ...r, values: [...r.values] }));
      for (let i = 0; i < grid.length; i++) {
        const r = rowIdx + i;
        while (next.length <= r) {
          next.push({ year: 0, values: scenarios.map(() => 0) });
        }
        const row = grid[i]!;
        for (let j = 0; j < row.length; j++) {
          const c = colIdx + j;
          if (c > scenarios.length) break;
          const v = parseNumber(row[j]);
          if (Number.isFinite(v)) {
            if (c === 0) {
              next[r]!.year = v;
            } else {
              next[r]!.values[c - 1] = v;
            }
          }
        }
      }
      return next;
    });
  };

  const handlePasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text) return;
      const grid = parseTabular(text);
      if (grid.length === 0) return;

      // Detectar si la primera fila es encabezado (año no numérico)
      let startRow = 0;
      const firstCell = parseNumber(grid[0]?.[0]);
      if (!Number.isFinite(firstCell)) {
        startRow = 1;
      }

      const newRows: Row[] = [];
      for (let i = startRow; i < grid.length; i++) {
        const row = grid[i]!;
        const year = parseNumber(row[0]);
        if (!Number.isFinite(year)) continue;
        const values = scenarios.map((_, si) => {
          const v = parseNumber(row[si + 1]);
          return Number.isFinite(v) ? v : 0;
        });
        if (values.some((v) => v !== 0)) {
          newRows.push({ year, values });
        }
      }

      if (newRows.length > 0) {
        setDraftRows(newRows);
      }
    } catch (err) {
      console.warn("No se pudo leer portapapeles", err);
    }
  };

  const clearAll = () => {
    setDraftRows(buildInitialRows(scenarios, suggestedYears));
  };

  const handleSave = () => {
    const cleaned = draftRows
      .filter((r) => Number.isFinite(r.year))
      .map((r) => ({
        ...r,
        values: r.values.map((v) => (Number.isFinite(v) ? v : 0)),
      }))
      .sort((a, b) => a.year - b.year);

    if (cleaned.length === 0 || cleaned.every((r) => r.values.every((v) => v === 0))) {
      onChange(null);
      onClose();
      return;
    }

    const config = rowsToConfig(cleaned, scenarios, isActive, color, DEFAULT_CATEGORY_LABEL);
    onChange(config);
    onClose();
  };

  const totalPoints = useMemo(
    () => draftRows.length * scenarios.length,
    [draftRows.length, scenarios.length],
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Datos exógenos — Refinerías"
      wide
      footer={
        <div className="flex w-full items-center justify-between gap-2">
          <p className="m-0 text-[11px] text-slate-500">
            {draftRows.length} año{draftRows.length === 1 ? "" : "s"} · {scenarios.length} escenario
            {scenarios.length === 1 ? "" : "s"} · {totalPoints} valor{totalPoints === 1 ? "" : "es"}
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
            <b className="text-slate-300">Paste tipo Excel:</b> copia los datos desde
            Excel / Google Sheets y p&eacute;galos usando el bot&oacute;n &ldquo;Pegar desde portapapeles&rdquo;.
          </p>
          <p className="m-0 mt-1">
            Formato esperado: <code>A&ntilde;o [TAB] Esc1 [TAB] Esc2 [TAB] Esc3</code>.
            La primera fila puede ser encabezado (se omite autom&aacute;ticamente).
          </p>
          <p className="m-0 mt-1">
            <b className="text-slate-300">Decimales:</b> se aceptan tanto{" "}
            <code>.</code> como <code>,</code>.
            {unitLabel ? (
              <>
                {" "}
                <b className="text-slate-300">Unidad:</b> {unitLabel}.
              </>
            ) : null}
          </p>
        </div>

        {/* Fila de controles globales */}
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-300 hover:bg-slate-900/80">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="h-3.5 w-3.5 cursor-pointer accent-emerald-500"
            />
            <span>{isActive ? "Activo" : "Inactivo"}</span>
          </label>
          <label className="flex items-center gap-1.5 text-xs text-slate-400">
            <span>Color:</span>
            <input
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              className="h-8 w-10 shrink-0 cursor-pointer rounded border border-slate-700 bg-transparent"
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-slate-400">
            <span>Categoría:</span>
            <span className="rounded bg-slate-800 px-2 py-1 text-sm font-semibold text-slate-200">
              {DEFAULT_CATEGORY_LABEL}
            </span>
          </label>
        </div>

        {draftRows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-700 p-6 text-center text-sm text-slate-500">
            Sin datos. Pega desde Excel o agrega filas manualmente.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="w-24 py-1 pr-2">Año</th>
                  {scenarios.map((s, i) => (
                    <th key={i} className="py-1 pr-2">
                      {s.name} {unitLabel ? `(${unitLabel})` : ""}
                    </th>
                  ))}
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {draftRows.map((row, rowIdx) => (
                  <tr key={rowIdx} className="border-t border-slate-800/60">
                    <td className="py-1 pr-2">
                      <input
                        type="number"
                        value={row.year}
                        onChange={(e) => updateYear(rowIdx, Number(e.target.value))}
                        onPaste={(e) => handlePaste(e, rowIdx, 0)}
                        className="w-24 rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-sm text-slate-100 tabular-nums"
                      />
                    </td>
                    {row.values.map((val, colIdx) => (
                      <td key={colIdx} className="py-1 pr-2">
                        <input
                          type="number"
                          step="any"
                          value={val}
                          onChange={(e) =>
                            updateValue(rowIdx, colIdx, Number(e.target.value))
                          }
                          onPaste={(e) => handlePaste(e, rowIdx, colIdx + 1)}
                          className="w-full max-w-[200px] rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-sm text-slate-100 tabular-nums"
                        />
                      </td>
                    ))}
                    <td className="py-1">
                      <button
                        type="button"
                        onClick={() => removeRow(rowIdx)}
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
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={addRow}
            className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800/60"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden />
            Agregar fila
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => void handlePasteFromClipboard()}
            className="inline-flex items-center gap-1 rounded-md border border-cyan-500/30 bg-cyan-500/5 px-2 py-1 text-xs text-cyan-200 hover:bg-cyan-500/15"
            title="Pega tabla desde portapapeles (TSV / Excel) — reemplaza datos"
          >
            📋 Pegar desde portapapeles
          </Button>
          {draftRows.length > 0 ? (
            <Button
              type="button"
              variant="ghost"
              onClick={clearAll}
              className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-400 hover:bg-slate-800/60"
              title="Vacía todos los datos"
            >
              Vaciar datos
            </Button>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
