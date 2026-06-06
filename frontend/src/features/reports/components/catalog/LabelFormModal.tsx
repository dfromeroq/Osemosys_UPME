import { useEffect, useState } from 'react';
import { Button } from '@/shared/components/Button';
import { Modal } from '@/shared/components/Modal';
import type { LabelPublic } from '@/features/reports/api/visualizationCatalogApi';

type Props = {
  open: boolean;
  initial?: LabelPublic | null;
  categories: string[];
  onClose: () => void;
  onSave: (payload: {
    code: string;
    label_es: string;
    label_en: string | null;
    category: string | null;
  }) => Promise<void>;
};

export function LabelFormModal({ open, initial, categories, onClose, onSave }: Props) {
  const [code, setCode] = useState('');
  const [labelEs, setLabelEs] = useState('');
  const [labelEn, setLabelEn] = useState('');
  const [category, setCategory] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setCode(initial?.code ?? '');
    setLabelEs(initial?.label_es ?? '');
    setLabelEn(initial?.label_en ?? '');
    setCategory(initial?.category ?? '');
    setError(null);
  }, [open, initial]);

  const submit = async () => {
    if (!code.trim() || !labelEs.trim()) {
      setError('Código y nombre ES son obligatorios.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({
        code: code.trim(),
        label_es: labelEs.trim(),
        label_en: labelEn.trim() || null,
        category: category.trim() || null,
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
      title={initial ? 'Editar label' : 'Nuevo label'}
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
      <div className="grid gap-3 sm:grid-cols-2">
        {error && (
          <p className="sm:col-span-2 rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {error}
          </p>
        )}
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
          <span className="text-slate-400">Categoría</span>
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            list="label-categories"
          />
          <datalist id="label-categories">
            {categories.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </label>
        <label className="block text-sm sm:col-span-2">
          <span className="text-slate-400">Nombre (ES)</span>
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
            value={labelEs}
            onChange={(e) => setLabelEs(e.target.value)}
          />
        </label>
        <label className="block text-sm sm:col-span-2">
          <span className="text-slate-400">Nombre (EN)</span>
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
            value={labelEn}
            onChange={(e) => setLabelEn(e.target.value)}
          />
        </label>
      </div>
    </Modal>
  );
}
