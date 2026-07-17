import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/shared/components/Button';
import { isApiError } from '@/shared/errors/ApiError';
import {
  createFilterGroup,
  deleteFilterGroup,
  fetchFilterGroup,
  fetchFilterGroups,
  replaceFilterGroupMembers,
  updateFilterGroup,
  type CatalogFormOptions,
  type FilterGroupPublic,
} from '@/features/reports/api/visualizationCatalogApi';
import { confirmCatalogMutation } from '@/features/reports/components/catalog/catalogConfirm';
import { FilterGroupFormModal } from '@/features/reports/components/catalog/FilterGroupFormModal';

type Props = {
  formOptions: CatalogFormOptions | null;
  onMessage: (msg: string | null) => void;
};

export function CatalogFilterGroupsPanel({ formOptions, onMessage }: Props) {
  const [items, setItems] = useState<FilterGroupPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<FilterGroupPublic | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchFilterGroups());
    } catch (e: unknown) {
      onMessage(isApiError(e) ? e.message : 'Error al cargar agrupaciones');
    } finally {
      setLoading(false);
    }
  }, [onMessage]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const openEdit = async (code: string, isSystem: boolean) => {
    if (!confirmCatalogMutation({ isSystem, action: 'edit', entityLabel: code })) return;
    try {
      const detail = await fetchFilterGroup(code);
      setEditing(detail);
      setModalOpen(true);
    } catch (e: unknown) {
      onMessage(isApiError(e) ? e.message : 'Error al cargar grupo');
    }
  };

  const handleDelete = async (row: FilterGroupPublic) => {
    if (
      !confirmCatalogMutation({
        isSystem: row.is_system,
        action: 'delete',
        entityLabel: row.code,
      })
    ) {
      return;
    }
    try {
      await deleteFilterGroup(row.code);
      onMessage('Agrupación eliminada.');
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
          Nueva agrupación
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <div className="max-h-[420px] overflow-auto rounded border border-slate-800">
          <table className="min-w-full text-sm">
            <thead className="sticky top-0 bg-slate-800/95 text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left">Código</th>
                <th className="px-3 py-2 text-left">Nombre</th>
                <th className="px-3 py-2 text-left">Modo</th>
                <th className="px-3 py-2 text-left">Miembros</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((g) => (
                <tr key={g.id} className="border-t border-slate-800">
                  <td className="px-3 py-2 font-mono text-xs">
                    {g.code}
                    {g.is_system && (
                      <span className="ml-1 rounded bg-amber-500/20 px-1 text-[10px] text-amber-300">
                        sistema
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">{g.name}</td>
                  <td className="px-3 py-2">{g.filter_mode}</td>
                  <td className="px-3 py-2 text-slate-400">{g.members?.length ?? 0}</td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <button
                      type="button"
                      className="mr-2 text-sky-400 hover:text-sky-300"
                      onClick={() => void openEdit(g.code, g.is_system)}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="text-rose-400 hover:text-rose-300"
                      onClick={() => void handleDelete(g)}
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

      <FilterGroupFormModal
        open={modalOpen}
        initial={editing}
        formOptions={formOptions}
        onClose={() => setModalOpen(false)}
        onSave={async (payload) => {
          if (editing) {
            await updateFilterGroup(editing.code, {
              name: payload.name,
              description: payload.description,
              filter_mode: payload.filter_mode,
            });
            await replaceFilterGroupMembers(editing.code, payload.members);
            onMessage('Agrupación actualizada.');
          } else {
            await createFilterGroup(payload);
            onMessage('Agrupación creada.');
          }
          await reload();
        }}
      />
    </div>
  );
}
