import React, { useCallback, useEffect, useState } from 'react';
import { simulationApi } from '@/features/simulation/api/simulationApi';
import {
  resultTableTemplatesApi,
  type ResultTableColumnRulePayload,
  type ResultTablePresentationOptions,
  type ResultTableTemplateCreatePayload,
} from '@/features/reports/api/resultTableTemplatesApi';
import { Button } from '@/shared/components/Button';
import type { ChartCatalogItem, ResultTableTemplatePublic } from '@/types/domain';

type ColumnRuleRow = {
  category_key: string;
  hidden: boolean;
  sort_order: string;
};

type FormState = {
  name: string;
  display_title: string;
  seed_key_readonly: string | null;
  tipo: string;
  un: string;
  sub_filtro: string;
  loc: string;
  variable: string;
  agrupar_por: string;
  region: string;
  timeslice: string;
  table_period_years: string;
  table_cumulative: boolean;
  custom_series_order: string;
  y_axis_min: string;
  y_axis_max: string;
  is_enabled: boolean;
  columnRules: ColumnRuleRow[];
};

function emptyForm(): FormState {
  return {
    name: '',
    display_title: '',
    seed_key_readonly: null,
    tipo: '',
    un: 'PJ',
    sub_filtro: '',
    loc: '',
    variable: '',
    agrupar_por: '',
    region: '',
    timeslice: '',
    table_period_years: '',
    table_cumulative: false,
    custom_series_order: '',
    y_axis_min: '',
    y_axis_max: '',
    is_enabled: true,
    columnRules: [],
  };
}

function buildColumnRulesPayload(rules: ColumnRuleRow[]): ResultTableColumnRulePayload[] {
  return rules
    .filter((c) => c.category_key.trim())
    .map((c) => ({
      category_key: c.category_key.trim(),
      hidden: c.hidden,
      sort_order: c.sort_order.trim() ? Number(c.sort_order) : null,
    }));
}

function formFromTemplate(t: ResultTableTemplatePublic): FormState {
  const columnRules = (t.column_rules ?? []).map((c) => ({
    category_key: c.category_key,
    hidden: Boolean(c.hidden),
    sort_order: c.sort_order != null ? String(c.sort_order) : '',
  }));
  return {
    name: t.name,
    display_title: t.display_title ?? '',
    seed_key_readonly: t.seed_key ?? null,
    tipo: t.tipo,
    un: t.un,
    sub_filtro: t.sub_filtro ?? '',
    loc: t.loc ?? '',
    variable: t.variable ?? '',
    agrupar_por: t.agrupar_por ?? '',
    region: t.region ?? '',
    timeslice: t.timeslice ?? '',
    table_period_years:
      t.table_period_years != null && t.table_period_years >= 1
        ? String(t.table_period_years)
        : '',
    table_cumulative: Boolean(t.table_cumulative),
    custom_series_order: (t.custom_series_order ?? []).join(', '),
    y_axis_min: t.y_axis_min != null ? String(t.y_axis_min) : '',
    y_axis_max: t.y_axis_max != null ? String(t.y_axis_max) : '',
    is_enabled: t.is_enabled,
    columnRules,
  };
}

