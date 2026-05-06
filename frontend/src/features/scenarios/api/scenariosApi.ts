/**
 * API de escenarios: CRUD, permisos, valores OSeMOSYS, importación Excel, solicitudes de cambio.
 * Incluye getEffectivePermission para determinar acceso según política y permisos explícitos.
 */
import { httpClient } from "@/shared/api/httpClient";
import type { PaginatedResponse } from "@/shared/api/pagination";
import type {
  ChangeRequest,
  ChangeRequestStatus,
  DataQualityReport,
  ParameterValue,
  Scenario,
  ScenarioEditPolicy,
  ScenarioPermissionScope,
  ScenarioPermission,
  ScenarioOperationJob,
  ScenarioOperationLog,
  ScenarioTag,
  ScenarioTagCategory,
  ScenarioTagConflict,
  SimulationType,
  User,
} from "@/types/domain";
import type { OfficialImportResult } from "@/features/officialImport/api/officialImportApi";

/** Permisos efectivos de un usuario sobre un escenario (owner, edit direct, propose, manage values) */
export type ScenarioAccess = {
  isOwner: boolean;
  can_edit_direct: boolean;
  can_propose: boolean;
  can_manage_values: boolean;
};

export type OsemosysValueRow = {
  id: number;
  id_scenario: number;
  param_name: string;
  region_name: string | null;
  technology_name: string | null;
  fuel_name: string | null;
  emission_name: string | null;
  udc_name: string | null;
  year: number | null;
  value: number;
};

export type OsemosysValuesPage = {
  items: OsemosysValueRow[];
  total: number;
  offset: number;
  limit: number;
};

export type OsemosysWideCell = {
  id: number;
  value: number;
};

export type OsemosysWideRow = {
  group_key: string;
  param_name: string;
  region_name: string | null;
  technology_name: string | null;
  fuel_name: string | null;
  emission_name: string | null;
  udc_name: string | null;
  cells: Record<string, OsemosysWideCell>;
};

export type OsemosysValuesWidePage = {
  items: OsemosysWideRow[];
  total: number;
  offset: number;
  limit: number;
  years: number[];
  has_scalar: boolean;
};

export type OsemosysWideFacets = {
  param_names: string[];
  region_names: string[];
  technology_names: string[];
  fuel_names: string[];
  emission_names: string[];
  udc_names: string[];
};

export type OsemosysWideFilters = {
  param_names?: string[];
  region_names?: string[];
  technology_names?: string[];
  fuel_names?: string[];
  emission_names?: string[];
  udc_names?: string[];
  /** Reglas sobre años, serializadas como `year:op[:value]` separados por coma. */
  year_rules?: string;
};

export type ScenarioDeleteChild = {
  id: number;
  name: string;
  owner: string;
  edit_policy: ScenarioEditPolicy;
  simulation_type: SimulationType;
  child_count: number;
  simulation_job_count: number;
  created_at: string;
};

export type ScenarioDeleteImpact = {
  scenario_id: number;
  scenario_name: string;
  direct_children: ScenarioDeleteChild[];
};

/** Sentinel que el backend usa para representar "(vacío)" en las listas. */
export const WIDE_NULL_SENTINEL = "__NULL__";

export type YearRuleOp = "gt" | "lt" | "gte" | "lte" | "eq" | "ne" | "nonzero" | "zero";
export type YearRule = { op: YearRuleOp; value: number | null };

export function serializeYearRules(rules: Record<string, YearRule>): string | undefined {
  const parts: string[] = [];
  for (const [year, rule] of Object.entries(rules)) {
    if (!rule || !rule.op) continue;
    if (rule.op === "nonzero" || rule.op === "zero") {
      parts.push(`${year}:${rule.op}`);
    } else if (rule.value !== null && Number.isFinite(rule.value)) {
      parts.push(`${year}:${rule.op}:${rule.value}`);
    }
  }
  return parts.length ? parts.join(",") : undefined;
}

export type OsemosysParamAuditEntry = {
  id: number;
  param_name: string;
  id_osemosys_param_value: number | null;
  action: string;
  old_value: number | null;
  new_value: number | null;
  dimensions_json: Record<string, unknown> | null;
  source: string;
  changed_by: string;
  created_at: string;
};

export type OsemosysParamAuditPage = {
  items: OsemosysParamAuditEntry[];
  total: number;
  offset: number;
  limit: number;
};

export type ScenarioExcelImportResponse = {
  scenario: Scenario;
  import_result: OfficialImportResult;
};

export type ScenarioExcelUpdateResponse = {
  updated: number;
  inserted: number;
  skipped: number;
  not_found: number;
  total_rows_read: number;
  warnings: string[];
};

