/**
 * API admin para configuración runtime del sistema (e.g. hilos del solver).
 */
import { httpClient } from "@/shared/api/httpClient";

export type SolverSettings = {
  solver_threads: number;
  updated_at: string | null;
  updated_by_username: string | null;
};

async function getSolverSettings(): Promise<SolverSettings> {
  const { data } = await httpClient.get<SolverSettings>(
    "/admin/system-settings/solver",
  );
  return data;
}

async function updateSolverSettings(
  threads: number,
): Promise<SolverSettings> {
  const { data } = await httpClient.patch<SolverSettings>(
    "/admin/system-settings/solver",
    { solver_threads: threads },
  );
  return data;
}

export const systemSettingsApi = {
  getSolverSettings,
  updateSolverSettings,
};
