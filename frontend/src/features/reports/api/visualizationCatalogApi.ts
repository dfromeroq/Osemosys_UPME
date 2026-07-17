import { httpClient } from '@/shared/api/httpClient';

export type ApiMenuChart = {
  tipo: string;
  label: string;
  allowed?: string[];
  default_grouping?: string;
  is_capacity?: boolean;
  soporta_pareto?: boolean;
  has_loc?: boolean;
  sub_filtros?: string[];
  sub_label?: string;
};

export type ApiMenuSubmodule = {
  code: string;
  label: string;
  charts: ApiMenuChart[];
};

export type ApiMenuModule = {
  code: string;
  label: string;
  icon?: string | null;
  charts?: ApiMenuChart[];
  subs?: ApiMenuSubmodule[];
};

export type FilterMemberPublic = {
  id?: number;
  member_kind: string;
  operation: string;
  entity_type: string;
  match_mode: string;
  value: string | null;
  ref_group_id: number | null;
  sort_order: number;
};

export type FilterGroupPublic = {
  id: number;
  code: string;
  name: string;
  description?: string | null;
  filter_mode: string;
  is_system: boolean;
  members?: FilterMemberPublic[];
};

export type LabelPublic = {
  id: number;
  code: string;
  label_es: string;
  label_en?: string | null;
  category?: string | null;
};

export type LabelPagePublic = {
  items: LabelPublic[];
  total: number;
  page: number;
  page_size: number;
};

export type ColorPalettePublic = {
  id: number;
  group: string;
  key: string;
  color_hex: string;
  sort_order: number;
};

export type ChartConfigPublic = {
  id: number;
  tipo: string;
  label_titulo: string;
  variable_default: string;
  agrupar_por_default: string;
  color_fn_key: string;
  filtro_kind: string;
  is_visible: boolean;
};

export type ChartSubfilterPublic = {
  id?: number;
  code: string;
  display_label?: string | null;
  group_label?: string | null;
  filter_group_id?: number | null;
  sort_order: number;
  default_selected: boolean;
};

export type ChartConfigDetail = {
  id: number;
  tipo: string;
  module_id: number;
  submodule_id: number | null;
  label_titulo: string;
  label_figura: string | null;
  variable_default: string;
  filtro_kind: string;
  filtro_group_id: number | null;
  filtro_params_json: Record<string, unknown> | null;
  agrupar_por_default: string;
  agrupaciones_permitidas_json: string[] | null;
  color_fn_key: string;
  flags_json: Record<string, unknown> | null;
  msg_sin_datos: string | null;
  data_explorer_filters_json: Record<string, unknown> | null;
  is_visible: boolean;
  sort_order: number;
  subfilters: ChartSubfilterPublic[];
};

export type CatalogFormOptions = {
  grouping_axes: { value: string; label: string }[];
  color_fn_keys: string[];
  filtro_kinds: string[];
  filter_modes: string[];
  member_operations: string[];
  entity_types: string[];
  color_groups: string[];
  label_categories: string[];
  modules: { id: number; code: string; label: string }[];
  submodules: { id: number; module_id: number; code: string; label: string }[];
};

export async function fetchFormOptions(): Promise<CatalogFormOptions> {
  const { data } = await httpClient.get<CatalogFormOptions>('/visualization-catalog/form-options');
  return data;
}

export async function fetchVisualizationMenu(): Promise<ApiMenuModule[]> {
  const { data } = await httpClient.get<ApiMenuModule[]>('/visualization-catalog/menu');
  return data;
}

export async function fetchFilterGroups(): Promise<FilterGroupPublic[]> {
  const { data } = await httpClient.get<FilterGroupPublic[]>('/visualization-catalog/filter-groups');
  return data;
}

export async function fetchFilterGroup(code: string): Promise<FilterGroupPublic> {
  const { data } = await httpClient.get<FilterGroupPublic>(`/visualization-catalog/filter-groups/${encodeURIComponent(code)}`);
  return data;
}

export async function createFilterGroup(body: {
  code: string;
  name: string;
  description?: string | null;
  filter_mode: string;
  members?: FilterMemberPublic[];
}): Promise<FilterGroupPublic> {
  const { data } = await httpClient.post<FilterGroupPublic>('/visualization-catalog/filter-groups', body);
  return data;
}

export async function updateFilterGroup(
  code: string,
  body: { name?: string; description?: string | null; filter_mode?: string },
): Promise<FilterGroupPublic> {
  const { data } = await httpClient.patch<FilterGroupPublic>(
    `/visualization-catalog/filter-groups/${encodeURIComponent(code)}`,
    body,
  );
  return data;
}