export type SandContribution = {
  archivo: string;
  total_cambios: number;
  n_nuevas: number;
  n_eliminadas: number;
  n_modificadas: number;
  parametros: string[];
  tecnologias: string[];
  fuels: string[];
};

/** Muestra de fila/celda no verificada (doble lectura del exportado). */
export type SandExportVerificationFaltante = {
  tipo?: string;
  Parameter?: string;
  TECHNOLOGY?: string;
  FUEL?: string;
  columna?: string;
  valor_esperado?: unknown;
  valor_actual?: unknown;
};

export type SandExportVerificationPerFile = {
  archivo: string;
  ok: boolean;
  n_verificadas_nuevas: number;
  n_verificadas_modif: number;
  n_omitidas_drop: number;
  n_faltantes: number;
};

/** Doble verificación del archivo integrado releído desde el Excel exportado. */
export type SandExportVerification = {
  ok: boolean;
  /** false si hay conflictos: el ZIP no incluye el integrado; la verificación es sobre el generado en servidor. */
  applies_to_download: boolean;
  verification_error?: string | null;
  total_nuevas_verificadas: number;
  total_modificadas_verificadas: number;
  total_omitidas_drop: number;
  total_faltantes: number;
  per_file: SandExportVerificationPerFile[];
  faltantes_muestra?: SandExportVerificationFaltante[];
};

export type SandIntegrationSummary = {
  total_filas: number;
  contribuciones: SandContribution[];
  conflictos_count: number;
  /** Detalle de conflictos entre archivos nuevos (misma estructura que la hoja Conflictos del Excel). */
  conflictos?: Record<string, unknown>[];
  resumen: string;
  warnings: string[];
  errors: string[];
  has_log?: boolean;
  log_line_count?: number;
  has_cambios_xlsx?: boolean;
  /** true cuando el ZIP trae conflictos_integracion.xlsx (disputas entre archivos nuevos). */
  has_conflictos_xlsx?: boolean;
  /** true cuando el backend no generó Excel integrado (solo log de error). */
  integration_failed?: boolean;
  export_verification?: SandExportVerification | null;
};

/** Respuesta JSON de verificación manual (sin integrar en servidor). */
export type VerifySandIntegrationResponse = {
  standalone: boolean;
  export_verification: SandExportVerification;
};

export type ExcelUpdatePreviewRow = {
  preview_id: string;
  action: "update" | "insert";
  row_id: number | null;
  param_name: string;
  region_name: string | null;
  technology_name: string | null;
  fuel_name: string | null;
  emission_name: string | null;
  timeslice_code: string | null;
  mode_of_operation_code: string | null;
  season_code: string | null;
  daytype_code: string | null;
  dailytimebracket_code: string | null;
  storage_set_code: string | null;
  udc_set_code: string | null;
  year: number | null;
  old_value: number | null;
  new_value: number;
};

export type ScenarioExcelPreviewResponse = {
  changes: ExcelUpdatePreviewRow[];
  not_found: number;
  total_rows_read: number;
  warnings: string[];
};

export type UdcMultiplierEntry = {
  type: "TotalCapacity" | "NewCapacity" | "Activity";
  tech_dict: Record<string, number>;
};

export type UdcConfig = {
  enabled: boolean;
  multipliers: UdcMultiplierEntry[];
  tag_value: 0 | 1;
};

type ScenarioListParams = {
  busqueda?: string;
  owner?: string;
  edit_policy?: ScenarioEditPolicy;
  permission_scope?: ScenarioPermissionScope;
  cantidad?: number;
  offset?: number;
  /** Solo surte efecto con rol can_manage_scenarios; incluye OWNER_ONLY ajenos. */
  include_private?: boolean;
  /** Filtros multiselect (repiten query param al serializar). */
  owners?: string[];
  edit_policies?: ScenarioEditPolicy[];
  simulation_types?: SimulationType[];
  tag_ids?: number[];
};

export type ScenarioFacetsResponse = {
  owners: string[];
  edit_policies: string[];
  simulation_types: string[];
  tags: Array<{
    id: number;
    name: string;
    color: string;
    category_id: number;
    category_name: string;
    hierarchy_level: number;
  }>;
};

/**
 * Decodifica JSON en Base64 URL-safe. El backend codifica UTF-8; hay que pasar por TextDecoder
 * para no interpretar bytes UTF-8 como Latin-1 (mojibake: integraciÃ³n → integración).
 */
