import { useEffect, useState } from 'react';
import { Button } from '@/shared/components/Button';
import { Modal } from '@/shared/components/Modal';
import type { ColorPalettePublic } from '@/features/reports/api/visualizationCatalogApi';

type Props = {
  open: boolean;
  initial?: ColorPalettePublic | null;
  colorGroups: string[];
  onClose: () => void;
  onSave: (payload: {
    group: string;
    key: string;
    color_hex: string;
    sort_order: number;
  }) => Promise<void>;
};

export function ColorFormModal({ open, initial, colorGroups, onClose, onSave }: Props) {
  const [group, setGroup] = useState('fuel');
  const [key, setKey] = useState('');
  const [colorHex, setColorHex] = useState('#888888');
  const [sortOrder, setSortOrder] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setGroup(initial?.group ?? 'fuel');
    setKey(initial?.key ?? '');
    setColorHex(initial?.color_hex ?? '#888888');
    setSortOrder(initial?.sort_order ?? 0);
    setError(null);
  }, [open, initial]);

  const submit = async () => {
    if (!group.trim() || !key.trim() || !colorHex.trim()) {
      setError('Grupo, clave y color son obligatorios.');
      return;
    }
    setSaving(true);
    try {
      await onSave({
        group: group.trim(),
        key: key.trim(),
        color_hex: colorHex.trim(),
        sort_order: sortOrder,
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
      title={initial ? 'Editar color' : 'Nuevo color'}
      onClose={onClose}
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
      <div className="grid gap-3 sm:grid-cols-2">
        {error && (
          <p className="sm:col-span-2 rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {error}
          </p>
        )}
        <label className="block text-sm">
          <span className="text-slate-400">Grupo</span>
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
            value={group}
            onChange={(e) => setGroup(e.target.value)}
            list="color-groups"
          />
          <datalist id="color-groups">
            {colorGroups.map((g) => (
              <option key={g} value={g} />
            ))}
          </datalist>
        </label>
        <label className="block text-sm">
          <span className="text-slate-400">Clave</span>
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-sm"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            disabled={Boolean(initial)}
          />
        </label>
        <label className="block text-sm">
          <span className="text-slate-400">Color</span>
          <div className="mt-1 flex items-center gap-2">
            <input type="color" value={colorHex} onChange={(e) => setColorHex(e.target.value)} />
            <input
              className="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-sm"
              value={colorHex}
              onChange={(e) => setColorHex(e.target.value)}
            />
          </div>
        </label>
        <label className="block text-sm">
          <span className="text-slate-400">Orden</span>
          <input
            type="number"
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
            value={sortOrder}
            onChange={(e) => setSortOrder(Number(e.target.value))}
          />
        </label>
      </div>
    </Modal>
  );
}
