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

function formatTimestamp(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString("es-CO") : "—";
}

function jobDurationSeconds(job: SimulationOpsJob): number | null {
  if (!job.started_at || !job.finished_at) return null;
  const started = new Date(job.started_at).getTime();
  const finished = new Date(job.finished_at).getTime();
  if (!Number.isFinite(started) || !Number.isFinite(finished) || finished < started) return null;
  return (finished - started) / 1000;
}

function sampleMax(
  job: SimulationOpsJob,
  read: (sample: NonNullable<SimulationOpsJob["runtime"]>["last_resource_sample"]) => number | null,
): number | null {
  const samples = job.runtime?.resource_samples ?? [];
  const values = samples
    .map((sample) => read(sample))
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return values.length ? Math.max(...values) : null;
}

function ramPeakGb(job: SimulationOpsJob): number | null {
  const peak = sampleMax(job, (sample) => sample?.peak_rss_mb ?? sample?.rss_mb ?? null);
  return peak === null ? null : peak / 1024;
}

function cpuPeakCores(job: SimulationOpsJob): number | null {
  const peak = sampleMax(job, (sample) => sample?.process_cpu_percent ?? null);
  return peak === null ? null : peak / 100;
}

function threadPeak(job: SimulationOpsJob): number | null {
  return sampleMax(job, (sample) => sample?.threads ?? null);
}

function EventTimeline({ job }: { job: SimulationOpsJob }) {
  const events = job.events ?? [];
  if (events.length === 0) return null;
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div className="text-xs font-medium text-slate-400">Eventos recientes</div>
      <div style={{ display: "grid", gap: 4, maxHeight: 180, overflowY: "auto" }}>
        {events.map((event) => (
          <div
            key={event.id}
            className="rounded border border-slate-800 px-2 py-1 text-xs text-slate-400"
            style={{ display: "grid", gridTemplateColumns: "145px 110px 1fr", gap: 8 }}
          >
            <span className="font-mono">{formatTimestamp(event.created_at)}</span>
            <span className="font-mono text-sky-300">{event.stage ?? event.event_type}</span>
            <span>{event.message ?? "—"}</span>
          </div>
        ))}
      </div>
    </div>
  );
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
      <table className="w-full text-sm" style={{ borderCollapse: "collapse", minWidth: 960 }}>
        <thead className="text-slate-500">
          <tr>
            <th className="py-2 pr-3 text-left font-medium">ID</th>
            <th className="py-2 pr-3 text-left font-medium">Estado</th>
            <th className="py-2 pr-3 text-left font-medium">Tipo</th>
            <th className="py-2 pr-3 text-right font-medium">Progreso</th>
            <th className="py-2 pr-3 text-left font-medium">Paso</th>
            <th className="py-2 pr-3 text-right font-medium">PID</th>
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
                    {job.runtime?.pid ?? "—"}
                  </td>
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
                    <td colSpan={11} className="py-3">
                      <div style={{ display: "grid", gap: 10 }}>
                        <ResourceTimeline
                          samples={samples}
                          title={`Recursos por paso · ejecución ${job.id}`}
                          capacity={capacity}
                        />
                        <EventTimeline job={job} />
                      </div>
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

