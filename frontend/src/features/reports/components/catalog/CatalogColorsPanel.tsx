import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/shared/components/Button';
import { isApiError } from '@/shared/errors/ApiError';
import {
  createColor,
  deleteColor,
  fetchVisualizationColors,
  updateColor,
  type CatalogFormOptions,
  type ColorPalettePublic,
} from '@/features/reports/api/visualizationCatalogApi';
import { confirmCatalogMutation } from '@/features/reports/components/catalog/catalogConfirm';
import { ColorFormModal } from '@/features/reports/components/catalog/ColorFormModal';

type Props = {
  formOptions: CatalogFormOptions | null;
  onMessage: (msg: string | null) => void;
};

export function CatalogColorsPanel({ formOptions, onMessage }: Props) {
  const [items, setItems] = useState<ColorPalettePublic[]>([]);
  const [groupFilter, setGroupFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ColorPalettePublic | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchVisualizationColors(groupFilter || undefined));
    } catch (e: unknown) {
      onMessage(isApiError(e) ? e.message : 'Error al cargar colores');
    } finally {
      setLoading(false);
    }
  }, [groupFilter, onMessage]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleDelete = async (row: ColorPalettePublic) => {
    if (!confirmCatalogMutation({ action: 'delete', entityLabel: `${row.group}/${row.key}` })) return;
    try {
      await deleteColor(row.id);
      onMessage('Color eliminado.');
      await reload();
    } catch (e: unknown) {
      onMessage(isApiError(e) ? e.message : 'Error al eliminar');
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="text-slate-400">Grupo</span>
          <select
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
            value={groupFilter}
            onChange={(e) => setGroupFilter(e.target.value)}
          >
            <option value="">Todos</option>
            {(formOptions?.color_groups ?? []).map((g) => (
              <option key={g} value={g}>
                {g}
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
          Nuevo color
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <div className="max-h-[420px] overflow-auto rounded border border-slate-800">
          <table className="min-w-full text-sm">
            <thead className="sticky top-0 bg-slate-800/95 text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left">Grupo</th>
                <th className="px-3 py-2 text-left">Clave</th>
                <th className="px-3 py-2 text-left">Color</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-t border-slate-800">
                  <td className="px-3 py-2">{c.group}</td>
                  <td className="px-3 py-2 font-mono text-xs">{c.key}</td>
                  <td className="px-3 py-2">
                    <span
                      className="mr-2 inline-block h-4 w-4 rounded border border-slate-600 align-middle"
                      style={{ backgroundColor: c.color_hex }}
                    />
                    {c.color_hex}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <button
                      type="button"
                      className="mr-2 text-sky-400 hover:text-sky-300"
                      onClick={() => {
                        setEditing(c);
                        setModalOpen(true);
                      }}
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

      <ColorFormModal
        open={modalOpen}
        initial={editing}
        colorGroups={formOptions?.color_groups ?? []}
        onClose={() => setModalOpen(false)}
        onSave={async (payload) => {
          if (editing) {
            await updateColor(editing.id, payload);
            onMessage('Color actualizado.');
          } else {
            await createColor(payload);
            onMessage('Color creado.');
          }
          await reload();
        }}
      />
    </div>
  );
}
