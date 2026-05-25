/**
 * Editor de datos exógenos para Emisiones Contaminantes Criterio.
 *
 * Tres pestañas (una por escenario), cada una con una tabla de
 * años (filas) × contaminantes (columnas).  Los datos se SUMAN a las
 * series existentes en la gráfica.
 *
 * No tiene color picker porque reusa COLORES_EMISIONES.
 */
import { useEffect, useState, useMemo, type ClipboardEvent } from "react";
import { Plus, X } from "lucide-react";
import { Modal } from "@/shared/components/Modal";
import { Button } from "@/shared/components/Button";
import { parseNumber, parseTabular } from "./tabularUtils";
import type { ContaminantesExogenousConfig, ContaminantesScenarioData } from "./contaminantesExogenousTypes";

const POLLUTANT_KEYS = ["BC", "CO", "COVDM", "NOx", "PM10", "PM2_5", "SOx"] as const;
const DEFAULT_YEARS_RANGE: number[] = Array.from(
  { length: 2055 - 2022 + 1 },
  (_, i) => 2022 + i,
);

type ScenarioInfo = {
  jobId: number;
  name: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
  value: ContaminantesExogenousConfig | null;
  onChange: (next: ContaminantesExogenousConfig | null) => void;
  /** Escenarios comparados. */
  scenarios: ScenarioInfo[];
  unitLabel?: string | undefined;
  suggestedYears?: number[] | undefined;
};

type Row = {
  year: number;
  values: Record<string, number>;
};

// ── helpers ──────────────────────────────────────────────────────────────

function buildEmptyRow(year: number): Row {
  return {
    year,
    values: Object.fromEntries(POLLUTANT_KEYS.map((k) => [k, 0])),
  };
}

function configToRows(
  config: ContaminantesExogenousConfig | null,
  scenarioIdx: number,
): Row[] {
  if (!config || !config.active) return [];
  const sc = config.scenarios[scenarioIdx];
  if (!sc) return [];
  const yearsSet = new Set<number>();
  for (const pairs of Object.values(sc.data)) {
    for (const [y] of pairs) yearsSet.add(y);
  }
  const years = Array.from(yearsSet).sort((a, b) => a - b);
  if (years.length === 0) return [];
  return years.map((year) => {
    const values: Record<string, number> = {};
    for (const key of POLLUTANT_KEYS) {
      const pairs = sc.data[key];
      if (!pairs) {
        values[key] = 0;
        continue;
      }
      const found = pairs.find(([y]) => y === year);
      values[key] = found != null ? found[1] : 0;
    }
    return { year, values };
  });
}

function rowsToData(rows: Row[]): Record<string, Array<[number, number]>> {
  const data: Record<string, Array<[number, number]>> = {};
  for (const key of POLLUTANT_KEYS) {
    const pairs: Array<[number, number]> = [];
    for (const row of rows) {
      const val = row.values[key] as number;
      if (Number.isFinite(row.year) && Number.isFinite(val) && val !== 0) {
        pairs.push([row.year, val]);
      }
    }
    if (pairs.length > 0) data[key] = pairs;
  }
  return data;
}

// ── Component ────────────────────────────────────────────────────────────