function RecentJobsHistory({
  jobs,
  capacity,
}: {
  jobs: SimulationOpsJob[];
  capacity?: ResourceTimelineCapacity;
}) {
  const historicalJobs = jobs.filter((job) => job.status !== "QUEUED" && job.status !== "RUNNING");
  const firstWithSamples = historicalJobs.find((job) => (job.runtime?.resource_samples?.length ?? 0) > 1)?.id ?? null;
  const [selectedJobId, setSelectedJobId] = useState<number | null>(firstWithSamples);
  const selectedJob = historicalJobs.find((job) => job.id === selectedJobId) ?? null;
  const selectedSamples = selectedJob?.runtime?.resource_samples ?? [];

  if (historicalJobs.length === 0) {
    return null;
  }

  return (
    <section style={{ display: "grid", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 15 }}>Histórico reciente</h3>
          <div className="text-xs text-slate-500">
            Últimas ejecuciones terminadas con muestras de RAM, CPU e hilos cuando estén disponibles.
          </div>
        </div>
        {selectedJob ? (
          <div className="text-xs text-slate-500">
            Seleccionada: <span className="font-mono text-slate-300">#{selectedJob.id}</span>
          </div>
        ) : null}
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="w-full text-sm" style={{ borderCollapse: "collapse", minWidth: 980 }}>
          <thead className="text-slate-500">
            <tr>
              <th className="py-2 pr-3 text-left font-medium">ID</th>
              <th className="py-2 pr-3 text-left font-medium">Estado</th>
              <th className="py-2 pr-3 text-left font-medium">Tipo</th>
              <th className="py-2 pr-3 text-left font-medium">Fin</th>
              <th className="py-2 pr-3 text-right font-medium">Duración</th>
              <th className="py-2 pr-3 text-right font-medium">RAM pico</th>
              <th className="py-2 pr-3 text-right font-medium">CPU pico</th>
              <th className="py-2 pr-3 text-right font-medium">Hilos pico</th>
              <th className="py-2 pr-3 text-left font-medium">Commit</th>
              <th className="py-2 text-right font-medium">Detalle</th>
            </tr>
          </thead>
          <tbody>
            {historicalJobs.map((job) => {
              const selected = selectedJobId === job.id;
              const hasSamples = (job.runtime?.resource_samples?.length ?? 0) > 1;
              return (
                <tr
                  key={job.id}
                  className="border-t border-slate-800/70"
                  style={{ background: selected ? "rgba(14,165,233,0.07)" : undefined }}
                >
                  <td className="py-2 pr-3 font-mono text-slate-200">{job.id}</td>
                  <td className="py-2 pr-3 text-slate-200">{job.status}</td>
                  <td className="py-2 pr-3 text-slate-300">{job.simulation_type}</td>
                  <td className="py-2 pr-3 text-slate-300">{formatTimestamp(job.finished_at)}</td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-300">
                    {formatSeconds(jobDurationSeconds(job))}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-300">
                    {formatGb(ramPeakGb(job))}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-300">
                    {cpuPeakCores(job)?.toLocaleString("es-CO", { maximumFractionDigits: 2 }) ?? "—"}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-300">
                    {threadPeak(job)?.toLocaleString("es-CO", { maximumFractionDigits: 0 }) ?? "—"}
                  </td>
                  <td className="py-2 pr-3 font-mono text-slate-300">{shortCommit(job.runtime?.commit)}</td>
                  <td className="py-2 text-right">
                    {hasSamples ? (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => setSelectedJobId(selected ? null : job.id)}
                        style={{ padding: "5px 9px", fontSize: 12 }}
                      >
                        {selected ? "Ocultar" : "Ver"}
                      </button>
                    ) : (
                      <span className="text-xs text-slate-600">Sin muestras</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {selectedJob ? (
        <div style={{ display: "grid", gap: 10 }}>
          {selectedSamples.length > 1 ? (
            <ResourceTimeline
              samples={selectedSamples}
              title={`Histórico de recursos · ejecución ${selectedJob.id}`}
              capacity={capacity}
            />
          ) : null}
          <EventTimeline job={selectedJob} />
        </div>
      ) : null}
    </section>
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
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))",
            gap: 8,
          }}
        >
          {env.services_memory.map((service) => {
            const processes = (service.processes ?? []).filter((process) =>
              ["python", "glpsol", "highs", "celery"].some((name) =>
                `${process.command ?? ""} ${process.args ?? ""}`.toLowerCase().includes(name),
              ),
            );
            return (
              <div
                key={service.service_name}
                className="rounded border border-slate-700 px-3 py-2 text-xs text-slate-300"
                style={{ display: "grid", gap: 5 }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <strong className="font-mono text-slate-200">{service.service_name}</strong>
                  <span className={service.oom_killed ? "text-red-400" : "text-slate-500"}>
                    {service.oom_killed ? "OOMKilled" : service.status ?? "—"}
                  </span>
                </div>
                <div className="font-mono">
                  CPU {service.cpu_percent != null ? `${service.cpu_percent.toFixed(1)}%` : "—"}
                  {service.cpu_used_cores != null ? ` (${service.cpu_used_cores.toFixed(2)} cores)` : ""}
                </div>
                <div className="font-mono">
                  RAM {formatBytes(service.memory_working_set_bytes ?? service.memory_usage_bytes)} /{" "}
                  {formatBytes(service.memory_limit_bytes)} · pico {formatBytes(service.memory_peak_bytes)}
                </div>
                <div className="font-mono text-slate-500">
                  PID host {service.host_pid ?? "—"} · procesos {service.pids_current ?? "—"} · reinicios{" "}
                  {service.restart_count ?? 0}
                </div>
                {processes.slice(0, 4).map((process, index) => (
                  <div key={`${process.pid ?? index}-${process.command ?? "process"}`} className="font-mono text-slate-500">
                    {process.command ?? "proceso"} pid={process.pid ?? "—"} cpu={process.cpu_percent ?? "—"}% rss={
                      process.rss_kb != null ? `${(process.rss_kb / 1024).toFixed(0)}MiB` : "—"
                    }
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      ) : null}

      <JobTable environment={env.name} jobs={env.active_jobs} onCancel={onCancel} capacity={capacity} />
      <RecentJobsHistory jobs={env.recent_jobs} capacity={capacity} />
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