export async function deleteFilterGroup(code: string): Promise<void> {
  await httpClient.delete(`/visualization-catalog/filter-groups/${encodeURIComponent(code)}`);
}

export async function replaceFilterGroupMembers(
  code: string,
  members: FilterMemberPublic[],
): Promise<FilterGroupPublic> {
  const { data } = await httpClient.put<FilterGroupPublic>(
    `/visualization-catalog/filter-groups/${encodeURIComponent(code)}/members`,
    { members },
  );
  return data;
}

export async function importFilterGroupMembers(
  code: string,
  text: string,
  mode: 'merge' | 'replace',
): Promise<FilterGroupPublic> {
  const { data } = await httpClient.post<FilterGroupPublic>(
    `/visualization-catalog/filter-groups/${encodeURIComponent(code)}/members/import`,
    { text, mode },
  );
  return data;
}

export async function fetchLabelsPaged(params: {
  q?: string;
  category?: string;
  page?: number;
  page_size?: number;
}): Promise<LabelPagePublic> {
  const query: Record<string, string | number> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 50,
  };
  if (params.q) query.q = params.q;
  if (params.category) query.category = params.category;
  const { data } = await httpClient.get<LabelPagePublic>('/visualization-catalog/labels', {
    params: query,
  });
  return data;
}

export async function createLabel(body: {
  code: string;
  label_es: string;
  label_en?: string | null;
  category?: string | null;
}): Promise<LabelPublic> {
  const { data } = await httpClient.post<LabelPublic>('/visualization-catalog/labels', body);
  return data;
}

export async function updateLabel(
  id: number,
  body: { label_es?: string; label_en?: string | null; category?: string | null },
): Promise<LabelPublic> {
  const { data } = await httpClient.patch<LabelPublic>(`/visualization-catalog/labels/${id}`, body);
  return data;
}

export async function deleteLabel(id: number): Promise<void> {
  await httpClient.delete(`/visualization-catalog/labels/${id}`);
}

export async function fetchVisualizationColors(group?: string): Promise<ColorPalettePublic[]> {
  const { data } = await httpClient.get<ColorPalettePublic[]>('/visualization-catalog/colors', {
    params: group ? { group } : undefined,
  });
  return data;
}

export async function createColor(body: {
  group: string;
  key: string;
  color_hex: string;
  sort_order?: number;
}): Promise<ColorPalettePublic> {
  const { data } = await httpClient.post<ColorPalettePublic>('/visualization-catalog/colors', body);
  return data;
}

export async function updateColor(
  id: number,
  body: { group?: string; key?: string; color_hex?: string; sort_order?: number },
): Promise<ColorPalettePublic> {
  const { data } = await httpClient.patch<ColorPalettePublic>(`/visualization-catalog/colors/${id}`, body);
  return data;
}

export async function deleteColor(id: number): Promise<void> {
  await httpClient.delete(`/visualization-catalog/colors/${id}`);
}

export async function fetchChartConfigs(): Promise<ChartConfigPublic[]> {
  const { data } = await httpClient.get<ChartConfigPublic[]>('/visualization-catalog/chart-configs');
  return data;
}

export async function fetchChartConfigDetail(tipo: string): Promise<ChartConfigDetail> {
  const { data } = await httpClient.get<ChartConfigDetail>(
    `/visualization-catalog/chart-configs/${encodeURIComponent(tipo)}`,
  );
  return data;
}

export type ChartConfigCreatePayload = Omit<ChartConfigDetail, 'id'>;

export async function createChartConfig(body: ChartConfigCreatePayload): Promise<ChartConfigDetail> {
  const { data } = await httpClient.post<ChartConfigDetail>('/visualization-catalog/chart-configs', body);
  return data;
}

export async function updateChartConfig(
  tipo: string,
  body: Partial<Omit<ChartConfigDetail, 'id' | 'tipo'>>,
): Promise<ChartConfigDetail> {
  const { data } = await httpClient.patch<ChartConfigDetail>(
    `/visualization-catalog/chart-configs/${encodeURIComponent(tipo)}`,
    body,
  );
  return data;
}

export async function deleteChartConfig(tipo: string): Promise<void> {
  await httpClient.delete(`/visualization-catalog/chart-configs/${encodeURIComponent(tipo)}`);
}

export async function fetchVisualizationLabels(category?: string): Promise<LabelPublic[]> {
  const params: { page: number; page_size: number; category?: string } = { page: 1, page_size: 200 };
  if (category) params.category = category;
  const page = await fetchLabelsPaged(params);
  return page.items;
}
