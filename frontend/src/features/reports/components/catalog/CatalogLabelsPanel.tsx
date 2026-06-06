import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/shared/components/Button';
import { isApiError } from '@/shared/errors/ApiError';
import {
  createLabel,
  deleteLabel,
  fetchLabelsPaged,
  updateLabel,
  type CatalogFormOptions,
  type LabelPublic,
} from '@/features/reports/api/visualizationCatalogApi';
import { confirmCatalogMutation } from '@/features/reports/components/catalog/catalogConfirm';
import { LabelFormModal } from '@/features/reports/components/catalog/LabelFormModal';

type Props = {
  formOptions: CatalogFormOptions | null;
  onMessage: (msg: string | null) => void;
};

export function CatalogLabelsPanel({ formOptions, onMessage }: Props) {
  const [items, setItems] = useState<LabelPublic[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<LabelPublic | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(q), 300);
    return () => window.clearTimeout(t);
  }, [q]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const params: { page: number; page_size: number; q?: string; category?: string } = {
        page,
        page_size: pageSize,
      };
      if (debouncedQ) params.q = debouncedQ;
      if (category) params.category = category;
      const data = await fetchLabelsPaged(params);
      setItems(data.items);
      setTotal(data.total);
    } catch (e: unknown) {
      onMessage(isApiError(e) ? e.message : 'Error al cargar labels');
    } finally {
      setLoading(false);
    }
  }, [debouncedQ, category, page, pageSize, onMessage]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const handleDelete = async (row: LabelPublic) => {
    if (!confirmCatalogMutation({ action: 'delete', entityLabel: row.code })) return;
    try {
      await deleteLabel(row.id);
      onMessage('Label eliminado.');
      await reload();
    } catch (e: unknown) {
      onMessage(isApiError(e) ? e.message : 'Error al eliminar');
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="text-slate-400">Buscar</span>
          <input
            className="mt-1 block w-48 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="código o nombre"
          />
        </label>
        <label className="text-sm">
          <span className="text-slate-400">Categoría</span>
          <select
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Todas</option>
            {(formOptions?.label_categories ?? []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-slate-400">Por página</span>
          <select
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(1);
            }}
          >
            {[25, 50, 100, 200].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <Button
          onClick={() => {
            setEditing(null);
            setModalOpen(true);
          }}
        >
          Nuevo label
        </Button>
      </div>

      <p className="text-xs text-slate-500">
        {total.toLocaleString()} registro{total === 1 ? '' : 's'}
      </p>

      {loading ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <div className="max-h-[420px] overflow-auto rounded border border-slate-800">
          <table className="min-w-full text-sm">
            <thead className="sticky top-0 bg-slate-800/95 text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left">Código</th>
                <th className="px-3 py-2 text-left">ES</th>
                <th className="px-3 py-2 text-left">EN</th>
                <th className="px-3 py-2 text-left">Categoría</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((l) => (
                <tr key={l.id} className="border-t border-slate-800">
                  <td className="px-3 py-2 font-mono text-xs">{l.code}</td>
                  <td className="px-3 py-2">{l.label_es}</td>
                  <td className="px-3 py-2 text-slate-400">{l.label_en ?? '—'}</td>
                  <td className="px-3 py-2">{l.category ?? '—'}</td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <button
                      type="button"
                      className="mr-2 text-sky-400 hover:text-sky-300"
                      onClick={() => {
                        setEditing(l);
                        setModalOpen(true);
                      }}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="text-rose-400 hover:text-rose-300"
                      onClick={() => void handleDelete(l)}
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center gap-2 text-sm">
        <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          Anterior
        </Button>
        <span className="text-slate-400">
          Página {page} / {totalPages}
        </span>
        <Button
          variant="ghost"
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
        >
          Siguiente
        </Button>
      </div>

      <LabelFormModal
        open={modalOpen}
        initial={editing}
        categories={formOptions?.label_categories ?? []}
        onClose={() => setModalOpen(false)}
        onSave={async (payload) => {
          if (editing) {
            await updateLabel(editing.id, {
              label_es: payload.label_es,
              label_en: payload.label_en,
              category: payload.category,
            });
            onMessage('Label actualizado.');
          } else {
            await createLabel(payload);
            onMessage('Label creado.');
          }
          await reload();
        }}
      />
    </div>
  );
}
