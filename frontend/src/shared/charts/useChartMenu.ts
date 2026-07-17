import { useEffect, useState } from 'react';
import {
  fetchVisualizationMenu,
  type ApiMenuChart,
  type ApiMenuModule,
} from '@/features/reports/api/visualizationCatalogApi';
import { setChartMenuCache } from '@/shared/charts/chartMenuCache';

export interface ChartItem {
  id: string;
  label: string;
  isCapacity?: boolean;
  hasSub?: boolean;
  hasLoc?: boolean;
  subFiltros?: string[];
  subFiltroLabel?: string;
  allowedGroupings?: string[];
  defaultGrouping?: string;
  soportaPareto?: boolean;
  soportaPorcentaje?: boolean;
  soportaTabla?: boolean;
}

export interface Subsector {
  id: string;
  label: string;
  charts: ChartItem[];
}

export interface ChartMenuModule {
  id: string;
  emoji: string;
  label: string;
  subsectors?: Subsector[];
  charts?: ChartItem[];
}

function mapChart(c: ApiMenuChart): ChartItem {
  const item: ChartItem = {
    id: c.tipo,
    label: c.label,
    hasSub: Boolean(c.sub_filtros?.length),
    soportaTabla: true,
  };
  if (c.is_capacity === true) item.isCapacity = true;
  if (c.has_loc === true) item.hasLoc = true;
  if (c.sub_filtros && c.sub_filtros.length > 0) item.subFiltros = c.sub_filtros;
  if (c.sub_label) item.subFiltroLabel = c.sub_label;
  if (c.allowed && c.allowed.length > 0) item.allowedGroupings = c.allowed;
  if (c.default_grouping) item.defaultGrouping = c.default_grouping;
  if (c.soporta_pareto === true) item.soportaPareto = true;
  return item;
}

export function mapApiMenuToModules(api: ApiMenuModule[]): ChartMenuModule[] {
  return api.map((m) => {
    const mod: ChartMenuModule = {
      id: m.code,
      emoji: m.icon ?? '📊',
      label: m.label,
    };
    if (m.charts && m.charts.length > 0) {
      mod.charts = m.charts.map(mapChart);
    }
    if (m.subs && m.subs.length > 0) {
      mod.subsectors = m.subs.map((s) => ({
        id: s.code,
        label: s.label,
        charts: s.charts.map(mapChart),
      }));
    }
    return mod;
  });
}

export function useChartMenu(): {
  menu: ChartMenuModule[];
  loading: boolean;
  error: string | null;
} {
  const [menu, setMenu] = useState<ChartMenuModule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchVisualizationMenu()
      .then((api) => {
        if (!cancelled) {
          const mapped = mapApiMenuToModules(api);
          setMenu(mapped);
          setChartMenuCache(mapped);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Error cargando menú');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { menu, loading, error };
}