export function ContaminantesExogenousEditor({
  open,
  onClose,
  value,
  onChange,
  scenarios,
  unitLabel,
}: Props) {
  const [activeTab, setActiveTab] = useState(0);
  const [draftRows, setDraftRows] = useState<Row[][]>(() =>
    scenarios.map((_, i) => configToRows(value, i)),
  );
  const [isActive, setIsActive] = useState(value?.active ?? true);
  const [pasteTarget, setPasteTarget] = useState<{
    tabIdx: number;
    rowIdx: number;
    colKey: string;
  } | null>(null);

  useEffect(() => {
    if (open) {
      setDraftRows(scenarios.map((_, i) => configToRows(value, i)));
      setIsActive(value?.active ?? true);
      setActiveTab(0);
      setPasteTarget(null);
    }
  }, [open, value, scenarios]);

  const currentRows = draftRows[activeTab] ?? [];

  const setCurrentRows = (fn: (prev: Row[]) => Row[]) => {
    setDraftRows((prev) => {
      const next = prev.map((tab) => [...tab]);
      next[activeTab] = fn(next[activeTab] ?? []);
      return next;
    });
  };

  // ── row mutations ──────────────────────────────────────────────────────

  const addRow = () => {
    setCurrentRows((prev) => {
      const last = prev.at(-1);
      const nextYear = last ? last.year + 1 : 2022;
      return [...prev, buildEmptyRow(nextYear)];
    });
  };

  const removeRow = (rowIdx: number) => {
    setCurrentRows((prev) => prev.filter((_, i) => i !== rowIdx));
  };

  const updateYear = (rowIdx: number, year: number) => {
    setCurrentRows((prev) =>
      prev.map((r, i) => (i === rowIdx ? { ...r, year } : r)),
    );
  };

  const updateValue = (rowIdx: number, colKey: string, val: number) => {
    setCurrentRows((prev) =>
      prev.map((r, i) =>
        i === rowIdx
          ? { ...r, values: { ...r.values, [colKey]: val } }
          : r,
      ),
    );
  };

  // ── paste ──────────────────────────────────────────────────────────────

  const handlePasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text) return;
      const grid = parseTabular(text);
      if (grid.length === 0) return;

      // Detectar si la primera fila es encabezado
      let startRow = 0;
      const firstCell = parseNumber(grid[0]?.[0]);
      if (!Number.isFinite(firstCell)) {
        startRow = 1;
      }

      // Mapear columnas: first row headers → pollutant keys
      const headerRow = startRow > 0 ? grid[0] : null;
      const colMap: number[] = []; // colMap[gridIdx] = pollutantIdx or -1
      if (headerRow) {
        for (let gi = 1; gi < headerRow.length; gi++) {
          const h = String(headerRow[gi]).trim().toLowerCase();
          const found = POLLUTANT_KEYS.findIndex(
            (pk) => pk.toLowerCase() === h,
          );
          colMap.push(found);
        }
      } else {
        // No header: assume columns 1..N map to POLLUTANT_KEYS 0..N-1
        for (let gi = 1; gi < POLLUTANT_KEYS.length + 1; gi++) {
          colMap.push(gi - 1);
        }
      }

      const newRows: Row[] = [];
      for (let i = startRow; i < grid.length; i++) {
        const row = grid[i]!;
        const year = parseNumber(row[0]);
        if (!Number.isFinite(year)) continue;
        const values: Record<string, number> = {} as Record<string, number>;
        let hasValue = false;
        for (let gi = 0; gi < colMap.length; gi++) {
          const pi = colMap[gi]!;
          if (pi < 0 || pi >= POLLUTANT_KEYS.length) continue;
          const raw = row[gi + 1];
          const v = parseNumber(raw);
          const key = POLLUTANT_KEYS[pi]!;
          values[key] = Number.isFinite(v) ? v : 0;
          if (Number.isFinite(v) && v !== 0) hasValue = true;
        }
        if (hasValue) {
          newRows.push({ year, values });
        }
      }

      if (newRows.length > 0) {
        setCurrentRows(() => newRows);
      }
    } catch (err) {
      console.warn("No se pudo leer portapapeles", err);
    }
  };

  const handleCellPaste = (
    e: ClipboardEvent<HTMLInputElement>,
    rowIdx: number,
    colKey: string,
  ) => {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const grid = parseTabular(text);
    if (grid.length === 0) return;
    setDraftRows((prev) => {
      const next = prev.map((tab) => tab.map((r) => ({ ...r, values: { ...r.values } })));
      const target = next[activeTab] ?? [];
      for (let i = 0; i < grid.length; i++) {
        const r = rowIdx + i;
        while (target.length <= r) {
          target.push(buildEmptyRow((target.at(-1)?.year ?? 2021) + 1));
        }
        const gridRow = grid[i]!;
        // cell 0 = year, rest = pollutant values in order
        const year = parseNumber(gridRow[0]);
        if (Number.isFinite(year)) {
          target[r]!.year = year;
        }
        const colIdx = POLLUTANT_KEYS.indexOf(colKey as typeof POLLUTANT_KEYS[number]);
        for (let j = 0; j < gridRow.length - 1; j++) {
          const pi = colIdx + j;
          if (pi < 0 || pi >= POLLUTANT_KEYS.length) break;
          const v = parseNumber(gridRow[j + 1]!);
          if (Number.isFinite(v)) {
            target[r]!.values[POLLUTANT_KEYS[pi]!] = v;
          }
        }
      }
      next[activeTab] = target;
      return next;
    });
  };

  const clearTab = () => {
    setCurrentRows(() => []);
  };

  const clearAllTabs = () => {
    setDraftRows(scenarios.map(() => []));
  };

  // ── save ───────────────────────────────────────────────────────────────

  const handleSave = () => {
    const scenarioData: ContaminantesScenarioData[] = scenarios.map((s, si) => {
      const rows = draftRows[si] ?? [];
      const data = rowsToData(rows);
      return { jobId: s.jobId, scenarioName: s.name, data };
    });

    const hasAnyData = scenarioData.some(
      (sd) => Object.keys(sd.data).length > 0,
    );

    if (!hasAnyData) {
      onChange(null);
      onClose();
      return;
    }

    onChange({ active: isActive, scenarios: scenarioData });
    onClose();
  };

  // ── stats ──────────────────────────────────────────────────────────────

  const totalPoints = useMemo(() => {
    let n = 0;
    for (const tab of draftRows) {
      for (const row of tab) {
        for (const key of POLLUTANT_KEYS) {
          if (row.values[key] !== 0) n++;
        }
      }
    }
    return n;
  }, [draftRows]);

  // ── render ─────────────────────────────────────────────────────────────

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Datos exógenos — Contaminantes Criterio"
      wide
      footer={
        <div className="flex w-full items-center justify-between gap-2">
          <p className="m-0 text-[11px] text-slate-500">
            {scenarios.length} escenario{scenarios.length === 1 ? "" : "s"} ·{" "}
            {totalPoints} valor{totalPoints === 1 ? "" : "es"}
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
            <b className="text-slate-300">Paste tipo Excel:</b> copia los datos
            desde Excel / Google Sheets y p&eacute;galos usando el bot&oacute;n
            &ldquo;Pegar desde portapapeles&rdquo;.
          </p>
          <p className="m-0 mt-1">
            Formato esperado:{" "}
            <code>
              A&ntilde;o [TAB] BC [TAB] CO [TAB] COVDM [TAB] NOx [TAB] PM10
              [TAB] PM2_5 [TAB] SOx
            </code>
            . La primera fila puede ser encabezado (se omite autom&aacute;ticamente).
          </p>
          <p className="m-0 mt-1">
            <b className="text-slate-300">Comportamiento:</b> los valores se{" "}
            <b>suman</b> a los resultados simulados de cada contaminante.
            {unitLabel ? (
              <>
                {" "}
                <b className="text-slate-300">Unidad:</b> {unitLabel}.
              </>
            ) : null}
          </p>
        </div>

        {/* Controles globales */}
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
        </div>

        {/* Tabs por escenario */}
        <div className="flex gap-1 border-b border-slate-700/60 pb-2">
          {scenarios.map((s, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setActiveTab(i)}
              className={`rounded-t px-3 py-1.5 text-xs font-medium transition-colors ${
                activeTab === i
                  ? "border-b-2 border-emerald-500 bg-slate-800/60 text-slate-100"
                  : "text-slate-500 hover:bg-slate-800/30 hover:text-slate-300"
              }`}
            >
              {s.name}
            </button>
          ))}
        </div>

        {/* Tabla del escenario activo */}
        {currentRows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-700 p-6 text-center text-sm text-slate-500">
            Sin datos para este escenario. Pega desde Excel o agrega filas manualmente.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="w-20 py-1 pr-2">A&ntilde;o</th>
                  {POLLUTANT_KEYS.map((key) => (
                    <th key={key} className="py-1 pr-2">
                      {key}
                    </th>
                  ))}
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {currentRows.map((row, rowIdx) => (
                  <tr key={rowIdx} className="border-t border-slate-800/60">
                    <td className="py-1 pr-2">
                      <input
                        type="number"
                        value={row.year}
                        onChange={(e) => updateYear(rowIdx, Number(e.target.value))}
                        onPaste={(e) => handleCellPaste(e, rowIdx, "BC")}
                        className="w-20 rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-sm text-slate-100 tabular-nums"
                      />
                    </td>
                    {POLLUTANT_KEYS.map((key) => (
                      <td key={key} className="py-1 pr-2">
                        <input
                          type="number"
                          step="any"
                          value={row.values[key]}
                          onChange={(e) =>
                            updateValue(rowIdx, key, Number(e.target.value))
                          }
                          onPaste={(e) => handleCellPaste(e, rowIdx, key)}
                          className="w-full min-w-[80px] rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-sm text-slate-100 tabular-nums"
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
            title="Pega tabla desde portapapeles (TSV / Excel) — reemplaza datos del escenario activo"
          >
            📋 Pegar desde portapapeles
          </Button>
          {currentRows.length > 0 ? (
            <Button
              type="button"
              variant="ghost"
              onClick={clearTab}
              className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-400 hover:bg-slate-800/60"
              title="Vacía los datos del escenario activo"
            >
              Vaciar escenario
            </Button>
          ) : null}
          {draftRows.some((tab) => tab.length > 0) ? (
            <Button
              type="button"
              variant="ghost"
              onClick={clearAllTabs}
              className="inline-flex items-center gap-1 rounded-md border border-rose-700/40 px-2 py-1 text-xs text-rose-300 hover:bg-rose-900/20"
              title="Vacía todos los escenarios"
            >
              Vaciar todo
            </Button>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
