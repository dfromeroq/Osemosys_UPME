/**
 * Constantes de rutas de la aplicación. Centralizadas para evitar strings hardcodeados.
 * paths.scenarioDetail(id) y paths.resultsDetail(runId) son funciones.
 */
export const paths = {
  home: "/",
  login: "/login",
  app: "/app",
  profile: "/app/profile",
  usersAdmin: "/app/users-admin",
  scenarios: "/app/scenarios",
  scenarioDetail: (id: string | number) => `/app/scenarios/${id}`,
  scenarioTagsAdmin: "/app/scenario-tags-admin",
  systemSettingsAdmin: "/app/system-settings",
  changeRequests: "/app/change-requests",
  catalogs: "/app/catalogs",
  officialImport: "/app/official-import",
  simulation: "/app/simulation",
  results: "/app/results",
  resultsDetail: (runId: string | number) => `/app/results/${runId}`,
  resultsDataExplorer: (
    runId: string | number,
    filters?: {
      variable_names?: string[];
      technology_names?: string[];
      technology_prefixes?: string[];
      fuel_names?: string[];
      fuel_prefixes?: string[];
      emission_names?: string[];
    },
  ) => {
    const base = `/app/results/${runId}/data`;
    if (!filters) return base;
    const params = new URLSearchParams();
    const append = (key: string, vals?: string[]) => {
      if (vals && vals.length) params.set(key, vals.join(","));
    };
    append("variable_names", filters.variable_names);
    append("technology_names", filters.technology_names);
    append("technology_prefixes", filters.technology_prefixes);
    append("fuel_names", filters.fuel_names);
    append("fuel_prefixes", filters.fuel_prefixes);
    append("emission_names", filters.emission_names);
    const qs = params.toString();
    return qs ? `${base}?${qs}` : base;
  },
  infeasibilityReport: (runId: string | number) => `/app/simulations/${runId}/infeasibility`,
  reports: "/app/reports",
  reportDashboard: (reportId: string | number) => `/app/reports/${reportId}`,
  /**
   * Visor amplificado de una sola gráfica — diseñado para links compartibles.
   * No usa AppLayout (sin sidebar de navegación). Tiene su propio side-panel
   * de "Configuración" plegable a la derecha.
   */
  chartViewer: (jobId: string | number) => `/app/charts/viewer/${jobId}`,
  history: "/app/history",
} as const;

