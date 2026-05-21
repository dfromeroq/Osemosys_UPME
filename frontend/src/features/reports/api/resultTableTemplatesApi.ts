import { httpClient } from '@/shared/api/httpClient';
import type { ResultTableTemplatePublic } from '@/types/domain';

export type ResultTableColumnRulePayload = {
  category_key: string;
  hidden?: boolean;
  sort_order?: number | null;
};

export type ResultTableTemplateCreatePayload = {
  name: string;
  display_title?: string | null;
  sort_order?: number;
  is_enabled?: boolean;
  tipo: string;
  un: string;
  sub_filtro?: string | null;
  loc?: string | null;
  variable?: string | null;
  agrupar_por?: string | null;
  region?: string | null;
  timeslice?: string | null;
  table_period_years?: number | null;
  table_cumulative?: boolean | null;
  custom_series_order?: string[] | null;
  y_axis_min?: number | null;
  y_axis_max?: number | null;
  column_rules?: ResultTableColumnRulePayload[];
};

export type ResultTableTemplateUpdatePayload = Partial<ResultTableTemplateCreatePayload>;

export type ResultTablePresentationSeriesOption = {
  value: string;
  code?: string | null;
};

export type ResultTablePresentationOptions = {
  series_options: ResultTablePresentationSeriesOption[];
  category_keys: string[];
  agrupar_por_resolved: string;
};

export const resultTableTemplatesApi = {
  listEnabled() {
    return httpClient
      .get<ResultTableTemplatePublic[]>('/result-table-templates')
      .then((r) => r.data);
  },

  listManage() {
    return httpClient
      .get<ResultTableTemplatePublic[]>('/result-table-templates/manage')
      .then((r) => r.data);
  },

  get(id: number) {
    return httpClient
      .get<ResultTableTemplatePublic>(`/result-table-templates/${id}`)
      .then((r) => r.data);
  },

  getPresentationOptions(params: {
    tipo: string;
    agrupar_por?: string | null;
    variable?: string | null;
  }) {
    const sp = new URLSearchParams();
    sp.set('tipo', params.tipo);
    if (params.agrupar_por != null && params.agrupar_por !== '') {
      sp.set('agrupar_por', params.agrupar_por);
    }
    if (params.variable != null && params.variable !== '') {
      sp.set('variable', params.variable);
    }
    return httpClient
      .get<ResultTablePresentationOptions>(
        `/result-table-templates/presentation-options?${sp.toString()}`,
      )
      .then((r) => r.data);
  },

  create(payload: ResultTableTemplateCreatePayload) {
    return httpClient
      .post<ResultTableTemplatePublic>('/result-table-templates', payload)
      .then((r) => r.data);
  },

  update(id: number, payload: ResultTableTemplateUpdatePayload) {
    return httpClient
      .patch<ResultTableTemplatePublic>(`/result-table-templates/${id}`, payload)
      .then((r) => r.data);
  },

  delete(id: number) {
    return httpClient.delete(`/result-table-templates/${id}`);
  },

  reorder(ids: number[]) {
    return httpClient
      .post<ResultTableTemplatePublic[]>('/result-table-templates/reorder', { ids })
      .then((r) => r.data);
  },
};