function decodeBase64JsonHeader<T>(rawHeader: string | undefined, fallback: T): T {
  if (!rawHeader) return fallback;
  try {
    const normalized = rawHeader.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const binary = atob(padded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    const text = new TextDecoder("utf-8").decode(bytes);
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}

/** Serializa arrays como ?owners=a&owners=b (formato que FastAPI espera). */
function repeatArrayParamsSerializer(params: Record<string, unknown>): string {
  const out = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      for (const v of value) {
        if (v === undefined || v === null) continue;
        out.append(key, String(v));
      }
    } else {
      out.append(key, String(value));
    }
  }
  return out.toString();
}

async function listScenarios(params: ScenarioListParams = {}) {
  const { data } = await httpClient.get<PaginatedResponse<Scenario>>(
    "/scenarios",
    { params, paramsSerializer: repeatArrayParamsSerializer },
  );
  return data;
}

async function listScenarioFacets(
  params: { include_private?: boolean } = {},
): Promise<ScenarioFacetsResponse> {
  const { data } = await httpClient.get<ScenarioFacetsResponse>(
    "/scenarios/facets",
    { params },
  );
  return data;
}

async function listScenarioTags(categoryId?: number) {
  const params = categoryId != null ? { category_id: categoryId } : undefined;
  const { data } = await httpClient.get<ScenarioTag[]>("/scenario-tags", { params });
  return data;
}

async function listScenarioTagCategories() {
  const { data } = await httpClient.get<ScenarioTagCategory[]>(
    "/scenario-tag-categories",
  );
  return data;
}

/** Error tipado que el UI debe interceptar para mostrar el diálogo de conflicto. */
export class TagAssignmentConflictError extends Error {
  conflict: ScenarioTagConflict;
  constructor(conflict: ScenarioTagConflict) {
    super("tag_assignment_conflict");
    this.conflict = conflict;
  }
}

/**
 * Extrae el objeto `conflict` de un error 409 estructurado devuelto por el backend.
 * Soporta tanto AxiosError crudo como ApiError normalizado por el interceptor
 * global del httpClient (que mueve el payload original a `details.response`).
 */
function extractTagAssignmentConflict(
  err: unknown,
): ScenarioTagConflict | null {
  if (!err || typeof err !== "object") return null;
  const e = err as {
    status?: number;
    response?: { status?: number; data?: { detail?: unknown } };
    details?: { response?: { detail?: unknown } };
  };
  const status = e.response?.status ?? e.status;
  if (status !== 409) return null;
  const detail =
    (e.response?.data?.detail as unknown) ??
    (e.details?.response as { detail?: unknown } | undefined)?.detail;
  if (!detail || typeof detail !== "object") return null;
  const d = detail as { code?: string; conflict?: ScenarioTagConflict };
  if (d.code === "tag_assignment_conflict" && d.conflict) {
    return d.conflict;
  }
  return null;
}

export type ScenarioDataQualityResponse = {
  scenario_id: number;
  data_quality_warnings: DataQualityReport | Record<string, never>;
};

export type FixNumericPrecisionResponse = {
  scenario_id: number;
  fixed_n_tuples: number;
  before: { n_real_conflict: number; n_numeric_precision: number };
  after: { n_real_conflict: number; n_numeric_precision: number };
  data_quality_warnings: DataQualityReport;
};


