import { Fragment, useEffect, useMemo, useState } from "react";
import { simulationOpsApi } from "@/features/simulation/api/simulationOpsApi";
import type { ResourceTimelineCapacity } from "@/features/simulation/components/ResourceTimeline";
import { ResourceTimeline } from "@/features/simulation/components/ResourceTimeline";
import type { SimulationOpsDashboard, SimulationOpsEnvironment, SimulationOpsJob } from "@/types/domain";

function formatBytes(value: number | null | undefined): string {
  const bytes = Number(value ?? 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toLocaleString("es-CO", { maximumFractionDigits: unit === 0 ? 0 : 1 })} ${units[unit]}`;
}

function formatSeconds(value: unknown): string {
  const seconds = typeof value === "number" && Number.isFinite(value) ? value : null;
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes} min ${rest} s`;
}

function shortCommit(value: string | null | undefined): string {
  return value ? value.slice(0, 7) : "—";
}

function bytesToGb(value: number | null | undefined): number | null {
  const bytes = Number(value ?? Number.NaN);
  return Number.isFinite(bytes) ? bytes / (1024 ** 3) : null;
}

function formatGb(value: number | null | undefined): string {
  const gb = Number(value ?? Number.NaN);
  if (!Number.isFinite(gb)) return "—";
  return `${gb.toLocaleString("es-CO", { maximumFractionDigits: 1 })} GB`;
}

