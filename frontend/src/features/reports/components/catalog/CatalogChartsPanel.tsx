import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/shared/components/Button';
import { isApiError } from '@/shared/errors/ApiError';
import {
  createChartConfig,
  deleteChartConfig,
  fetchChartConfigDetail,
  fetchChartConfigs,
  fetchFilterGroups,
  updateChartConfig,
  type ChartConfigCreatePayload,
  type CatalogFormOptions,
  type ChartConfigPublic,
  type FilterGroupPublic,
} from '@/features/reports/api/visualizationCatalogApi';
import { ChartConfigFormModal } from '@/features/reports/components/catalog/ChartConfigFormModal';
import { confirmCatalogMutation } from '@/features/reports/components/catalog/catalogConfirm';

type Props = {
  formOptions: CatalogFormOptions | null;
  onMessage: (msg: string | null) => void;
};

export function CatalogChartsPanel({ formOptions, onMessage }: Props) {
  const [items, setItems] = useState<ChartConfigPublic[]>([]);
  const [filterGroups, setFilterGroups] = useState<FilterGroupPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Awaited<ReturnType<typeof fetchChartConfigDetail>> | null>(
    null,
  );

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [charts, groups] = await Promise.all([fetchChartConfigs(), fetchFilterGroups()]);
      setItems(charts);
      setFilterGroups(groups);
    } catch (e: unknown) {
      onMessage(isApiError(e) ? e.message : 'Error al cargar gráficas');
    } finally {
      setLoading(false);
    }
  }, [onMessage]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const openEdit = async (tipo: string) => {
    if (!confirmCatalogMutation({ action: 'edit', entityLabel: tipo })) return;
    try {
      setEditing(await fetchChartConfigDetail(tipo));
      setModalOpen(true);
    } catch (e: unknown) {
      onMessage(isApiError(e) ? e.message : 'Error al cargar gráfica');
    }
  };

  const handleDelete = async (row: ChartConfigPublic) => {
    if (!confirmCatalogMutation({ action: 'delete', entityLabel: row.tipo })) return;
    try {
      await deleteChartConfig(row.tipo);
      onMessage('Gráfica eliminada.');
      await reload();
    } catch (e: unknown) {
      onMessage(isApiError(e) ? e.message : 'Error al eliminar');
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button
          onClick={() => {
            setEditing(null);
            setModalOpen(true);
          }}
        >
          Nueva gráfica
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <div className="max-h-[420px] overflow-auto rounded border border-slate-800">
          <table className="min-w-full text-sm">
            <thead className="sticky top-0 bg-slate-800/95 text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left">tipo</th>
                <th className="px-3 py-2 text-left">Título</th>
                <th className="px-3 py-2 text-left">Variable</th>
                <th className="px-3 py-2 text-left">Agrupación</th>
                <th className="px-3 py-2 text-left">Visible</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-t border-slate-800">
                  <td className="px-3 py-2 font-mono text-xs">{c.tipo}</td>
                  <td className="px-3 py-2">{c.label_titulo}</td>
                  <td className="px-3 py-2">{c.variable_default}</td>
                  <td className="px-3 py-2">{c.agrupar_por_default}</td>
                  <td className="px-3 py-2">{c.is_visible ? 'Sí' : 'No'}</td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <button
                      type="button"
                      className="mr-2 text-sky-400 hover:text-sky-300"
                      onClick={() => void openEdit(c.tipo)}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="text-rose-400 hover:text-rose-300"
                      onClick={() => void handleDelete(c)}
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

      <ChartConfigFormModal
        open={modalOpen}
        initial={editing}
        formOptions={formOptions}
        filterGroups={filterGroups}
        onClose={() => setModalOpen(false)}
        onSave={async (payload) => {
          const body = payload as ChartConfigCreatePayload & { id?: number };
          const { id: _id, ...rest } = body;
          if (editing) {
            await updateChartConfig(editing.tipo, rest);
            onMessage('Gráfica actualizada.');
          } else {
            await createChartConfig(rest);
            onMessage('Gráfica creada.');
          }
          await reload();
        }}
      />
    </div>
  );
}