export function ResultTablesAdminTab() {
  const [catalog, setCatalog] = useState<ChartCatalogItem[]>([]);
  const [rows, setRows] = useState<ResultTableTemplatePublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [presOpts, setPresOpts] = useState<ResultTablePresentationOptions | null>(null);
  const [presOptsLoading, setPresOptsLoading] = useState(false);
  const [presOptsError, setPresOptsError] = useState<string | null>(null);

  useEffect(() => {
    if (!formOpen || !form.tipo.trim()) {
      setPresOpts(null);
      setPresOptsLoading(false);
      setPresOptsError(null);
      return;
    }
    let cancelled = false;
    setPresOptsLoading(true);
    setPresOptsError(null);
    const tid = window.setTimeout(() => {
      void resultTableTemplatesApi
        .getPresentationOptions({
          tipo: form.tipo.trim(),
          agrupar_por: form.agrupar_por.trim() || null,
          variable: form.variable.trim() || null,
        })
        .then((d) => {
          if (!cancelled) setPresOpts(d);
        })
        .catch((e) => {
          if (!cancelled) {
            setPresOpts(null);
            setPresOptsError(
              e instanceof Error ? e.message : 'Error cargando sugerencias.',
            );
          }
        })
        .finally(() => {
          if (!cancelled) setPresOptsLoading(false);
        });
    }, 280);
    return () => {
      cancelled = true;
      window.clearTimeout(tid);
    };
  }, [formOpen, form.tipo, form.agrupar_por, form.variable]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cat, list] = await Promise.all([
        simulationApi.getChartCatalog(),
        resultTableTemplatesApi.listManage(),
      ]);
      setCatalog(cat);
      setRows(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error cargando datos.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const openNew = () => {
    setEditingId(null);
    setForm(emptyForm());
    setFormOpen(true);
  };

  const openEdit = (t: ResultTableTemplatePublic) => {
    setEditingId(t.id);
    setFormOpen(true);
    void (async () => {
      try {
        const full = await resultTableTemplatesApi.get(t.id);
        setForm(formFromTemplate(full));
      } catch {
        setForm(formFromTemplate(t));
      }
    })();
  };

  const parseNum = (s: string): number | null => {
    const t = s.trim();
    if (!t) return null;
    const n = Number(t);
    return Number.isFinite(n) ? n : null;
  };

  const submit = async () => {
    if (!form.name.trim() || !form.tipo.trim() || !form.un.trim()) {
      setError('Nombre, tipo de gráfica y unidad son obligatorios.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const column_rules = buildColumnRulesPayload(form.columnRules);
      const seriesOrder = form.custom_series_order
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const payload: ResultTableTemplateCreatePayload = {
        name: form.name.trim(),
        display_title: form.display_title.trim() || null,
        is_enabled: form.is_enabled,
        tipo: form.tipo.trim(),
        un: form.un.trim(),
        sub_filtro: form.sub_filtro.trim() || null,
        loc: form.loc.trim() || null,
        variable: form.variable.trim() || null,
        agrupar_por: form.agrupar_por.trim() || null,
        region: form.region.trim() || null,
        timeslice: form.timeslice.trim() || null,
        table_period_years: parseNum(form.table_period_years),
        table_cumulative: form.table_cumulative,
        custom_series_order: seriesOrder.length > 0 ? seriesOrder : null,
        y_axis_min: parseNum(form.y_axis_min),
        y_axis_max: parseNum(form.y_axis_max),
        column_rules,
      };
      if (editingId != null) {
        await resultTableTemplatesApi.update(editingId, payload);
      } else {
        await resultTableTemplatesApi.create(payload);
      }
      setFormOpen(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar.');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: number) => {
    if (!window.confirm('¿Eliminar esta plantilla de tabla?')) return;
    setError(null);
    try {
      await resultTableTemplatesApi.delete(id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar.');
    }
  };

  const move = async (idx: number, dir: -1 | 1) => {
    const j = idx + dir;
    if (j < 0 || j >= rows.length) return;
    const next = [...rows];
    [next[idx], next[j]] = [next[j]!, next[idx]!];
    try {
      const reordered = await resultTableTemplatesApi.reorder(next.map((r) => r.id));
      setRows(reordered);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo reordenar.');
    }
  };

  const toggleEnabled = async (t: ResultTableTemplatePublic) => {
    try {
      await resultTableTemplatesApi.update(t.id, { is_enabled: !t.is_enabled });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error actualizando.');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="m-0 text-lg font-semibold text-white">Tablas en página de resultados</h2>
          <p className="m-0 mt-1 text-sm text-slate-500 max-w-2xl">
            Cada plantilla usa los mismos datos que una gráfica en vista tabla. Aparecen automáticamente
            bajo la gráfica principal en cada resultado óptimo. Las series (colores, orden, visibilidad)
            se configuran en «Series por gráfica» (configuración global).
          </p>
        </div>
        <Button type="button" onClick={openNew}>
          Nueva tabla
        </Button>
      </div>

      {error ? (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {loading ? <p className="text-slate-500 text-sm">Cargando…</p> : null}

      <ul className="space-y-3 list-none m-0 p-0">
        {rows.map((t, idx) => (
          <li
            key={t.id}
            className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 flex flex-wrap gap-3 items-start justify-between"
          >
            <div className="min-w-0">
              <p className="m-0 font-semibold text-white">{t.name}</p>
              <p className="m-0 text-[11px] text-slate-500 font-mono mt-1">
                {t.tipo} · {t.un}
                {t.seed_key ? ` · ${t.seed_key}` : ''}
                {t.is_enabled ? '' : ' · deshabilitada'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2 shrink-0">
              <Button type="button" variant="ghost" onClick={() => move(idx, -1)} disabled={idx === 0}>
                Subir
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => move(idx, 1)}
                disabled={idx >= rows.length - 1}
              >
                Bajar
              </Button>
              <Button type="button" variant="ghost" onClick={() => void toggleEnabled(t)}>
                {t.is_enabled ? 'Deshabilitar' : 'Habilitar'}
              </Button>
              <Button type="button" variant="ghost" onClick={() => openEdit(t)}>
                Editar
              </Button>
              <Button type="button" variant="ghost" onClick={() => void remove(t.id)}>
                Eliminar
              </Button>
            </div>
          </li>
        ))}
      </ul>

      {rows.length === 0 && !loading ? (
        <p className="text-slate-500 text-sm">No hay plantillas. Crea una con «Nueva tabla».</p>
      ) : null}

      {formOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60">
          <div className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl border border-slate-700 bg-slate-950 p-6 space-y-4 shadow-2xl">
            <h3 className="m-0 text-lg font-semibold text-white">
              {editingId != null ? 'Editar plantilla' : 'Nueva plantilla'}
            </h3>
            {form.seed_key_readonly ? (
              <p className="m-0 text-[11px] text-slate-500">
                Clave de siembra (solo lectura):{' '}
                <code className="text-slate-400">{form.seed_key_readonly}</code>
              </p>
            ) : null}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="block text-xs text-slate-400">
                Nombre interno
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
              </label>
              <label className="block text-xs text-slate-400">
                Título mostrado (opcional)
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.display_title}
                  onChange={(e) => setForm((f) => ({ ...f, display_title: e.target.value }))}
                />
              </label>
              <label className="block text-xs text-slate-400">
                Tipo de gráfica (id)
                <select
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.tipo}
                  onChange={(e) => setForm((f) => ({ ...f, tipo: e.target.value }))}
                >
                  <option value="">— elegir —</option>
                  {catalog.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label} ({c.id})
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs text-slate-400">
                Unidad
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.un}
                  onChange={(e) => setForm((f) => ({ ...f, un: e.target.value }))}
                />
              </label>
              <label className="block text-xs text-slate-400">
                Sub-filtro
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.sub_filtro}
                  onChange={(e) => setForm((f) => ({ ...f, sub_filtro: e.target.value }))}
                />
              </label>
              <label className="block text-xs text-slate-400">
                Loc
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.loc}
                  onChange={(e) => setForm((f) => ({ ...f, loc: e.target.value }))}
                />
              </label>
              <label className="block text-xs text-slate-400">
                Variable
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.variable}
                  onChange={(e) => setForm((f) => ({ ...f, variable: e.target.value }))}
                />
              </label>
              <label className="block text-xs text-slate-400">
                Agrupar por
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.agrupar_por}
                  onChange={(e) => setForm((f) => ({ ...f, agrupar_por: e.target.value }))}
                />
              </label>
              <label className="block text-xs text-slate-400">
                Región (REGIONAL)
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.region}
                  onChange={(e) => setForm((f) => ({ ...f, region: e.target.value }))}
                />
              </label>
              <label className="block text-xs text-slate-400">
                Timeslice
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.timeslice}
                  onChange={(e) => setForm((f) => ({ ...f, timeslice: e.target.value }))}
                />
              </label>
              <label className="block text-xs text-slate-400">
                Años cada N (vacío = todos)
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.table_period_years}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, table_period_years: e.target.value }))
                  }
                />
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-400 mt-6">
                <input
                  type="checkbox"
                  checked={form.table_cumulative}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, table_cumulative: e.target.checked }))
                  }
                />
                Valores acumulados
              </label>
              <label className="block text-xs text-slate-400 sm:col-span-2">
                Orden de series (comma-separated, opcional; override en tabla)
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.custom_series_order}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, custom_series_order: e.target.value }))
                  }
                />
              </label>
              <label className="block text-xs text-slate-400">
                Y min
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.y_axis_min}
                  onChange={(e) => setForm((f) => ({ ...f, y_axis_min: e.target.value }))}
                />
              </label>
              <label className="block text-xs text-slate-400">
                Y max
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
                  value={form.y_axis_max}
                  onChange={(e) => setForm((f) => ({ ...f, y_axis_max: e.target.value }))}
                />
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-400 mt-6 sm:col-span-2">
                <input
                  type="checkbox"
                  checked={form.is_enabled}
                  onChange={(e) => setForm((f) => ({ ...f, is_enabled: e.target.checked }))}
                />
                Habilitada (visible para todos en resultados)
              </label>
            </div>

            <datalist id="rtt-category-suggestions">
              {(presOpts?.category_keys ?? []).map((y) => (
                <option key={y} value={y} />
              ))}
            </datalist>

            {form.columnRules.length === 0 ? (
              <p className="m-0 text-[11px] text-slate-500">
                Sin reglas de columnas, la tabla muestra todas las categorías (años) del chart-data.
                Acota u oculta años con las reglas siguientes si lo necesitas.
              </p>
            ) : null}
            {form.tipo.trim() ? (
              <p className="m-0 text-[11px] text-slate-400">
                {presOptsLoading
                  ? 'Cargando sugerencias del catálogo…'
                  : presOptsError
                    ? presOptsError
                    : presOpts
                      ? `Sugerencias de años/columnas (agrupación «${presOpts.agrupar_por_resolved}»): ${presOpts.category_keys.length} entradas.`
                      : null}
              </p>
            ) : null}

            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="m-0 text-xs font-semibold text-slate-300">Columnas (categoría / año)</p>
                <button
                  type="button"
                  className="text-xs text-cyan-400 hover:underline"
                  onClick={() =>
                    setForm((f) => ({
                      ...f,
                      columnRules: [
                        ...f.columnRules,
                        { category_key: '', hidden: false, sort_order: '' },
                      ],
                    }))
                  }
                >
                  + Columna
                </button>
              </div>
              <div className="space-y-2">
                {form.columnRules.map((c, i) => (
                  <div
                    key={i}
                    className="grid grid-cols-1 sm:grid-cols-4 gap-2 p-2 rounded border border-slate-800 bg-slate-900/50"
                  >
                    <input
                      placeholder="Año o categoría (ej. 2030)"
                      list="rtt-category-suggestions"
                      autoComplete="off"
                      className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-white"
                      value={c.category_key}
                      onChange={(e) =>
                        setForm((f) => {
                          const next = [...f.columnRules];
                          next[i] = { ...next[i]!, category_key: e.target.value };
                          return { ...f, columnRules: next };
                        })
                      }
                    />
                    <input
                      placeholder="orden"
                      className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-white"
                      value={c.sort_order}
                      onChange={(e) =>
                        setForm((f) => {
                          const next = [...f.columnRules];
                          next[i] = { ...next[i]!, sort_order: e.target.value };
                          return { ...f, columnRules: next };
                        })
                      }
                    />
                    <label className="flex items-center gap-1 text-[11px] text-slate-400">
                      <input
                        type="checkbox"
                        checked={c.hidden}
                        onChange={(e) =>
                          setForm((f) => {
                            const next = [...f.columnRules];
                            next[i] = { ...next[i]!, hidden: e.target.checked };
                            return { ...f, columnRules: next };
                          })
                        }
                      />
                      oculta
                    </label>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap justify-end gap-2 pt-2 border-t border-slate-800">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setFormOpen(false);
                  setError(null);
                }}
              >
                Cancelar
              </Button>
              <Button type="button" onClick={() => void submit()} disabled={saving}>
                {saving ? 'Guardando…' : 'Guardar'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
