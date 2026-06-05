/**
 * API admin para configuración runtime del sistema (solver HiGHS/Gurobi).
 */
import { httpClient } from "@/shared/api/httpClient";

export type HighsMethod =
  | "default"
  | "choose"
  | "simplex"
  | "ipm"
  | "ipx"
  | "hipo";
export type OnOffChoose = "default" | "off" | "on" | "choose";

export type SolverSettings = {
  solver_threads: number;
  highs_method: HighsMethod;
  highs_presolve: OnOffChoose;
  highs_parallel: OnOffChoose;
  highs_hipo_parallel_type: string;
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
  "updated_at" | "updated_by_username"
>;

async function getSolverSettings(): Promise<SolverSettings> {
  const { data } = await httpClient.get<SolverSettings>(
    "/admin/system-settings/solver",
  );
  return data;
}

async function updateSolverSettings(
  payload: SolverSettingsUpdate,
): Promise<SolverSettings> {
  const { data } = await httpClient.patch<SolverSettings>(
    "/admin/system-settings/solver",
    payload,
  );
  return data;
}

export const systemSettingsApi = {
  getSolverSettings,
  updateSolverSettings,
};
