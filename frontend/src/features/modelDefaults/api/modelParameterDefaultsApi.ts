import { httpClient } from "@/shared/api/httpClient";

export type ModelDefaultCatalogRow = {
  param_key: string;
  pyomo_name: string;
  index_dims: string;
  category: string;
  description: string | null;
  value_type: string;
  min_value: number | null;
  max_value: number | null;
  requires_storage: boolean;
  requires_udc: boolean;
  value: number;
};

export type ModelDefaultCatalogResponse = {
  version_id: number;
  is_active: boolean;
  rows: ModelDefaultCatalogRow[];
};

export type ModelDefaultVersionSummary = {
  id: number;
  created_at: string;
  created_by_username: string | null;
  comment: string | null;
  is_active: boolean;
};

export type ModelDefaultVersionListResponse = {
  active_version_id: number;
  versions: ModelDefaultVersionSummary[];
};

export type ModelDefaultVersionCreateResponse = {
  version_id: number;
  active_version_id: number;
};

const base = "/admin/model-parameter-defaults";

export const modelParameterDefaultsApi = {
  async getCatalog(versionId?: number) {
    const q = versionId != null ? `?version_id=${versionId}` : "";
    const { data } = await httpClient.get<ModelDefaultCatalogResponse>(
      `${base}/catalog${q}`,
    );
    return data;
  },

  async listVersions(limit = 50) {
    const { data } = await httpClient.get<ModelDefaultVersionListResponse>(
      `${base}/versions?limit=${limit}`,
    );
    return data;
  },

  async createVersion(payload: {
    items: { param_key: string; value: number }[];
    comment?: string | null;
  }) {
    const { data } = await httpClient.post<ModelDefaultVersionCreateResponse>(
      `${base}/versions`,
      payload,
    );
    return data;
  },
};
