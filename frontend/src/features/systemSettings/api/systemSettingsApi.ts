/**
 * API admin para configuración runtime del sistema (solver HiGHS/Gurobi).
 */
import { httpClient } from "@/shared/api/httpClient";

export type HighsMethod = "choose" | "simplex" | "ipm" | "ipx";
export type OnOffChoose = "off" | "on" | "choose";

export type SolverSettings = {
  solver_threads: number;
  hardware_thread_limit: number;
  effective_threads_preview: number;
  highs_method: HighsMethod;
  highs_presolve: OnOffChoose;
  highs_parallel: OnOffChoose;
  highs_run_crossover: OnOffChoose;
  highs_use_direct: boolean;
  highs_time_limit: number;
  highs_ipm_optimality_tolerance: number;
  highs_primal_feasibility_tolerance: number;
  updated_at: string | null;
  updated_by_username: string | null;
};

export type SolverSettingsUpdate = Omit<
  SolverSettings,
  "hardware_thread_limit" | "effective_threads_preview" | "updated_at" | "updated_by_username"
>;

async function getSolverSettings(): Promise<SolverSettings> {
  const { data } = await httpClient.get<SolverSettings>(
    "/admin/system-settings/solver",
  );
  return data;
}

async function updateSolverSettings(
  payload: SolverSettingsUpdate | number,
): Promise<SolverSettings> {
  const body = typeof payload === "number" ? { solver_threads: payload } : payload;
  const { data } = await httpClient.patch<SolverSettings>(
    "/admin/system-settings/solver",
    body,
  );
  return data;
}

export const systemSettingsApi = {
  getSolverSettings,
  updateSolverSettings,
};