export const scenariosApi = {
  listScenarios,
  listScenarioFacets,
  listScenarioTags,
  listScenarioTagCategories,

  /** GET /scenarios/{id}/data-quality — reporte persistido. */
  getDataQuality: (scenarioId: number) =>
    httpClient
      .get<ScenarioDataQualityResponse>(`/scenarios/${scenarioId}/data-quality`)
      .then((r) => r.data),

  /** POST /scenarios/{id}/data-quality/refresh — re-detecta y persiste. */
  refreshDataQuality: (scenarioId: number) =>
    httpClient
      .post<ScenarioDataQualityResponse>(
        `/scenarios/${scenarioId}/data-quality/refresh`,
      )
      .then((r) => r.data),

  /** POST /scenarios/{id}/data-quality/fix-numeric-precision — auto-fix decimal. */
  fixNumericPrecisionConflicts: (scenarioId: number) =>
    httpClient
      .post<FixNumericPrecisionResponse>(
        `/scenarios/${scenarioId}/data-quality/fix-numeric-precision`,
      )
      .then((r) => r.data),

  createScenarioTag: (input: {
    category_id: number;
    name: string;
    color: string;
    sort_order?: number;
    is_exclusive_combination?: boolean;
  }) => httpClient.post<ScenarioTag>("/scenario-tags", input).then((r) => r.data),

  updateScenarioTag: (
    id: number,
    input: {
      category_id?: number;
      name?: string;
      color?: string;
      sort_order?: number;
      is_exclusive_combination?: boolean;
    },
  ) => httpClient.patch<ScenarioTag>(`/scenario-tags/${id}`, input).then((r) => r.data),

  deleteScenarioTag: (id: number) => httpClient.delete(`/scenario-tags/${id}`),

  createScenarioTagCategory: (input: {
    name: string;
    hierarchy_level?: number;
    sort_order?: number;
    max_tags_per_scenario?: number | null;
    is_exclusive_combination?: boolean;
    default_color?: string;
  }) =>
    httpClient
      .post<ScenarioTagCategory>("/scenario-tag-categories", input)
      .then((r) => r.data),

  updateScenarioTagCategory: (
    id: number,
    input: {
      name?: string;
      hierarchy_level?: number;
      sort_order?: number;
      max_tags_per_scenario?: number | null;
      is_exclusive_combination?: boolean;
      default_color?: string;
    },
  ) =>
    httpClient
      .patch<ScenarioTagCategory>(`/scenario-tag-categories/${id}`, input)
      .then((r) => r.data),

  deleteScenarioTagCategory: (id: number) =>
    httpClient.delete(`/scenario-tag-categories/${id}`),

  /**
   * Asigna una etiqueta a un escenario.
   * Si el backend detecta un conflicto (409 con detail.code === "tag_assignment_conflict"),
   * lanza `TagAssignmentConflictError` con el detalle del otro escenario.
   * Pasa `force=true` para confirmar y quitar la etiqueta del otro escenario.
   *
   * NOTE: httpClient tiene un interceptor que convierte errores axios en ApiError
   * (perdiendo la estructura `response.data.detail` como objeto anidado). Lo
   * recuperamos desde `ApiError.details.response.detail`.
   */
  async assignTagToScenario(
    scenarioId: number,
    tagId: number,
    force = false,
  ): Promise<ScenarioTag[]> {
    try {
      const { data } = await httpClient.post<ScenarioTag[]>(
        `/scenarios/${scenarioId}/tags`,
        { tag_id: tagId, force },
      );
      return data;
    } catch (err: unknown) {
      const conflict = extractTagAssignmentConflict(err);
      if (conflict) throw new TagAssignmentConflictError(conflict);
      throw err;
    }
  },

  removeTagFromScenario: (scenarioId: number, tagId: number) =>
    httpClient
      .delete<ScenarioTag[]>(`/scenarios/${scenarioId}/tags/${tagId}`)
      .then((r) => r.data),

  getScenarioById: (id: number) => httpClient.get<Scenario>(`/scenarios/${id}`).then((r) => r.data),

  /** Descarga el escenario en Excel (`sand` o `raw`). */
  async downloadScenarioExcel(
    scenarioId: number,
    format: "sand" | "raw" = "sand",
  ): Promise<{ blob: Blob; filename: string }> {
    const { data, headers } = await httpClient.get(`/scenarios/${scenarioId}/export-excel`, {
      responseType: "blob",
      params: { format },
    });
    const blob = data as Blob;
    const disposition = headers["content-disposition"];
    let filename = `scenario_${scenarioId}_Parameters_${format.toUpperCase()}.xlsx`;
    if (typeof disposition === "string") {
      const match = /filename="?([^";\n]+)"?/i.exec(disposition);
      if (match?.[1]) filename = match[1].trim();
    }
    return { blob, filename };
  },

  createScenario: (input: {
    name: string;
    description: string;
    edit_policy: ScenarioEditPolicy;
    simulation_type: SimulationType;
    is_template?: boolean;
    tag_ids?: number[];
  }) => httpClient.post<Scenario>("/scenarios", input).then((r) => r.data),

  listPermissions: (scenarioId: number) =>
    httpClient.get<ScenarioPermission[]>(`/scenarios/${scenarioId}/permissions`).then((r) => r.data),
  upsertPermission: (
    scenarioId: number,
    input: {
      user_id?: string;
      user_identifier?: string;
      can_edit_direct: boolean;
      can_propose: boolean;
      can_manage_values: boolean;
    },
  ) => httpClient.post<ScenarioPermission>(`/scenarios/${scenarioId}/permissions`, input).then((r) => r.data),

  async createScenarioFromExcel(
    input: {
      file: File;
      sheet_name: string;
      scenario_name: string;
      description?: string;
      edit_policy: ScenarioEditPolicy;
      simulation_type: SimulationType;
      tag_ids?: number[];
      include_udc_reserve_margin?: boolean;
      /** Default true: colapsar/agregar timeslices como en importaciones anteriores. */
      collapse_timeslices?: boolean;
    },
    onUploadProgress?: (percent: number) => void,
    onUploadDone?: () => void,
    signal?: AbortSignal,
  ): Promise<ScenarioExcelImportResponse> {
    const form = new FormData();
    form.append("file", input.file);
    form.append("sheet_name", input.sheet_name);
    form.append("scenario_name", input.scenario_name);
    form.append("edit_policy", input.edit_policy);
    form.append("simulation_type", input.simulation_type);
    if (input.description?.trim()) form.append("description", input.description.trim());
    if (input.tag_ids && input.tag_ids.length)
      form.append("tag_ids", input.tag_ids.join(","));
    form.append("include_udc_reserve_margin", input.include_udc_reserve_margin ? "true" : "false");
    form.append(
      "collapse_timeslices",
      input.collapse_timeslices !== false ? "true" : "false",
    );

    const { data } = await httpClient.post<ScenarioExcelImportResponse>(
      "/scenarios/import-excel",
      form,
      {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 1_800_000,
        ...(signal ? { signal } : {}),
        onUploadProgress(event) {
          if (event.total && onUploadProgress) {
            onUploadProgress(Math.round((event.loaded * 100) / event.total));
          }
        },
      },
    );
    onUploadDone?.();
    return data;
  },

  async createScenarioFromCsv(
    input: {
      file: File;
      scenario_name: string;
      description?: string;
      edit_policy: ScenarioEditPolicy;
      simulation_type: SimulationType;
      tag_ids?: number[];
    },
    onUploadProgress?: (percent: number) => void,
    signal?: AbortSignal,
  ): Promise<Scenario> {
    const form = new FormData();
    form.append("csv_zip", input.file);
    form.append("scenario_name", input.scenario_name);
    form.append("edit_policy", input.edit_policy);
    form.append("simulation_type", input.simulation_type);
    if (input.description?.trim()) form.append("description", input.description.trim());
    if (input.tag_ids && input.tag_ids.length)
      form.append("tag_ids", input.tag_ids.join(","));
    const { data } = await httpClient.post<Scenario>("/scenarios/import-csv", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 1_800_000,
      ...(signal ? { signal } : {}),
      onUploadProgress(event) {
        if (event.total && onUploadProgress) {
          onUploadProgress(Math.round((event.loaded * 100) / event.total));
        }
      },
    });
    return data;
  },

  async concatenateSand(
    input: {
      baseFile: File;
      newFiles: File[];
      dropTechs?: string;
      dropFuels?: string;
      /** Si es true, la respuesta es un ZIP con el Excel y `integracion_sand_log.txt`. */
      includeLogTxt?: boolean;
    },
    onUploadProgress?: (percent: number) => void,
    signal?: AbortSignal,
  ): Promise<{ blob: Blob; filename: string; summary: SandIntegrationSummary }> {
    const form = new FormData();
    form.append("base_file", input.baseFile);
    for (const file of input.newFiles) {
      form.append("new_files", file);
    }
    if (input.dropTechs?.trim()) form.append("drop_techs", input.dropTechs.trim());
    if (input.dropFuels?.trim()) form.append("drop_fuels", input.dropFuels.trim());
    if (input.includeLogTxt) form.append("include_log_txt", "true");

    const { data, headers } = await httpClient.post("/scenarios/concatenate-sand", form, {
      responseType: "blob",
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 1_800_000,
      ...(signal ? { signal } : {}),
      onUploadProgress(event) {
        if (event.total && onUploadProgress) {
          onUploadProgress(Math.round((event.loaded * 100) / event.total));
        }
      },
    });

    const blob = data as Blob;
    const disposition = headers["content-disposition"];
    let filename = "SAND_integrado.xlsx";
    if (typeof disposition === "string") {
      const match = /filename="?([^";\n]+)"?/i.exec(disposition);
      if (match?.[1]) filename = match[1].trim();
    }

    const summary = decodeBase64JsonHeader<SandIntegrationSummary>(
      headers["x-sand-integration-summary"],
      {
        total_filas: 0,
        contribuciones: [],
        conflictos_count: 0,
        conflictos: [],
        resumen: "",
        warnings: [],
        errors: [],
        has_log: false,
        log_line_count: 0,
        has_cambios_xlsx: false,
        has_conflictos_xlsx: false,
        integration_failed: false,
        export_verification: null,
      },
    );

    return { blob, filename, summary };
  },

  async verifySandIntegration(
    input: {
      baseFile: File;
      integratedFile: File;
      newFiles: File[];
      dropTechs?: string;
      dropFuels?: string;
    },
    onUploadProgress?: (percent: number) => void,
    signal?: AbortSignal,
  ): Promise<VerifySandIntegrationResponse> {
    const form = new FormData();
    form.append("base_file", input.baseFile);
    form.append("integrated_file", input.integratedFile);
    for (const file of input.newFiles) {
      form.append("new_files", file);
    }
    if (input.dropTechs?.trim()) form.append("drop_techs", input.dropTechs.trim());
    if (input.dropFuels?.trim()) form.append("drop_fuels", input.dropFuels.trim());

    const { data } = await httpClient.post<VerifySandIntegrationResponse>(
      "/scenarios/verify-sand-integration",
      form,
      {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 1_800_000,
        ...(signal ? { signal } : {}),
        onUploadProgress(event) {
          if (event.total && onUploadProgress) {
            onUploadProgress(Math.round((event.loaded * 100) / event.total));
          }
        },
      },
    );
    return data;
  },

  /** Calcula permisos efectivos: owner tiene todo; OPEN da acceso amplio; RESTRICTED usa permisos explícitos */
  async getEffectivePermission(scenario: Scenario, currentUser: User): Promise<ScenarioAccess> {
    if (scenario.effective_access) {
      return {
        isOwner: scenario.effective_access.is_owner,
        can_edit_direct: scenario.effective_access.can_edit_direct,
        can_propose: scenario.effective_access.can_propose,
        can_manage_values: scenario.effective_access.can_manage_values,
      };
    }

    const isOwner = scenario.owner === currentUser.username;
    if (isOwner) {
      return {
        isOwner: true,
        can_edit_direct: true,
        can_propose: true,
        can_manage_values: true,
      };
    }

    const openPolicyAccess =
      scenario.edit_policy === "OPEN"
        ? {
            isOwner: false,
            can_edit_direct: false,
            can_propose: true,
            can_manage_values: true,
          }
        : {
            isOwner: false,
            can_edit_direct: false,
            can_propose: false,
            can_manage_values: false,
          };

    try {
      const permissions = await scenariosApi.listPermissions(scenario.id);
      const match =
        permissions.find((p) => p.user_id === currentUser.id) ??
        permissions.find((p) => p.user_identifier === `user:${currentUser.username}`) ??
        null;
      if (!match) return openPolicyAccess;
      return {
        isOwner: false,
        can_edit_direct: match.can_edit_direct,
        can_propose: match.can_propose,
        can_manage_values: match.can_manage_values,
      };
    } catch {
      return openPolicyAccess;
    }
  },

  updateScenario: (
    scenarioId: number,
    input: {
      name?: string;
      description?: string | null;
      edit_policy?: ScenarioEditPolicy;
      simulation_type?: SimulationType;
      tag_ids?: number[];
    },
  ) => httpClient.patch<Scenario>(`/scenarios/${scenarioId}`, input).then((r) => r.data),

  listDefaults: () =>
    httpClient.get<ParameterValue[]>('/parameter-values').then((r) => r.data),
  listOsemosysValues: (
    scenarioId: number,
    params: {
      param_name?: string;
      param_name_exact?: boolean;
      year?: number;
      search?: string;
      offset?: number;
      limit?: number;
    } = {},
  ) =>
    httpClient
      .get<OsemosysValuesPage>(`/scenarios/${scenarioId}/osemosys-values`, { params })
      .then((r) => r.data),
  listOsemosysValuesWide: (
    scenarioId: number,
    params: {
      param_name?: string;
      param_name_exact?: boolean;
      search?: string;
      offset?: number;
      limit?: number;
    } & OsemosysWideFilters = {},
  ) => {
    // Serializa listas como CSV; axios de otro modo emite `?k[]=a&k[]=b`.
    const { param_names, region_names, technology_names, fuel_names, emission_names, udc_names, ...rest } = params;
    const csv = (v?: string[]) => (v && v.length ? v.join(",") : undefined);
    return httpClient
      .get<OsemosysValuesWidePage>(`/scenarios/${scenarioId}/osemosys-values/wide`, {
        params: {
          ...rest,
          ...(csv(param_names) ? { param_names: csv(param_names) } : {}),
          ...(csv(region_names) ? { region_names: csv(region_names) } : {}),
          ...(csv(technology_names) ? { technology_names: csv(technology_names) } : {}),
          ...(csv(fuel_names) ? { fuel_names: csv(fuel_names) } : {}),
          ...(csv(emission_names) ? { emission_names: csv(emission_names) } : {}),
          ...(csv(udc_names) ? { udc_names: csv(udc_names) } : {}),
        },
      })
      .then((r) => r.data);
  },
  listOsemosysWideFacets: (
    scenarioId: number,
    params: {
      param_name?: string;
      param_name_exact?: boolean;
      search?: string;
      limit_per_column?: number;
    } & OsemosysWideFilters = {},
  ) => {
    const { param_names, region_names, technology_names, fuel_names, emission_names, udc_names, year_rules, ...rest } = params;
    const csv = (v?: string[]) => (v && v.length ? v.join(",") : undefined);
    return httpClient
      .get<OsemosysWideFacets>(`/scenarios/${scenarioId}/osemosys-values/wide/facets`, {
        params: {
          ...rest,
          ...(csv(param_names) ? { param_names: csv(param_names) } : {}),
          ...(csv(region_names) ? { region_names: csv(region_names) } : {}),
          ...(csv(technology_names) ? { technology_names: csv(technology_names) } : {}),
          ...(csv(fuel_names) ? { fuel_names: csv(fuel_names) } : {}),
          ...(csv(emission_names) ? { emission_names: csv(emission_names) } : {}),
          ...(csv(udc_names) ? { udc_names: csv(udc_names) } : {}),
          ...(year_rules ? { year_rules } : {}),
        },
      })
      .then((r) => r.data);
  },
  listOsemosysParamAudit: (
    scenarioId: number,
    paramName: string,
    params: { offset?: number; limit?: number } = {},
  ) =>
    httpClient
      .get<OsemosysParamAuditPage>(`/scenarios/${scenarioId}/osemosys-param-audit`, {
        params: { param_name: paramName, ...params },
      })
      .then((r) => r.data),
  createOsemosysValue: (
    scenarioId: number,
    input: {
      param_name: string;
      region_name?: string;
      technology_name?: string;
      fuel_name?: string;
      emission_name?: string;
      udc_name?: string;
      year?: number;
      value: number;
    },
  ) => httpClient.post<OsemosysValueRow>(`/scenarios/${scenarioId}/osemosys-values`, input).then((r) => r.data),
  updateOsemosysValue: (
    scenarioId: number,
    valueId: number,
    input: {
      param_name: string;
      region_name?: string;
      technology_name?: string;
      fuel_name?: string;
      emission_name?: string;
      udc_name?: string;
      year?: number;
      value: number;
    },
  ) =>
    httpClient
      .put<OsemosysValueRow>(`/scenarios/${scenarioId}/osemosys-values/${valueId}`, input)
      .then((r) => r.data),
  deactivateOsemosysValue: (scenarioId: number, valueId: number) =>
    httpClient.delete(`/scenarios/${scenarioId}/osemosys-values/${valueId}`),
  createValue: (input: {
    id_parameter: number;
    id_region: number;
    id_solver?: number;
    id_technology?: number;
    id_fuel?: number;
    id_emission?: number;
    mode_of_operation?: boolean;
    year: number;
    value: number;
    unit?: string;
  }) => httpClient.post<ParameterValue>('/parameter-values', input).then((r) => r.data),
  updateValue: (id: number, patch: { value: number; unit?: string }) =>
    httpClient.put<ParameterValue>(`/parameter-values/${id}`, patch).then((r) => r.data),

  createChangeRequest: (input: {
    id_osemosys_param_value: number;
    new_value: number;
  }) => httpClient.post<ChangeRequest>("/change-requests", input).then((r) => r.data),

  listMyChangeRequests: () =>
    httpClient.get<ChangeRequest[]>("/change-requests/mine").then((r) => r.data),
  listPendingChangeRequests: (scenarioId: number) =>
    httpClient.get<ChangeRequest[]>(`/change-requests/pending/${scenarioId}`).then((r) => r.data),

  reviewChangeRequest: (id: number, status: Exclude<ChangeRequestStatus, "PENDING">) =>
    status === "APPROVED"
      ? httpClient.post<ChangeRequest>(`/change-requests/${id}/approve`).then((r) => r.data)
      : httpClient.post<ChangeRequest>(`/change-requests/${id}/reject`).then((r) => r.data),

  deleteScenario: (scenarioId: number) =>
    httpClient.delete(`/scenarios/${scenarioId}`),

  getScenarioDeleteImpact: (scenarioId: number) =>
    httpClient
      .get<ScenarioDeleteImpact>(`/scenarios/${scenarioId}/delete-impact`)
      .then((r) => r.data),

  detachScenarioChildren: (scenarioId: number, childIds: number[]) =>
    httpClient
      .post<{ detached_child_ids: number[] }>(`/scenarios/${scenarioId}/children/detach`, {
        child_ids: childIds,
      })
      .then((r) => r.data),

  cloneScenario: (scenarioId: number, input: { name: string; description?: string; edit_policy?: ScenarioEditPolicy }) =>
    httpClient.post<Scenario>(`/scenarios/${scenarioId}/clone`, input, { timeout: 600_000 }).then((r) => r.data),

  cloneScenarioAsync: (
    scenarioId: number,
    input: { name: string; description?: string; edit_policy?: ScenarioEditPolicy },
  ) =>
    httpClient
      .post<ScenarioOperationJob>(`/scenarios/${scenarioId}/clone-async`, input, { timeout: 600_000 })
      .then((r) => r.data),

  listScenarioOperations: (params: {
    status_filter?: string;
    operation_type?: string;
    scenario_id?: number;
    cantidad?: number;
    offset?: number;
  } = {}) =>
    httpClient.get<PaginatedResponse<ScenarioOperationJob>>("/scenarios/operations", { params }).then((r) => r.data),

  getScenarioOperationById: (jobId: number) =>
    httpClient.get<ScenarioOperationJob>(`/scenarios/operations/${jobId}`).then((r) => r.data),

  listScenarioOperationLogs: (jobId: number, params: { cantidad?: number; offset?: number } = {}) =>
    httpClient
      .get<PaginatedResponse<ScenarioOperationLog>>(`/scenarios/operations/${jobId}/logs`, { params })
      .then((r) => r.data),

  async updateScenarioFromExcel(
    scenarioId: number,
    input: { file: File; sheet_name: string; collapse_timeslices?: boolean },
    onUploadProgress?: (percent: number) => void,
    signal?: AbortSignal,
  ): Promise<ScenarioExcelUpdateResponse> {
    const form = new FormData();
    form.append("file", input.file);
    form.append("sheet_name", input.sheet_name);
    form.append(
      "collapse_timeslices",
      input.collapse_timeslices !== false ? "true" : "false",
    );
    const { data } = await httpClient.post<ScenarioExcelUpdateResponse>(
      `/scenarios/${scenarioId}/update-from-excel`,
      form,
      {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 600_000,
        ...(signal ? { signal } : {}),
        onUploadProgress(event) {
          if (event.total && onUploadProgress) {
            onUploadProgress(Math.round((event.loaded * 100) / event.total));
          }
        },
      },
    );
    return data;
  },

  async previewScenarioFromExcel(
    scenarioId: number,
    input: { file: File; sheet_name: string; collapse_timeslices?: boolean },
    onUploadProgress?: (percent: number) => void,
    signal?: AbortSignal,
  ): Promise<ScenarioExcelPreviewResponse> {
    const form = new FormData();
    form.append("file", input.file);
    form.append("sheet_name", input.sheet_name);
    form.append(
      "collapse_timeslices",
      input.collapse_timeslices !== false ? "true" : "false",
    );
    const { data } = await httpClient.post<ScenarioExcelPreviewResponse>(
      `/scenarios/${scenarioId}/preview-from-excel`,
      form,
      {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 600_000,
        ...(signal ? { signal } : {}),
        onUploadProgress(event) {
          if (event.total && onUploadProgress) {
            onUploadProgress(Math.round((event.loaded * 100) / event.total));
          }
        },
      },
    );
    return data;
  },

  async applyExcelChanges(
    scenarioId: number,
    changes: {
      preview_id: string;
      action: "update" | "insert";
      row_id?: number | null;
      param_name?: string | null;
      region_name?: string | null;
      technology_name?: string | null;
      fuel_name?: string | null;
      emission_name?: string | null;
      timeslice_code?: string | null;
      mode_of_operation_code?: string | null;
      season_code?: string | null;
      daytype_code?: string | null;
      dailytimebracket_code?: string | null;
      storage_set_code?: string | null;
      udc_set_code?: string | null;
      year?: number | null;
      new_value: number;
    }[],
  ): Promise<ScenarioExcelUpdateResponse> {
    const { data } = await httpClient.post<ScenarioExcelUpdateResponse>(
      `/scenarios/${scenarioId}/apply-excel-changes`,
      { changes },
      { timeout: 600_000 },
    );
    return data;
  },

  async applyExcelChangesAsync(
    scenarioId: number,
    changes: {
      preview_id: string;
      action: "update" | "insert";
      row_id?: number | null;
      param_name?: string | null;
      region_name?: string | null;
      technology_name?: string | null;
      fuel_name?: string | null;
      emission_name?: string | null;
      timeslice_code?: string | null;
      mode_of_operation_code?: string | null;
      season_code?: string | null;
      daytype_code?: string | null;
      dailytimebracket_code?: string | null;
      storage_set_code?: string | null;
      udc_set_code?: string | null;
      year?: number | null;
      new_value: number;
    }[],
  ): Promise<ScenarioOperationJob> {
    const { data } = await httpClient.post<ScenarioOperationJob>(
      `/scenarios/${scenarioId}/apply-excel-changes-async`,
      { changes },
    );
    return data;
  },

  getUdcConfig: (scenarioId: number) =>
    httpClient.get<UdcConfig>(`/scenarios/${scenarioId}/udc-config`).then((r) => r.data),
  updateUdcConfig: (scenarioId: number, config: UdcConfig) =>
    httpClient.put<UdcConfig>(`/scenarios/${scenarioId}/udc-config`, config).then((r) => r.data),
};
