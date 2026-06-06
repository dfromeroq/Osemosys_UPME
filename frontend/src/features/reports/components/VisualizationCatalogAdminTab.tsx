import { useEffect, useState } from 'react';
import { fetchFormOptions, type CatalogFormOptions } from '@/features/reports/api/visualizationCatalogApi';
import { CatalogChartsPanel } from '@/features/reports/components/catalog/CatalogChartsPanel';
import { CatalogColorsPanel } from '@/features/reports/components/catalog/CatalogColorsPanel';
import { CatalogFilterGroupsPanel } from '@/features/reports/components/catalog/CatalogFilterGroupsPanel';
import { CatalogLabelsPanel } from '@/features/reports/components/catalog/CatalogLabelsPanel';

type SubTab = 'groups' | 'charts' | 'labels' | 'colors';

export function VisualizationCatalogAdminTab() {
  const [subTab, setSubTab] = useState<SubTab>('groups');
  const [formOptions, setFormOptions] = useState<CatalogFormOptions | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void fetchFormOptions()
      .then(setFormOptions)
      .catch(() => setFormOptions(null));
  }, []);

  const tabs: { id: SubTab; label: string }[] = [
    { id: 'groups', label: 'Agrupaciones' },
    { id: 'charts', label: 'Gráficas' },
    { id: 'labels', label: 'Labels' },
    { id: 'colors', label: 'Colores' },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h3 className="text-lg font-semibold text-slate-100">Catálogo de gráficas (BD)</h3>
      </div>

      <div className="flex gap-2 border-b border-slate-800 pb-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`rounded px-3 py-1 text-sm transition-colors ${
              subTab === t.id
                ? 'bg-sky-600/30 text-sky-200'
                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
            }`}
            onClick={() => setSubTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {message && (
        <p className="rounded border border-slate-700 bg-slate-800/60 px-3 py-2 text-sm text-slate-300">
          {message}
        </p>
      )}

      {subTab === 'groups' && (
        <CatalogFilterGroupsPanel formOptions={formOptions} onMessage={setMessage} />
      )}
      {subTab === 'charts' && (
        <CatalogChartsPanel formOptions={formOptions} onMessage={setMessage} />
      )}
      {subTab === 'labels' && (
        <CatalogLabelsPanel formOptions={formOptions} onMessage={setMessage} />
      )}
      {subTab === 'colors' && (
        <CatalogColorsPanel formOptions={formOptions} onMessage={setMessage} />
      )}

      <p className="text-xs text-slate-500">
        Los cambios se guardan en PostgreSQL y recargan el catálogo en caliente. Cree o edite
        agrupaciones, gráficas, labels y colores desde los botones de cada pestaña.
      </p>
    </div>
  );
}
