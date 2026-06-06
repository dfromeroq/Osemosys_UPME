/**
 * Modal mínimo para mostrar registros (logs) de un job de simulación.
 *
 * Reutilizable desde ResultsPage y otras vistas que sólo necesitan inspeccionar
 * la cronología sin la UI extendida (banners de infactibilidad, etapas en
 * vivo) que sí usa SimulationPage.
 */
import { useEffect, useMemo, useState } from "react";
import { Modal } from "@/shared/components/Modal";
import { simulationApi } from "@/features/simulation/api/simulationApi";
import { ResourceTimeline } from "@/features/simulation/components/ResourceTimeline";
import { SimulationStageTimeline } from "@/features/simulation/components/SimulationStageTimeline";
import {
  formatReadableDuration,
  getTopSlowStages,
  resolveStageTimings,
} from "@/features/simulation/simulationStageTimings";
import type { RuntimeResourceSample, SimulationLog, SimulationRun } from "@/types/domain";

type Props = {
  jobId: number | null;
  onClose: () => void;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function formatCompactNumber(value: unknown, suffix = ""): string {
  const num = asNumber(value);
  if (num === null) return "—";
  return `${num.toLocaleString("es-CO", { maximumFractionDigits: 1 })}${suffix}`;
}

function shortCommit(value: unknown): string {
  const sha = asString(value);
  return sha ? sha.slice(0, 7) : "—";
}

function getRuntimeContext(run: SimulationRun | null): Record<string, unknown> | null {
  return asRecord(run?.model_timings?.runtime_context);
}

function getResourceSamples(run: SimulationRun | null): RuntimeResourceSample[] {
  const raw = run?.model_timings?.runtime_resource_samples;
  if (!Array.isArray(raw)) return [];
  return raw.map((item) => asRecord(item)).filter(Boolean) as RuntimeResourceSample[];
}

export function JobLogsModal({ jobId, onClose }: Props) {
  const [logs, setLogs] = useState<SimulationLog[]>([]);
  const [run, setRun] = useState<SimulationRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [liveNowMs, setLiveNowMs] = useState(() => Date.now());

  const jobActive = run ? run.status === "QUEUED" || run.status === "RUNNING" : false;

  useEffect(() => {
    if (jobId == null) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([simulationApi.listLatestLogs(jobId, 200), simulationApi.getRun(jobId)])
      .then(([logsRes, runRes]) => {
        if (!cancelled) {
          setLogs(logsRes.data);
          setRun(runRes);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "No se pudieron cargar los registros");
          setLogs([]);
          setRun(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    if (jobId == null || !jobActive) return;
    setLiveNowMs(Date.now());
    const id = window.setInterval(() => setLiveNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [jobId, jobActive]);

  useEffect(() => {
    if (jobId == null || !jobActive) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const [logsRes, runRes] = await Promise.all([
          simulationApi.listLatestLogs(jobId, 200),
          simulationApi.getRun(jobId),
        ]);
        if (!cancelled) {
          setLogs(logsRes.data);
          setRun(runRes);
        }
      } catch {
        // ignorar errores esporádicos de red
      }
    };
    const id = window.setInterval(() => {
      void poll();
    }, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [jobId, jobActive]);

  const resolvedTimings = useMemo(() => {
    if (!run || logs.length === 0) return null;
    return resolveStageTimings({
      logs,
      stageTimes: run.stage_times,
      modelTimings: run.model_timings,
      jobStatus: run.status,
      liveNowMs,
      startedAt: run.started_at,
      finishedAt: run.finished_at,
    });
  }, [logs, run, liveNowMs]);

  const topSlow = resolvedTimings ? getTopSlowStages(resolvedTimings, 3) : [];
  const runtimeContext = getRuntimeContext(run);
  const runtimeEnv = asRecord(runtimeContext?.env);
  const runtimeCpu = asRecord(runtimeContext?.cpu);
  const runtimeCgroup = asRecord(runtimeCpu?.cgroup);
  const resourceSamples = getResourceSamples(run);
  const visibleSamples = resourceSamples.slice(-8);

  return (
    <Modal
      open={jobId != null}
      title={jobId != null ? `Registros de la ejecución ${jobId}` : "Registros"}
      onClose={onClose}
    >
      {loading ? (
        <div style={{ display: "grid", gap: 8 }}>
          <div className="skeletonLine" />
          <div className="skeletonLine" />
          <div className="skeletonLine" />
        </div>
      ) : error ? (
        <div className="text-sm text-rose-300">{error}</div>
      ) : logs.length === 0 ? (
        <div className="text-sm text-slate-400">Sin registros disponibles para este job.</div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {resolvedTimings && resolvedTimings.totalSeconds !== null ? (
            <div
              style={{
                display: "grid",
                gap: 6,
                padding: 10,
                borderRadius: 10,
                border: "1px solid rgba(148,163,184,0.25)",
                background: "rgba(15,23,42,0.35)",
              }}
            >
              <div style={{ fontSize: 13 }}>
                <strong>Tiempo total:</strong>{" "}
                <span style={{ fontVariantNumeric: "tabular-nums" }}>
                  {formatReadableDuration(resolvedTimings.totalSeconds)}
                  {jobActive ? " (en curso)" : ""}
                </span>
              </div>
              {topSlow.length > 0 ? (
                <div style={{ fontSize: 12, opacity: 0.85 }}>
                  Etapas más lentas:{" "}
                  {topSlow
                    .map((s) => `${s.label} (${formatReadableDuration(s.durationSeconds)})`)
                    .join(" · ")}
                </div>
              ) : null}
            </div>
          ) : null}

          {run ? (
            <SimulationStageTimeline
              compact
              logs={logs}
              stageTimes={run.stage_times}
              modelTimings={run.model_timings}
              jobStatus={run.status}
              liveNowMs={liveNowMs}
              startedAt={run.started_at}
              finishedAt={run.finished_at}
            />
          ) : null}

          {runtimeContext || visibleSamples.length > 0 ? (
            <div
              style={{
                display: "grid",
                gap: 8,
                padding: 10,
                borderRadius: 8,
                border: "1px solid rgba(148,163,184,0.25)",
                background: "rgba(15,23,42,0.28)",
              }}
            >
              {runtimeContext ? (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                    gap: 8,
                    fontSize: 12,
                  }}
                >
                  <div>
                    <div className="text-slate-500">Commit</div>
                    <div className="font-mono text-slate-200">
                      {shortCommit(runtimeEnv?.APP_GIT_SHA)}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">CPU visible</div>
                    <div className="font-mono text-slate-200">
                      {formatCompactNumber(runtimeCpu?.affinity_count)}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">CPU cgroup</div>
                    <div className="font-mono text-slate-200">
                      {formatCompactNumber(runtimeCgroup?.quota_cpus)}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">Solver threads</div>
                    <div className="font-mono text-slate-200">
                      {asString(runtimeEnv?.SIM_SOLVER_THREADS) ?? "—"}
                    </div>
                  </div>
                </div>
              ) : null}

              {visibleSamples.length > 0 ? (
                <>
                  <ResourceTimeline samples={resourceSamples} />
                  <div style={{ overflowX: "auto" }}>
                    <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
                      <thead className="text-slate-500">
                        <tr>
                          <th className="py-1 pr-3 text-left font-medium">Paso</th>
                          <th className="py-1 pr-3 text-right font-medium">t</th>
                          <th className="py-1 pr-3 text-right font-medium">CPU</th>
                          <th className="py-1 pr-3 text-right font-medium">RAM</th>
                          <th className="py-1 pr-3 text-right font-medium">Pico</th>
                          <th className="py-1 text-right font-medium">Hilos</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleSamples.map((sample, idx) => (
                          <tr key={`${sample.stage ?? "sample"}-${idx}`} className="border-t border-slate-800/70">
                            <td className="py-1 pr-3 text-slate-200">{sample.stage ?? "—"}</td>
                            <td className="py-1 pr-3 text-right font-mono text-slate-300">
                              {formatCompactNumber(sample.elapsed_seconds, "s")}
                            </td>
                            <td className="py-1 pr-3 text-right font-mono text-slate-300">
                              {formatCompactNumber(sample.process_cpu_percent, "%")}
                            </td>
                            <td className="py-1 pr-3 text-right font-mono text-slate-300">
                              {formatCompactNumber(sample.rss_mb, " MiB")}
                            </td>
                            <td className="py-1 pr-3 text-right font-mono text-slate-300">
                              {formatCompactNumber(sample.peak_rss_mb, " MiB")}
                            </td>
                            <td className="py-1 text-right font-mono text-slate-300">
                              {formatCompactNumber(sample.threads)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : null}
            </div>
          ) : null}

          <ol
            className="grid gap-1.5 text-xs font-mono leading-relaxed"
            style={{ maxHeight: "40vh", overflowY: "auto" }}
          >
            {logs.map((l) => (
              <li
                key={l.id}
                className="grid grid-cols-[auto_auto_1fr] items-baseline gap-2 border-b border-slate-800/60 pb-1"
              >
                <span className="text-slate-500 tabular-nums">
                  {new Date(l.created_at).toLocaleTimeString("es-CO")}
                </span>
                <span className="text-cyan-300">{l.stage ?? l.event_type}</span>
                <span className="text-slate-200 break-words">{l.message ?? "—"}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Modal>
  );
}
