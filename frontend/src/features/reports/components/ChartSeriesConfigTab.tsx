import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { chartSeriesConfigApi } from '@/features/reports/api/chartSeriesConfigApi';
import { resultTableTemplatesApi } from '@/features/reports/api/resultTableTemplatesApi';
import { Button } from '@/shared/components/Button';
import { isApiError } from '@/shared/errors/ApiError';
import type { ChartSeriesConfigPublic, ChartTypeInfo } from '@/types/domain';

const AGRUP_EXTRA = [
  'TECNOLOGIA',
  'FUEL',
  'GROUP',
  'SECTOR',
  'EMISION',
  'REGION',
  'H2_PRODUCCION',
  'TRANSPORTE_GRUPO',
  'YEAR',
];

export type ChartSeriesConfigTabProps = {
  /** Si viene definido, fija el selector de tipo y oculta el bloque superior. */
  fixedTipo?: string | null;
  fixedAgruparPor?: string | null;
  /** Variable OSeMOSYS del chart (p. ej. capacidad); alinea sugerencias de códigos con el backend. */
  presentationVariable?: string | null;
  /** Tras guardar cambios, p.ej. recargar la gráfica de resultados. */
  onApplied?: () => void;
};

export function ChartSeriesConfigTab({
  fixedTipo,
  fixedAgruparPor,
  presentationVariable = null,
  onApplied,
}: ChartSeriesConfigTabProps) {
  const [chartTypes, setChartTypes] = useState<ChartTypeInfo[]>([]);
  const [tipo, setTipo] = useState('');
  const [agrupar, setAgrupar] = useState('TECNOLOGIA');
  const [rows, setRows] = useState<ChartSeriesConfigPublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [addCode, setAddCode] = useState('');
  const [addName, setAddName] = useState('');
  const [addColor, setAddColor] = useState('#999999');
  const [addGroup, setAddGroup] = useState('');
  const [addSaving, setAddSaving] = useState(false);
  const [codeCatalog, setCodeCatalog] = useState<{ code: string; label: string }[]>([]);
  const [codeCatalogLoading, setCodeCatalogLoading] = useState(false);
  const [codeMenuOpen, setCodeMenuOpen] = useState(false);

  const effectiveTipo = (fixedTipo ?? tipo).trim();
  const effectiveAgrupar = (fixedAgruparPor ?? agrupar).trim().toUpperCase();

  const addCodeFilter = addCode.trim().toLowerCase();
  const filteredCatalog = useMemo(() => {
    if (!codeCatalog.length) return [];
    if (!addCodeFilter) return codeCatalog.slice(0, 45);
    return codeCatalog
      .filter(
        (x) =>
          x.code.toLowerCase().includes(addCodeFilter) ||
          x.label.toLowerCase().includes(addCodeFilter),
      )
      .slice(0, 60);
  }, [codeCatalog, addCodeFilter]);

  const loadTypes = useCallback(() => {
    return chartSeriesConfigApi.listChartTypes().then(setChartTypes).catch(() => {
      setChartTypes([]);
    });
  }, []);

  const loadRows = useCallback(() => {
    if (!effectiveTipo || !effectiveAgrupar) return Promise.resolve();
    setLoading(true);
    setError(null);
    setStatusMessage(null);
    return chartSeriesConfigApi
      .list(effectiveTipo, effectiveAgrupar)
      .then(async (list) => {
        if (list.length === 0) {
          setStatusMessage('Poblando series desde el catálogo…');
          try {
            const populated = await chartSeriesConfigApi.populate({
              tipo: effectiveTipo,
              agrupar_por: effectiveAgrupar,
              variable: presentationVariable,
            });
            setRows(populated);
            onApplied?.();
          } catch (e) {
            setError(e instanceof Error ? e.message : 'Error en población automática.');
            setRows([]);
          } finally {
            setStatusMessage(null);
          }
        } else {
          setRows(list);
        }
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Error cargando series.');
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [effectiveTipo, effectiveAgrupar, presentationVariable, onApplied]);

  useEffect(() => {
    void loadTypes();
  }, [loadTypes]);

  useEffect(() => {
    if (chartTypes.length && !fixedTipo && !tipo) {
      setTipo(chartTypes[0]!.tipo);
      setAgrupar(chartTypes[0]!.agrupar_por_default);
    }
  }, [chartTypes, fixedTipo, tipo]);

  useEffect(() => {
    if (!effectiveTipo || !effectiveAgrupar) {
      setCodeCatalog([]);
      return;
    }
    let cancelled = false;
    setCodeCatalogLoading(true);
    void resultTableTemplatesApi
      .getPresentationOptions({
        tipo: effectiveTipo,
        agrupar_por: effectiveAgrupar,
        variable: presentationVariable ?? null,
      })
      .then((d) => {
        if (cancelled) return;
        const seen = new Set<string>();
        const uniq: { code: string; label: string }[] = [];
        for (const o of d.series_options ?? []) {
          const label = (o.value ?? '').trim();
          const code = (o.code?.trim() || label).trim();
          if (!code || seen.has(code)) continue;
          seen.add(code);
          uniq.push({ code, label: label || code });
        }
        uniq.sort((a, b) => a.code.localeCompare(b.code));
        setCodeCatalog(uniq);
      })
      .catch(() => {
        if (!cancelled) setCodeCatalog([]);
      })
      .finally(() => {
        if (!cancelled) setCodeCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [effectiveTipo, effectiveAgrupar, presentationVariable]);

  useEffect(() => {
    void loadRows();
  }, [loadRows]);

  const submitManualAdd = async () => {
    if (!effectiveTipo || !effectiveAgrupar) return;
    const code = addCode.trim();
    if (!code) {
      setError('El código de serie es obligatorio (debe coincidir con el dato de la simulación, ej. PWRCOA).');
      return;
    }
    setAddSaving(true);
    setError(null);
    try {
      await chartSeriesConfigApi.createRow({
        tipo: effectiveTipo,
        agrupar_por: effectiveAgrupar,
        series_code: code,
        display_name: addName.trim() || null,
        color: addColor.trim() && /^#[0-9a-fA-F]{6}$/.test(addColor.trim()) ? addColor.trim() : null,
        group_key: addGroup.trim() || null,
      });
      setAddCode('');
      setAddName('');
      setAddGroup('');
      setAddColor('#999999');
      await loadRows();
      onApplied?.();
    } catch (e) {
      setError(
        isApiError(e) ? e.message : e instanceof Error ? e.message : 'No se pudo crear la fila.',
      );
    } finally {
      setAddSaving(false);
    }
  };

  const populate = async () => {
    if (!effectiveTipo) return;
    setError(null);
    try {
      const list = await chartSeriesConfigApi.populate({
        tipo: effectiveTipo,
        agrupar_por: effectiveAgrupar,
        variable: presentationVariable,
      });
      setRows(list);
      onApplied?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error en población.');
    }
  };

  const populateAll = async () => {
    if (!window.confirm('Poblar series para todos los tipos de gráfica? Puede tardar.')) return;
    setError(null);
    try {
      const r = await chartSeriesConfigApi.populateAll();
      alert(`Filas nuevas insertadas (aprox.): ${r.inserted_rows}`);
      await loadRows();
      onApplied?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error en población masiva.');
    }
  };

  const move = async (idx: number, delta: number) => {
    const j = idx + delta;
    if (j < 0 || j >= rows.length) return;
    const ids = rows.map((r) => r.id);
    const t = ids[idx]!;
    ids[idx] = ids[j]!;
    ids[j] = t;
    try {
      const next = await chartSeriesConfigApi.reorder(ids);
      setRows(next);
      onApplied?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error reordenando.');
    }
  };

  const patchRow = async (id: number, payload: Parameters<typeof chartSeriesConfigApi.patch>[1]) => {
    setSavingId(id);
    setError(null);
    try {
      const updated = await chartSeriesConfigApi.patch(id, payload);
      setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
      onApplied?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error guardando.');
    } finally {
      setSavingId(null);
    }
  };

  const removeRow = async (id: number) => {
    if (!window.confirm('¿Eliminar esta serie de la configuración?')) return;
    try {
      await chartSeriesConfigApi.delete(id);
      setRows((prev) => prev.filter((r) => r.id !== id));
      onApplied?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error eliminando.');
    }
  };

  return (
    <div className="space-y-4">
      <p className="m-0 text-sm text-slate-500 max-w-3xl">
        Configuración global de series (nombre, color, orden, visibilidad) por tipo de gráfica y
        agrupación. Los cambios se aplican en el backend al servir chart-data (gráficas, tablas y
        exportaciones).
      </p>

      {!fixedTipo ? (
        <div className="flex flex-wrap gap-3 items-end">
          <label className="block text-xs text-slate-400">
            Tipo de gráfica
            <select
              className="mt-1 block w-72 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
              value={tipo}
              onChange={(e) => {
                const v = e.target.value;
                setTipo(v);
                const info = chartTypes.find((x) => x.tipo === v);
                if (info) setAgrupar(info.agrupar_por_default);
              }}
            >
              {chartTypes.map((c) => (
                <option key={`${c.tipo}-${c.source}`} value={c.tipo}>
                  {c.tipo} ({c.source})
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs text-slate-400">
            Agrupación (COLOR)
            <input
              list="agrup-datalist"
              className="mt-1 block w-52 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white font-mono"
              value={agrupar}
              onChange={(e) => setAgrupar(e.target.value.toUpperCase())}
            />
            <datalist id="agrup-datalist">
              {AGRUP_EXTRA.map((a) => (
                <option key={a} value={a} />
              ))}
            </datalist>
          </label>
        </div>
      ) : (
        <p className="m-0 text-xs text-slate-500 font-mono">
          {effectiveTipo} · {effectiveAgrupar}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="ghost" onClick={() => void populate()}>
          Poblar desde catálogo
        </Button>
        {!fixedTipo ? (
          <Button type="button" variant="ghost" onClick={() => void populateAll()}>
            Poblar todos los tipos
          </Button>
        ) : null}
        <Button type="button" variant="ghost" onClick={() => void loadRows()}>
          Recargar
        </Button>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4 space-y-3">
        <p className="m-0 text-xs font-semibold text-slate-300">Agregar serie manualmente</p>
        <p className="m-0 text-[11px] text-slate-500 max-w-3xl">
          Si la simulación ya devuelve una serie pero no apareció al poblar, crea la fila aquí. El{' '}
          <strong>código</strong> debe coincidir con el identificador en los datos. Escribe para filtrar
          sugerencias del catálogo; si no aparece, puedes pegar el código a mano (CSV / explorador).
        </p>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="relative text-xs text-slate-400">
            <span className="block">Código *</span>
            <input
              className="mt-1 block w-72 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white font-mono"
              value={addCode}
              onChange={(e) => {
                setAddCode(e.target.value);
                setCodeMenuOpen(true);
              }}
              onFocus={() => setCodeMenuOpen(true)}
              onBlur={() => {
                window.setTimeout(() => setCodeMenuOpen(false), 200);
              }}
              placeholder="Filtra o pega código (ej. PWRCOA)"
              disabled={addSaving || !effectiveTipo}
              autoComplete="off"
              aria-autocomplete="list"
              aria-expanded={codeMenuOpen}
            />
            {codeMenuOpen && effectiveTipo && effectiveAgrupar ? (
              <ul
                role="listbox"
                className="absolute z-[120] mt-0.5 max-h-56 w-72 overflow-auto rounded-lg border border-slate-600 bg-slate-900 py-1 shadow-xl"
              >
                {codeCatalogLoading ? (
                  <li className="px-3 py-2 text-slate-500">Cargando sugerencias…</li>
                ) : filteredCatalog.length > 0 ? (
                  filteredCatalog.map((x) => (
                    <li key={x.code} role="option">
                      <button
                        type="button"
                        className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left hover:bg-slate-800/90"
                        onMouseDown={(e) => {
                          e.preventDefault();
                          setAddCode(x.code);
                          setAddName((prev) => (prev.trim() ? prev : x.label));
                          setCodeMenuOpen(false);
                        }}
                      >
                        <span className="font-mono text-[13px] text-cyan-200/95">{x.code}</span>
                        <span className="text-[11px] text-slate-400">{x.label}</span>
                      </button>
                    </li>
                  ))
                ) : codeCatalog.length > 0 ? (
                  <li className="px-3 py-2 text-slate-500">Sin coincidencias — escribe el código a mano.</li>
                ) : (
                  <li className="px-3 py-2 text-slate-500">
                    Sin lista de sugerencias para este tipo/agrupación. Usa el código exacto de tus
                    resultados.
                  </li>
                )}
              </ul>
            ) : null}
          </div>
          <label className="block text-xs text-slate-400">
            Nombre visible (opcional)
            <input
              className="mt-1 block w-48 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
              value={addName}
              onChange={(e) => setAddName(e.target.value)}
              placeholder="Si vacío, se usa la etiqueta por defecto"
              disabled={addSaving}
            />
          </label>
          <label className="block text-xs text-slate-400">
            Color
            <input
              type="color"
              className="mt-1 block h-9 w-14 cursor-pointer rounded border border-slate-700 bg-transparent"
              value={addColor}
              onChange={(e) => setAddColor(e.target.value)}
              disabled={addSaving}
            />
          </label>
          <label className="block text-xs text-slate-400">
            Grupo (opcional)
            <input
              className="mt-1 block w-36 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
              value={addGroup}
              onChange={(e) => setAddGroup(e.target.value)}
              disabled={addSaving}
            />
          </label>
          <Button type="button" disabled={addSaving || !effectiveTipo || !effectiveAgrupar} onClick={() => void submitManualAdd()}>
            {addSaving ? 'Añadiendo…' : 'Añadir serie'}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {statusMessage ? (
        <p className="m-0 flex items-center gap-2 text-sm text-slate-400">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-cyan-500" />
          {statusMessage}
        </p>
      ) : null}

      {loading ? (
        <p className="text-sm text-slate-400">Cargando…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-slate-500">
          Sin filas aún. Puedes usar «Poblar desde catálogo» o «Agregar serie manualmente» arriba si ya
          conoces el código en los resultados.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-500">
                <th className="p-2 w-8">#</th>
                <th className="p-2">Código</th>
                <th className="p-2">Nombre visible</th>
                <th className="p-2">Color</th>
                <th className="p-2">Oculta</th>
                <th className="p-2">Grupo</th>
                <th className="p-2 w-24">Orden</th>
                <th className="p-2"> </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => (
                <tr key={r.id} className="border-b border-slate-800/80 hover:bg-slate-900/40">
                  <td className="p-2 text-slate-500">{idx + 1}</td>
                  <td className="p-2 font-mono text-[11px] text-slate-400 max-w-[180px] truncate">
                    {r.series_code}
                  </td>
                  <td className="p-2">
                    <input
                      className="w-full min-w-[140px] rounded border border-slate-700 bg-slate-950 px-2 py-1 text-slate-100"
                      defaultValue={r.display_name}
                      onBlur={(e) => {
                        const v = e.target.value.trim();
                        if (v && v !== r.display_name) void patchRow(r.id, { display_name: v });
                      }}
                    />
                  </td>
                  <td className="p-2">
                    <input
                      type="color"
                      className="h-8 w-12 cursor-pointer rounded border border-slate-700 bg-transparent"
                      value={r.color && /^#[0-9a-fA-F]{6}$/.test(r.color) ? r.color : '#999999'}
                      onChange={(e) => void patchRow(r.id, { color: e.target.value })}
                    />
                  </td>
                  <td className="p-2">
                    <input
                      type="checkbox"
                      checked={r.hidden}
                      onChange={(e) => void patchRow(r.id, { hidden: e.target.checked })}
                    />
                  </td>
                  <td className="p-2">
                    <input
                      className="w-full min-w-[100px] rounded border border-slate-700 bg-slate-950 px-2 py-1 text-slate-100"
                      defaultValue={r.group_key ?? ''}
                      placeholder="—"
                      onBlur={(e) => {
                        const v = e.target.value.trim();
                        const next = v || null;
                        if (next !== (r.group_key ?? null)) void patchRow(r.id, { group_key: next });
                      }}
                    />
                  </td>
                  <td className="p-2">
                    <div className="flex flex-col gap-1">
                      <button
                        type="button"
                        className="rounded border border-slate-700 px-1 text-[10px] hover:bg-slate-800 disabled:opacity-30"
                        disabled={idx === 0}
                        onClick={() => void move(idx, -1)}
                      >
                        ▲
                      </button>
                      <button
                        type="button"
                        className="rounded border border-slate-700 px-1 text-[10px] hover:bg-slate-800 disabled:opacity-30"
                        disabled={idx === rows.length - 1}
                        onClick={() => void move(idx, 1)}
                      >
                        ▼
                      </button>
                    </div>
                  </td>
                  <td className="p-2">
                    <button
                      type="button"
                      className="text-rose-400 hover:underline text-[11px] disabled:opacity-30"
                      disabled={savingId === r.id}
                      onClick={() => void removeRow(r.id)}
                    >
                      Quitar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
