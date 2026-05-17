import { httpClient } from '@/shared/api/httpClient';
import type { ChartSeriesConfigPublic, ChartTypeInfo } from '@/types/domain';

export const chartSeriesConfigApi = {
  listChartTypes() {
    return httpClient
      .get<ChartTypeInfo[]>('/chart-series-config/chart-types')
      .then((r) => r.data);
  },

  list(tipo: string, agrupar_por: string) {
    const sp = new URLSearchParams();
    sp.set('tipo', tipo);
    sp.set('agrupar_por', agrupar_por);
    return httpClient
      .get<ChartSeriesConfigPublic[]>(`/chart-series-config?${sp.toString()}`)
      .then((r) => r.data);
  },

  populate(payload: { tipo: string; agrupar_por?: string | null; variable?: string | null }) {
    return httpClient
      .post<ChartSeriesConfigPublic[]>('/chart-series-config/populate', payload)
      .then((r) => r.data);
  },

  populateAll() {
    return httpClient
      .post<{ inserted_rows: number }>('/chart-series-config/populate-all')
      .then((r) => r.data);
  },

  createRow(payload: {
    tipo: string;
    agrupar_por?: string | null;
    series_code: string;
    display_name?: string | null;
    color?: string | null;
    hidden?: boolean;
    sort_index?: number | null;
    group_key?: string | null;
    notes?: string | null;
  }) {
    return httpClient
      .post<ChartSeriesConfigPublic>('/chart-series-config/row', payload)
      .then((r) => r.data);
  },

  patch(
    id: number,
    payload: Partial<{
      display_name: string;
      color: string | null;
      hidden: boolean;
      sort_index: number;
      group_key: string | null;
    }>,
  ) {
    return httpClient
      .patch<ChartSeriesConfigPublic>(`/chart-series-config/${id}`, payload)
      .then((r) => r.data);
  },

  delete(id: number) {
    return httpClient.delete(`/chart-series-config/${id}`);
  },

  reorder(ids: number[]) {
    return httpClient
      .post<ChartSeriesConfigPublic[]>('/chart-series-config/reorder', { ids })
      .then((r) => r.data);
  },
};
