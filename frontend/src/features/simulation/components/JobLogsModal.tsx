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
