import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/shared/components/Button';
import { Modal } from '@/shared/components/Modal';
import type {
  CatalogFormOptions,
  ChartConfigDetail,
  ChartSubfilterPublic,
  FilterGroupPublic,
} from '@/features/reports/api/visualizationCatalogApi';

type Props = {
  open: boolean;
  initial?: ChartConfigDetail | null;
  formOptions: CatalogFormOptions | null;
  filterGroups: FilterGroupPublic[];
  onClose: () => void;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
};

const FLAG_KEYS = [
  { key: 'es_capacidad', label: 'Es capacidad' },
  { key: 'es_porcentaje', label: 'Es porcentaje' },
  { key: 'soporta_pareto', label: 'Soporta Pareto' },
  { key: 'soporta_tabla', label: 'Soporta tabla' },
  { key: 'has_loc', label: 'Tiene loc' },
] as const;

function defaultDetail(moduleId: number): ChartConfigDetail {
  return {
    id: 0,
    tipo: '',
    module_id: moduleId,
    submodule_id: null,
    label_titulo: '',
    label_figura: null,
    variable_default: 'Dispatch',
    filtro_kind: 'group',
    filtro_group_id: null,
    filtro_params_json: null,
    agrupar_por_default: 'TECNOLOGIA',
    agrupaciones_permitidas_json: ['TECNOLOGIA', 'FUEL'],
    color_fn_key: 'tecnologias',
    flags_json: {},
    msg_sin_datos: null,
    data_explorer_filters_json: null,
    is_visible: true,
    sort_order: 0,
    subfilters: [],
  };
}

