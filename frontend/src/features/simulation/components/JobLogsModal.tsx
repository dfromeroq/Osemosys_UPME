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
import { SimulationStageTimeline } from "@/features/simulation/components/SimulationStageTimeline";
import {
  formatReadableDuration,
  getTopSlowStages,
  resolveStageTimings,
} from "@/features/simulation/simulationStageTimings";
import type { SimulationLog, SimulationRun } from "@/types/domain";

type Props = {
  jobId: number | null;
  onClose: () => void;
};

type RuntimeResourceSample = {
  stage?: string;
  elapsed_seconds?: number;
  delta_seconds?: number;
  process_cpu_percent?: number;
  rss_mb?: number | null;
  peak_rss_mb?: number | null;
  threads?: number | null;
  cgroup_memory_current_mb?: number | null;
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

function cleanStageName(stage: string | undefined): string {
  return (stage ?? "sample")
    .replace(/_seconds$/, "")
    .replace(/_complete$/, "")
    .replace(/_/g, " ");
}

function metricMax(samples: RuntimeResourceSample[], read: (sample: RuntimeResourceSample) => number | null): number {
  return Math.max(
    1,
    ...samples.map((sample) => read(sample) ?? 0).filter((value) => Number.isFinite(value)),
  );
}

function buildPolyline(
  samples: RuntimeResourceSample[],
  read: (sample: RuntimeResourceSample) => number | null,
  max: number,
  totalSeconds: number,
): string {
  const width = 820;
  const height = 150;
  const padX = 36;
  const padY = 20;
  return samples
    .map((sample, idx) => {
      const elapsed = asNumber(sample.elapsed_seconds) ?? idx;
      const raw = read(sample) ?? 0;
      const x = padX + (elapsed / Math.max(1, totalSeconds)) * (width - padX * 2);
      const y = padY + (1 - raw / max) * (height - padY * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function ResourceTimeline({ samples }: { samples: RuntimeResourceSample[] }) {
  const prepared = samples
    .filter((sample) => asNumber(sample.elapsed_seconds) !== null)
    .sort((a, b) => (asNumber(a.elapsed_seconds) ?? 0) - (asNumber(b.elapsed_seconds) ?? 0));
  if (prepared.length < 2) return null;

  const totalSeconds = Math.max(...prepared.map((sample) => asNumber(sample.elapsed_seconds) ?? 0), 1);
  const ramMax = metricMax(prepared, (sample) => asNumber(sample.rss_mb));
  const cpuMax = metricMax(prepared, (sample) => asNumber(sample.process_cpu_percent));
  const threadsMax = metricMax(prepared, (sample) => asNumber(sample.threads));
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  const xFor = (elapsed: number) => 36 + (elapsed / totalSeconds) * (820 - 72);
  const yFor = (value: number, max: number) => 20 + (1 - value / max) * 110;

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div className="text-xs text-slate-500">
        Timeline de recursos por paso
      </div>
      <div style={{ overflowX: "auto" }}>
        <svg
          role="img"
          aria-label="Timeline de RAM, CPU e hilos por paso de simulación"
          viewBox="0 0 820 190"
          style={{ minWidth: 760, width: "100%", height: 230, display: "block" }}
        >
          <rect x="0" y="0" width="820" height="190" rx="8" fill="rgba(2,6,23,0.35)" />
          {ticks.map((tick) => {
            const x = 36 + tick * (820 - 72);
            return (
              <g key={tick}>
                <line x1={x} y1="20" x2={x} y2="130" stroke="rgba(148,163,184,0.16)" />
                <text x={x} y="148" textAnchor="middle" fill="rgba(148,163,184,0.85)" fontSize="10">
                  {formatReadableDuration(totalSeconds * tick)}
                </text>
              </g>
            );
          })}
          {[20, 75, 130].map((y) => (
            <line key={y} x1="36" y1={y} x2="784" y2={y} stroke="rgba(148,163,184,0.12)" />
          ))}
          <polyline
            fill="none"
            stroke="#38bdf8"
            strokeWidth="2.2"
            points={buildPolyline(prepared, (sample) => asNumber(sample.rss_mb), ramMax, totalSeconds)}
          />
          <polyline
            fill="none"
            stroke="#f59e0b"
            strokeWidth="2.2"
            points={buildPolyline(prepared, (sample) => asNumber(sample.process_cpu_percent), cpuMax, totalSeconds)}
          />
          <polyline
            fill="none"
            stroke="#a78bfa"
            strokeWidth="2.2"
            points={buildPolyline(prepared, (sample) => asNumber(sample.threads), threadsMax, totalSeconds)}
          />
          {prepared.map((sample, idx) => {
            const elapsed = asNumber(sample.elapsed_seconds) ?? 0;
            const x = xFor(elapsed);
            const ramY = yFor(asNumber(sample.rss_mb) ?? 0, ramMax);
            const cpuY = yFor(asNumber(sample.process_cpu_percent) ?? 0, cpuMax);
            const threadsY = yFor(asNumber(sample.threads) ?? 0, threadsMax);
            const label = cleanStageName(sample.stage);
            return (
              <g key={`${sample.stage ?? "sample"}-${idx}`}>
                <line x1={x} y1="20" x2={x} y2="130" stroke="rgba(148,163,184,0.09)" />
                <circle cx={x} cy={ramY} r="3.2" fill="#38bdf8">
                  <title>{`${label}: RAM ${formatCompactNumber(sample.rss_mb, " MiB")}`}</title>
                </circle>
                <circle cx={x} cy={cpuY} r="3.2" fill="#f59e0b">
                  <title>{`${label}: CPU ${formatCompactNumber(sample.process_cpu_percent, "%")}`}</title>
                </circle>
                <circle cx={x} cy={threadsY} r="3.2" fill="#a78bfa">
                  <title>{`${label}: hilos ${formatCompactNumber(sample.threads)}`}</title>
                </circle>
                {idx === 0 || idx === prepared.length - 1 || idx % Math.ceil(prepared.length / 5) === 0 ? (
                  <text
                    x={x}
                    y="171"
                    textAnchor="middle"
                    fill="rgba(203,213,225,0.78)"
                    fontSize="10"
                  >
                    {label.slice(0, 18)}
                  </text>
                ) : null}
              </g>
            );
          })}
          <g transform="translate(40 14)" fontSize="11" fill="rgba(203,213,225,0.9)">
            <circle cx="0" cy="0" r="4" fill="#38bdf8" />
            <text x="9" y="4">RAM max {formatCompactNumber(ramMax, " MiB")}</text>
            <circle cx="145" cy="0" r="4" fill="#f59e0b" />
            <text x="154" y="4">CPU max {formatCompactNumber(cpuMax, "%")}</text>
            <circle cx="285" cy="0" r="4" fill="#a78bfa" />
            <text x="294" y="4">Hilos max {formatCompactNumber(threadsMax)}</text>
          </g>
        </svg>
      </div>
    </div>
  );
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
