import { useEffect, useState } from 'react';
import { Button } from '@/shared/components/Button';
import { Modal } from '@/shared/components/Modal';
import type {
  CatalogFormOptions,
  FilterGroupPublic,
  FilterMemberPublic,
} from '@/features/reports/api/visualizationCatalogApi';

type Props = {
  open: boolean;
  initial?: FilterGroupPublic | null;
  formOptions: CatalogFormOptions | null;
  onClose: () => void;
  onSave: (payload: {
    code: string;
    name: string;
    description: string | null;
    filter_mode: string;
    members: FilterMemberPublic[];
  }) => Promise<void>;
};

function emptyMember(i: number, filterMode: string): FilterMemberPublic {
  return {
    member_kind: 'CODE',
    operation: 'INCLUDE',
    entity_type: filterMode === 'FUEL_ONLY' ? 'FUEL' : 'TECHNOLOGY',
    match_mode: 'EXACT',
    value: '',
    ref_group_id: null,
    sort_order: i,
  };
}

export function FilterGroupFormModal({ open, initial, formOptions, onClose, onSave }: Props) {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [filterMode, setFilterMode] = useState('TECH_ONLY');
  const [members, setMembers] = useState<FilterMemberPublic[]>([]);
  const [importText, setImportText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setCode(initial?.code ?? '');
    setName(initial?.name ?? '');
    setDescription(initial?.description ?? '');
    setFilterMode(initial?.filter_mode ?? 'TECH_ONLY');
    setMembers(initial?.members?.length ? [...initial.members] : [emptyMember(0, 'TECH_ONLY')]);
    setImportText('');
    setError(null);
  }, [open, initial]);

  const addMember = () => {
    setMembers((m) => [...m, emptyMember(m.length, filterMode)]);
  };

  const removeMember = (idx: number) => {
    setMembers((m) => m.filter((_, i) => i !== idx));
  };

  const updateMember = (idx: number, patch: Partial<FilterMemberPublic>) => {
    setMembers((m) => m.map((row, i) => (i === idx ? { ...row, ...patch } : row)));
  };

  const applyImport = (mode: 'merge' | 'replace') => {
    const lines = importText
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    if (!lines.length) return;
    const defaultEt = filterMode === 'FUEL_ONLY' ? 'FUEL' : 'TECHNOLOGY';
    const parsed: FilterMemberPublic[] = lines.map((line, i) => {
      const parts = line.split(/[,;\t]/).map((p) => p.trim());
      return {
        member_kind: 'CODE',
        operation: (parts[1]?.toUpperCase() as 'INCLUDE' | 'EXCLUDE') || 'INCLUDE',
        entity_type: (parts[2]?.toUpperCase() as 'TECHNOLOGY' | 'FUEL') || defaultEt,
        match_mode: 'EXACT',
        value: parts[0] || '',
        ref_group_id: null,
        sort_order: i,
      };
    });
    if (mode === 'replace') {
      setMembers(parsed);
    } else {
      const seen = new Set(members.map((m) => `${m.value}|${m.entity_type}`));
      const merged = [...members];
      for (const p of parsed) {
        const k = `${p.value}|${p.entity_type}`;
        if (!seen.has(k)) {
          merged.push({ ...p, sort_order: merged.length });
          seen.add(k);
        }
      }
      setMembers(merged);
    }
    setImportText('');
  };

  const submit = async () => {
    if (!code.trim() || !name.trim()) {
      setError('Código y nombre son obligatorios.');
      return;
    }
    setSaving(true);
    try {
      await onSave({
        code: code.trim(),
        name: name.trim(),
        description: description.trim() || null,
        filter_mode: filterMode,
        members: members.filter((m) => m.value?.trim() || m.ref_group_id),
      });
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  const ops = formOptions?.member_operations ?? ['INCLUDE', 'EXCLUDE'];
  const ets = formOptions?.entity_types ?? ['TECHNOLOGY', 'FUEL'];

  return (
    <Modal
      open={open}
      title={initial ? 'Editar agrupación' : 'Nueva agrupación'}
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
      <div className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        {error && (
          <p className="rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {error}
          </p>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-slate-400">Código</span>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-sm"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              disabled={Boolean(initial)}
            />
          </label>
          <label className="block text-sm">
            <span className="text-slate-400">Modo</span>
            <select
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
              value={filterMode}
              onChange={(e) => setFilterMode(e.target.value)}
            >
              {(formOptions?.filter_modes ?? ['TECH_ONLY', 'FUEL_ONLY']).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm sm:col-span-2">
            <span className="text-slate-400">Nombre</span>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block text-sm sm:col-span-2">
            <span className="text-slate-400">Descripción</span>
            <textarea
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-sm font-medium text-slate-300">Miembros</h4>
            <Button variant="ghost" onClick={addMember}>
              + Miembro
            </Button>
          </div>
          <div className="overflow-x-auto rounded border border-slate-800">
            <table className="min-w-full text-xs">
              <thead className="bg-slate-800/80 text-slate-400">
                <tr>
                  <th className="px-2 py-1 text-left">Valor</th>
                  <th className="px-2 py-1 text-left">Op</th>
                  <th className="px-2 py-1 text-left">Tipo</th>
                  <th className="px-2 py-1" />
                </tr>
              </thead>
              <tbody>
                {members.map((m, idx) => (
                  <tr key={idx} className="border-t border-slate-800">
                    <td className="px-2 py-1">
                      <input
                        className="w-full rounded border border-slate-700 bg-slate-900 px-1 py-0.5 font-mono"
                        value={m.value ?? ''}
                        onChange={(e) => updateMember(idx, { value: e.target.value })}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <select
                        className="rounded border border-slate-700 bg-slate-900 px-1 py-0.5"
                        value={m.operation}
                        onChange={(e) => updateMember(idx, { operation: e.target.value })}
                      >
                        {ops.map((o) => (
                          <option key={o} value={o}>
                            {o}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-1">
                      <select
                        className="rounded border border-slate-700 bg-slate-900 px-1 py-0.5"
                        value={m.entity_type}
                        onChange={(e) => updateMember(idx, { entity_type: e.target.value })}
                      >
                        {ets.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-1">
                      <button
                        type="button"
                        className="text-rose-400 hover:text-rose-300"
                        onClick={() => removeMember(idx)}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900/50 p-3">
          <p className="mb-2 text-sm text-slate-400">
            Importar códigos (una línea o CSV: code, operation, entity_type)
          </p>
          <textarea
            className="mb-2 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-xs"
            rows={4}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder="PWRSOL&#10;PWRWIND,INCLUDE,TECHNOLOGY"
          />
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => applyImport('merge')}>
              Agregar al listado
            </Button>
            <Button variant="ghost" onClick={() => applyImport('replace')}>
              Reemplazar todo
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
