import { httpClient } from "@/shared/api/httpClient";
import type { SimulationOpsDashboard, SimulationOpsJob } from "@/types/domain";

export const simulationOpsApi = {
  async getDashboard(includeRemotes = true) {
    const { data } = await httpClient.get<SimulationOpsDashboard>(
      "/simulation-ops/dashboard",
      { params: { include_remotes: includeRemotes } },
    );
    return data;
  },

  async cancelJob(environment: string, jobId: number) {
    const { data } = await httpClient.post<SimulationOpsJob>(
      `/simulation-ops/environments/${encodeURIComponent(environment)}/jobs/${jobId}/cancel`,
    );
    return data;
  },
};