export function ChartConfigFormModal({
  open,
  initial,
  formOptions,
  filterGroups,
  onClose,
  onSave,
}: Props) {
  const [form, setForm] = useState<ChartConfigDetail>(() =>
    defaultDetail(formOptions?.modules[0]?.id ?? 1),
  );
  const [filtroParamsJson, setFiltroParamsJson] = useState('{}');
  const [explorerJson, setExplorerJson] = useState('{}');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const base =
      initial ??
      defaultDetail(formOptions?.modules[0]?.id ?? 1);
    setForm({ ...base, subfilters: base.subfilters ? [...base.subfilters] : [] });
    setFiltroParamsJson(JSON.stringify(base.filtro_params_json ?? {}, null, 2));
    setExplorerJson(JSON.stringify(base.data_explorer_filters_json ?? {}, null, 2));
    setError(null);
  }, [open, initial, formOptions]);

  const submodulesForModule = useMemo(
    () =>
      (formOptions?.submodules ?? []).filter((s) => s.module_id === form.module_id),
    [formOptions, form.module_id],
  );

  const toggleGrouping = (value: string) => {
    const current = form.agrupaciones_permitidas_json ?? [];
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    setForm((f) => ({ ...f, agrupaciones_permitidas_json: next }));
  };

  const toggleFlag = (key: string, checked: boolean) => {
    setForm((f) => ({
      ...f,
      flags_json: { ...(f.flags_json ?? {}), [key]: checked },
    }));
  };

  const addSubfilter = () => {
    setForm((f) => ({
      ...f,
      subfilters: [
        ...f.subfilters,
        {
          code: '',
          display_label: '',
          group_label: '',
          filter_group_id: null,
          sort_order: f.subfilters.length,
          default_selected: false,
        },
      ],
    }));
  };

  const updateSubfilter = (idx: number, patch: Partial<ChartSubfilterPublic>) => {
    setForm((f) => ({
      ...f,
      subfilters: f.subfilters.map((s, i) => (i === idx ? { ...s, ...patch } : s)),
    }));
  };

  const removeSubfilter = (idx: number) => {
    setForm((f) => ({
      ...f,
      subfilters: f.subfilters.filter((_, i) => i !== idx),
    }));
  };

  const submit = async () => {
    if (!form.tipo.trim() || !form.label_titulo.trim() || !form.variable_default.trim()) {
      setError('tipo, título y variable son obligatorios.');
      return;
    }
    let filtroParams: Record<string, unknown> | null = null;
    let explorer: Record<string, unknown> | null = null;
    try {
      filtroParams = filtroParamsJson.trim() ? JSON.parse(filtroParamsJson) : null;
      explorer = explorerJson.trim() ? JSON.parse(explorerJson) : null;
    } catch {
      setError('JSON inválido en parámetros de filtro o data explorer.');
      return;
    }
    setSaving(true);
    try {
      await onSave({
        ...form,
        tipo: form.tipo.trim(),
        label_titulo: form.label_titulo.trim(),
        variable_default: form.variable_default.trim(),
        filtro_params_json: filtroParams,
        data_explorer_filters_json: explorer,
        subfilters: form.subfilters.filter((s) => s.code.trim()),
      });
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title={initial ? `Editar gráfica: ${initial.tipo}` : 'Nueva gráfica'}
      onClose={onClose}
      wide
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={() => void submit()} disabled={saving}>
            {saving ? 'Guardando…' : 'Guardar'}
          </Button>
        </>
      }
    >
      <div className="max-h-[75vh] space-y-4 overflow-y-auto pr-1 text-sm">
        {error && (
          <p className="rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-rose-200">
            {error}
          </p>
        )}

        <section className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="text-slate-400">tipo (id único)</span>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono"
              value={form.tipo}
              onChange={(e) => setForm((f) => ({ ...f, tipo: e.target.value }))}
              disabled={Boolean(initial)}
            />
          </label>
          <label className="block">
            <span className="text-slate-400">Orden</span>
            <input
              type="number"
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5"
              value={form.sort_order}
              onChange={(e) => setForm((f) => ({ ...f, sort_order: Number(e.target.value) }))}
            />
          </label>
          <label className="block">
            <span className="text-slate-400">Módulo</span>
            <select
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5"
              value={form.module_id}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  module_id: Number(e.target.value),
                  submodule_id: null,
                }))
              }
            >
              {(formOptions?.modules ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-slate-400">Submódulo</span>
            <select
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5"
              value={form.submodule_id ?? ''}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  submodule_id: e.target.value ? Number(e.target.value) : null,
                }))
              }
            >
              <option value="">—</option>
              {submodulesForModule.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block sm:col-span-2">
            <span className="text-slate-400">Título</span>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5"
              value={form.label_titulo}
              onChange={(e) => setForm((f) => ({ ...f, label_titulo: e.target.value }))}
            />
          </label>
          <label className="block">
            <span className="text-slate-400">Figura (eje Y)</span>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5"
              value={form.label_figura ?? ''}
              onChange={(e) =>
                setForm((f) => ({ ...f, label_figura: e.target.value || null }))
              }
            />
          </label>
          <label className="block">
            <span className="text-slate-400">Variable default</span>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono"
              value={form.variable_default}
              onChange={(e) => setForm((f) => ({ ...f, variable_default: e.target.value }))}
            />
          </label>
        </section>

        <section className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="text-slate-400">filtro_kind</span>
            <select
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5"
              value={form.filtro_kind}
              onChange={(e) => setForm((f) => ({ ...f, filtro_kind: e.target.value }))}
            >
              {(formOptions?.filtro_kinds ?? ['group']).map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-slate-400">Grupo filtro</span>
            <select
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5"
              value={form.filtro_group_id ?? ''}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  filtro_group_id: e.target.value ? Number(e.target.value) : null,
                }))
              }
            >
              <option value="">—</option>
              {filterGroups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.code}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-slate-400">color_fn_key</span>
            <select
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5"
              value={form.color_fn_key}
              onChange={(e) => setForm((f) => ({ ...f, color_fn_key: e.target.value }))}
            >
              {(formOptions?.color_fn_keys ?? []).map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-slate-400">Agrupación default</span>
            <select
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5"
              value={form.agrupar_por_default}
              onChange={(e) => setForm((f) => ({ ...f, agrupar_por_default: e.target.value }))}
            >
              {(formOptions?.grouping_axes ?? []).map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </select>
          </label>
        </section>

        <section>
          <p className="mb-2 text-slate-400">Agrupaciones permitidas</p>
          <div className="flex flex-wrap gap-2">
            {(formOptions?.grouping_axes ?? []).map((a) => (
              <label key={a.value} className="flex items-center gap-1 rounded bg-slate-800 px-2 py-1">
                <input
                  type="checkbox"
                  checked={(form.agrupaciones_permitidas_json ?? []).includes(a.value)}
                  onChange={() => toggleGrouping(a.value)}
                />
                <span className="text-xs">{a.label}</span>
              </label>
            ))}
          </div>
        </section>

        <section>
          <p className="mb-2 text-slate-400">Flags</p>
          <div className="flex flex-wrap gap-3">
            {FLAG_KEYS.map(({ key, label }) => (
              <label key={key} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={Boolean(form.flags_json?.[key])}
                  onChange={(e) => toggleFlag(key, e.target.checked)}
                />
                {label}
              </label>
            ))}
            <label className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={form.is_visible}
                onChange={(e) => setForm((f) => ({ ...f, is_visible: e.target.checked }))}
              />
              Visible
            </label>
          </div>
        </section>

        <label className="block">
          <span className="text-slate-400">Mensaje sin datos</span>
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5"
            value={form.msg_sin_datos ?? ''}
            onChange={(e) =>
              setForm((f) => ({ ...f, msg_sin_datos: e.target.value || null }))
            }
          />
        </label>

        <label className="block">
          <span className="text-slate-400">filtro_params_json</span>
          <textarea
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-xs"
            rows={3}
            value={filtroParamsJson}
            onChange={(e) => setFiltroParamsJson(e.target.value)}
          />
        </label>

        <label className="block">
          <span className="text-slate-400">data_explorer_filters_json</span>
          <textarea
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-xs"
            rows={3}
            value={explorerJson}
            onChange={(e) => setExplorerJson(e.target.value)}
          />
        </label>

        <section>
          <div className="mb-2 flex items-center justify-between">
            <h4 className="font-medium text-slate-300">Subfiltros</h4>
            <Button variant="ghost" onClick={addSubfilter}>
              + Subfiltro
            </Button>
          </div>
          {form.subfilters.map((sf, idx) => (
            <div key={idx} className="mb-2 grid gap-2 rounded border border-slate-800 p-2 sm:grid-cols-4">
              <input
                placeholder="code"
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs"
                value={sf.code}
                onChange={(e) => updateSubfilter(idx, { code: e.target.value })}
              />
              <input
                placeholder="display_label"
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs"
                value={sf.display_label ?? ''}
                onChange={(e) => updateSubfilter(idx, { display_label: e.target.value })}
              />
              <select
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs"
                value={sf.filter_group_id ?? ''}
                onChange={(e) =>
                  updateSubfilter(idx, {
                    filter_group_id: e.target.value ? Number(e.target.value) : null,
                  })
                }
              >
                <option value="">Grupo —</option>
                {filterGroups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.code}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="text-left text-xs text-rose-400"
                onClick={() => removeSubfilter(idx)}
              >
                Eliminar
              </button>
            </div>
          ))}
        </section>
      </div>
    </Modal>
  );
}