function JobTable({
  environment,
  jobs,
  onCancel,
  capacity,
}: {
  environment: string;
  jobs: SimulationOpsJob[];
  onCancel: (environment: string, jobId: number) => void;
  capacity?: ResourceTimelineCapacity;
}) {
  const firstWithSamples = jobs.find((job) => (job.runtime?.resource_samples?.length ?? 0) > 1)?.id ?? null;
  const [selectedJobId, setSelectedJobId] = useState<number | null>(firstWithSamples);

  if (jobs.length === 0) {
    return <div className="text-sm text-slate-500">Sin ejecuciones activas.</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="w-full text-sm" style={{ borderCollapse: "collapse", minWidth: 880 }}>
        <thead className="text-slate-500">
          <tr>
            <th className="py-2 pr-3 text-left font-medium">ID</th>
            <th className="py-2 pr-3 text-left font-medium">Estado</th>
            <th className="py-2 pr-3 text-left font-medium">Tipo</th>
            <th className="py-2 pr-3 text-right font-medium">Progreso</th>
            <th className="py-2 pr-3 text-left font-medium">Paso</th>
            <th className="py-2 pr-3 text-right font-medium">CPU</th>
            <th className="py-2 pr-3 text-right font-medium">RAM</th>
            <th className="py-2 pr-3 text-right font-medium">Hilos</th>
            <th className="py-2 pr-3 text-left font-medium">Commit</th>
            <th className="py-2 text-right font-medium">Acción</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => {
            const sample = job.runtime?.last_resource_sample;
            const samples = job.runtime?.resource_samples ?? [];
            const selected = selectedJobId === job.id;
            return (
              <Fragment key={job.id}>
                <tr
                  className="border-t border-slate-800/70"
                  style={{ background: selected ? "rgba(14,165,233,0.07)" : undefined }}
                >
                  <td className="py-2 pr-3 font-mono text-slate-200">{job.id}</td>
                  <td className="py-2 pr-3 text-slate-200">{job.status}</td>
                  <td className="py-2 pr-3 text-slate-300">{job.simulation_type}</td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-300">
                    {typeof job.progress === "number" ? `${job.progress.toFixed(0)}%` : "—"}
                  </td>
                  <td className="py-2 pr-3 text-slate-300">{sample?.stage ?? "—"}</td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-300">
                    {typeof sample?.process_cpu_percent === "number"
                      ? `${sample.process_cpu_percent.toFixed(1)}%`
                      : "—"}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-300">
                    {typeof sample?.rss_mb === "number" ? `${sample.rss_mb.toFixed(1)} MiB` : "—"}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-300">
                    {sample?.threads ?? "—"}
                  </td>
                  <td className="py-2 pr-3 font-mono text-slate-300">
                    {shortCommit(job.runtime?.commit)}
                  </td>
                  <td className="py-2 text-right">
                    {samples.length > 1 ? (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => setSelectedJobId(selected ? null : job.id)}
                        style={{ padding: "5px 9px", fontSize: 12, marginRight: 6 }}
                      >
                        {selected ? "Ocultar" : "Ver"}
                      </button>
                    ) : null}
                    {job.status === "QUEUED" || job.status === "RUNNING" ? (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => onCancel(environment, job.id)}
                        style={{ padding: "5px 9px", fontSize: 12 }}
                      >
                        Cancelar
                      </button>
                    ) : null}
                  </td>
                </tr>
                {selected && samples.length > 1 ? (
                  <tr key={`${job.id}-resource-timeline`} className="border-t border-slate-900/70">
                    <td colSpan={10} className="py-3">
                      <ResourceTimeline
                        samples={samples}
                        title={`Recursos por paso · ejecución ${job.id}`}
                        capacity={capacity}
                      />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EnvironmentPanel({
  env,
  onCancel,
}: {
  env: SimulationOpsEnvironment;
  onCancel: (environment: string, jobId: number) => void;
}) {
  const statusCounts = env.queue.counts_by_status_type ?? {};
  const limits = env.queue.limits ?? {};
  const system = env.system_resources;
  const totalRamGb = bytesToGb(system?.memory_total_bytes);
  const usedRamGb = bytesToGb(system?.memory_used_bytes);
  const capacity: ResourceTimelineCapacity = {
    cpuCores: system?.cpu_logical_count,
    totalRamGb,
    currentCpuPercent: system?.cpu_percent,
    currentRamUsedGb: usedRamGb,
  };
  return (
    <section
      style={{
        display: "grid",
        gap: 14,
        padding: "16px 0",
        borderTop: "1px solid rgba(148,163,184,0.18)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20 }}>{env.name}</h2>
          <div className="text-sm text-slate-500">
            {env.reachable ? "Disponible" : env.error ?? "No disponible"} ·{" "}
            {new Date(env.generated_at).toLocaleString("es-CO")}
          </div>
        </div>
        <div className="grid grid-cols-5 gap-3 text-right">
          <div>
            <div className="text-xs text-slate-500">En cola</div>
            <div className="font-mono text-lg">{env.queue.queued_count ?? 0}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Ejecutando</div>
            <div className="font-mono text-lg">{env.queue.running_count ?? 0}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Activas</div>
            <div className="font-mono text-lg">{env.queue.active_count ?? 0}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">RAM servicios</div>
            <div className="font-mono text-lg">{formatBytes(env.services_memory_total_bytes)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Máquina</div>
            <div className="font-mono text-lg">
              {system?.cpu_percent != null ? `${system.cpu_percent.toFixed(0)}%` : "—"} · {formatGb(usedRamGb)}
            </div>
          </div>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 10,
        }}
      >
        <div className="text-sm text-slate-300">
          <div className="text-xs text-slate-500">Nacional/Regional activos</div>
          <div className="font-mono">
            N {statusCounts.RUNNING?.NATIONAL ?? 0}/{statusCounts.QUEUED?.NATIONAL ?? 0} · R{" "}
            {statusCounts.RUNNING?.REGIONAL ?? 0}/{statusCounts.QUEUED?.REGIONAL ?? 0}
          </div>
        </div>
        <div className="text-sm text-slate-300">
          <div className="text-xs text-slate-500">Límites</div>
          <div className="font-mono">
            C {limits.sim_max_concurrency ?? "—"} · W {limits.sim_total_weight_limit ?? "—"}
          </div>
        </div>
        <div className="text-sm text-slate-300">
          <div className="text-xs text-slate-500">Commit</div>
          <div className="font-mono">{shortCommit(env.runtime_env.APP_GIT_SHA)}</div>
        </div>
        <div className="text-sm text-slate-300">
          <div className="text-xs text-slate-500">Solver threads</div>
          <div className="font-mono">{env.runtime_env.SIM_SOLVER_THREADS ?? "—"}</div>
        </div>
        <div className="text-sm text-slate-300">
          <div className="text-xs text-slate-500">Capacidad máquina</div>
          <div className="font-mono">
            {system?.cpu_logical_count ?? "—"} cores · {formatGb(totalRamGb)}
          </div>
        </div>
        <div className="text-sm text-slate-300">
          <div className="text-xs text-slate-500">Uso actual máquina</div>
          <div className="font-mono">
            CPU {system?.cpu_percent != null ? `${system.cpu_percent.toFixed(1)}%` : "—"} · RAM{" "}
            {formatGb(usedRamGb)}
          </div>
        </div>
      </div>

      {env.services_memory.length > 0 ? (
        <div className="flex flex-wrap gap-2 text-xs">
          {env.services_memory.map((service) => (
            <span
              key={service.service_name}
              className="rounded border border-slate-700 px-2 py-1 font-mono text-slate-300"
            >
              {service.service_name}: {formatBytes(service.memory_usage_bytes)}
            </span>
          ))}
        </div>
      ) : null}

      <JobTable environment={env.name} jobs={env.active_jobs} onCancel={onCancel} capacity={capacity} />
    </section>
  );
}

export function SimulationOpsPage() {
  const [dashboard, setDashboard] = useState<SimulationOpsDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    simulationOpsApi
      .getDashboard(true)
      .then((data) => {
        if (!cancelled) {
          setDashboard(data);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "No se pudo cargar operación");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  useEffect(() => {
    const id = window.setInterval(() => setRefreshKey((v) => v + 1), 10_000);
    return () => window.clearInterval(id);
  }, []);

  const environments = useMemo(() => dashboard?.environments ?? [], [dashboard]);

  const handleCancel = async (environment: string, jobId: number) => {
    const ok = window.confirm(`Cancelar ejecución ${jobId} en ${environment}?`);
    if (!ok) return;
    await simulationOpsApi.cancelJob(environment, jobId);
    setRefreshKey((v) => v + 1);
  };

  return (
    <section className="pageSection" style={{ display: "grid", gap: 18 }}>
      <header style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ margin: 0 }}>Operación de simulaciones</h1>
          <p className="text-sm text-slate-500" style={{ margin: "4px 0 0" }}>
            Colas, recursos y ejecuciones activas por ambiente.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => setRefreshKey((v) => v + 1)}
        >
          Actualizar
        </button>
      </header>

      {loading && !dashboard ? <div className="text-sm text-slate-500">Cargando…</div> : null}
      {error ? <div className="text-sm text-rose-300">{error}</div> : null}

      {environments.map((env) => (
        <EnvironmentPanel key={env.name} env={env} onCancel={handleCancel} />
      ))}

      {!loading && environments.length === 0 ? (
        <div className="text-sm text-slate-500">Sin ambientes operativos configurados.</div>
      ) : null}

      {dashboard ? (
        <div className="text-xs text-slate-600">
          Última lectura: {new Date(dashboard.generated_at).toLocaleString("es-CO")}
        </div>
      ) : null}
    </section>
  );
}
