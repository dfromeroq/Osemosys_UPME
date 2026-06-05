import type { RunStatus, SimulationLog } from "@/types/domain";

export type StageTimingStatus = "pending" | "running" | "done";
export type StageTimingSource = "measured" | "live" | null;
export type TimingDictSource = "stage_times" | "model_timings";

export type CanonicalStageId =
  | "extract_data"
  | "data_processing"
  | "declare_model"
  | "create_instance"
  | "solver_write_lp"
  | "solver_read_model"
  | "solver_run"
  | "solver_map_solution"
  | "process_results"
  | "persist_results"
  | "infeasibility_analysis";

export type CanonicalStageDef = {
  id: CanonicalStageId;
  label: string;
  timingKey: string;
  source: TimingDictSource;
  /** Etapas de log que activan esta etapa canónica. */
  logStages: string[];
  /** Sub-etapa del bloque HiGHS (agrupación visual). */
  highsSubStage?: boolean;
};

/** Etapas de log que son marcadores (sin duración propia). */
export const MARKER_LOG_STAGES = new Set([
  "solver",
  "solver_start",
  "data_loaded",
  "instance_ready",
  "create_instance",
  "process_results_complete",
  "release_model",
  "end",
  "complete",
  "solve",
  "build_model",
  "constraint_diagnostics",
  "infeasibility_analysis_complete",
  "general",
]);

export const CANONICAL_STAGES: CanonicalStageDef[] = [
  {
    id: "extract_data",
    label: "Leer insumos del escenario",
    timingKey: "extract_data_seconds",
    source: "stage_times",
    logStages: ["extract_data"],
  },
  {
    id: "data_processing",
    label: "Preprocesar datos",
    timingKey: "data_processing_seconds",
    source: "model_timings",
    logStages: ["data_loading", "data_loaded"],
  },
  {
    id: "declare_model",
    label: "Declarar modelo abstracto",
    timingKey: "declare_model_seconds",
    source: "model_timings",
    logStages: ["declare_model"],
  },
  {
    id: "create_instance",
    label: "Crear instancia Pyomo",
    timingKey: "create_instance_seconds",
    source: "model_timings",
    logStages: ["create_instance_start", "create_instance_pyomo"],
  },
  {
    id: "solver_write_lp",
    label: "Escribir archivo LP",
    timingKey: "solver_write_lp_seconds",
    source: "model_timings",
    logStages: ["solver_write_lp"],
    highsSubStage: true,
  },
  {
    id: "solver_read_model",
    label: "HiGHS: cargar LP",
    timingKey: "solver_read_model_seconds",
    source: "model_timings",
    logStages: ["solver_read_model"],
    highsSubStage: true,
  },
  {
    id: "solver_run",
    label: "HiGHS: resolver modelo",
    timingKey: "solver_run_seconds",
    source: "model_timings",
    logStages: ["solver_run"],
    highsSubStage: true,
  },
  {
    id: "solver_map_solution",
    label: "HiGHS: mapear solución",
    timingKey: "solver_map_solution_seconds",
    source: "model_timings",
    logStages: ["solver_map_solution"],
    highsSubStage: true,
  },
  {
    id: "process_results",
    label: "Extraer resultados Pyomo",
    timingKey: "results_processing_seconds",
    source: "model_timings",
    logStages: ["process_results"],
  },
  {
    id: "persist_results",
    label: "Guardar en base de datos",
    timingKey: "persist_results_seconds",
    source: "stage_times",
    logStages: ["persist_results"],
  },
  {
    id: "infeasibility_analysis",
    label: "Análisis de infactibilidad",
    timingKey: "infeasibility_analysis_seconds",
    source: "model_timings",
    logStages: ["infeasibility_analysis_start"],
  },
];

const LOG_STAGE_TO_CANONICAL = new Map<string, CanonicalStageId>();
for (const stage of CANONICAL_STAGES) {
  for (const logStage of stage.logStages) {
    LOG_STAGE_TO_CANONICAL.set(logStage, stage.id);
  }
}

const ACTIVE_JOB_STATUSES = new Set<RunStatus>(["QUEUED", "RUNNING"]);

export type ResolvedStage = {
  id: CanonicalStageId;
  label: string;
  status: StageTimingStatus;
  durationSeconds: number | null;
  source: StageTimingSource;
  startedAt?: Date | undefined;
  highsSubStage?: boolean | undefined;
};

export type ResolvedStageTimings = {
  stages: ResolvedStage[];
  highsSubStages: ResolvedStage[];
  highsTotalSeconds: number | null;
  highsTotalSource: "measured" | "derived" | null;
  solverStatus: string | null;
  currentStage: ResolvedStage | null;
  totalSeconds: number | null;
  jobActive: boolean;
};

export type ResolveStageTimingsInput = {
  logs: SimulationLog[];
  stageTimes?: Record<string, number | string> | null | undefined;
  modelTimings?: Record<string, number | string> | null | undefined;
  jobStatus: RunStatus;
  liveNowMs: number;
  startedAt?: string | null | undefined;
  finishedAt?: string | null | undefined;
};

function normalizeLogStage(stage: string | null | undefined): string {
  return (stage ?? "general").trim().toLowerCase();
}

function readTimingValue(
  dict: Record<string, number | string> | null | undefined,
  key: string,
): number | null {
  if (!dict) return null;
  const raw = dict[key];
  if (typeof raw === "number" && Number.isFinite(raw)) return Math.max(0, raw);
  if (typeof raw === "string" && raw.trim() !== "") {
    const parsed = Number(raw);
    if (Number.isFinite(parsed)) return Math.max(0, parsed);
  }
  return null;
}

function findLogStartForStage(logs: SimulationLog[], logStages: string[]): SimulationLog | null {
  const wanted = new Set(logStages.map((s) => s.toLowerCase()));
  for (let i = logs.length - 1; i >= 0; i -= 1) {
    const log = logs[i];
    if (!log) continue;
    if (wanted.has(normalizeLogStage(log.stage))) return log;
  }
  return null;
}

function resolveActiveCanonicalId(logs: SimulationLog[]): CanonicalStageId | null {
  for (let i = logs.length - 1; i >= 0; i -= 1) {
    const key = normalizeLogStage(logs[i]?.stage);
    if (MARKER_LOG_STAGES.has(key)) continue;
    const canonical = LOG_STAGE_TO_CANONICAL.get(key);
    if (canonical) return canonical;
  }
  return null;
}

function buildResolvedStage(
  def: CanonicalStageDef,
  startedAt: Date | undefined,
  partial: Pick<ResolvedStage, "status" | "durationSeconds" | "source">,
): ResolvedStage {
  return {
    id: def.id,
    label: def.label,
    status: partial.status,
    durationSeconds: partial.durationSeconds,
    source: partial.source,
    ...(startedAt ? { startedAt } : {}),
    ...(def.highsSubStage ? { highsSubStage: true } : {}),
  };
}

function resolveOneStage(
  def: CanonicalStageDef,
  input: ResolveStageTimingsInput,
  activeCanonicalId: CanonicalStageId | null,
  jobActive: boolean,
  endMs: number,
): ResolvedStage {
  const dict = def.source === "stage_times" ? input.stageTimes : input.modelTimings;
  const measured = readTimingValue(dict, def.timingKey);
  const startLog = findLogStartForStage(input.logs, def.logStages);
  const startedAt = startLog ? new Date(startLog.created_at) : undefined;

  if (measured !== null) {
    return buildResolvedStage(def, startedAt, {
      status: "done",
      durationSeconds: measured,
      source: "measured",
    });
  }

  if (jobActive && activeCanonicalId === def.id && startLog) {
    const startMs = new Date(startLog.created_at).getTime();
    const liveSeconds =
      Number.isFinite(startMs) ? Math.max(0, (endMs - startMs) / 1000) : null;
    return buildResolvedStage(def, startedAt, {
      status: "running",
      durationSeconds: liveSeconds,
      source: "live",
    });
  }

  if (!jobActive && activeCanonicalId === def.id && startLog) {
    const startMs = new Date(startLog.created_at).getTime();
    const frozenSeconds =
      Number.isFinite(startMs) ? Math.max(0, (endMs - startMs) / 1000) : null;
    return buildResolvedStage(def, startedAt, {
      status: "done",
      durationSeconds: frozenSeconds,
      source: "live",
    });
  }

  return buildResolvedStage(def, startedAt, {
    status: "pending",
    durationSeconds: null,
    source: null,
  });
}

function resolveHighsTotal(
  highsSubStages: ResolvedStage[],
  modelTimings?: Record<string, number | string> | null,
): { seconds: number | null; source: "measured" | "derived" | null } {
  const solverSeconds = readTimingValue(modelTimings, "solver_seconds");
  if (solverSeconds !== null) {
    return { seconds: solverSeconds, source: "measured" };
  }

  const measuredSubs = highsSubStages
    .map((s) => (s.source === "measured" ? s.durationSeconds : null))
    .filter((v): v is number => v !== null);
  if (measuredSubs.length > 0) {
    return {
      seconds: measuredSubs.reduce((sum, v) => sum + v, 0),
      source: "derived",
    };
  }

  const runOnly = readTimingValue(modelTimings, "solver_run_seconds");
  if (runOnly !== null) {
    return { seconds: runOnly, source: "measured" };
  }

  return { seconds: null, source: null };
}

export function getJobTotalDurationSeconds(input: {
  startedAt?: string | null | undefined;
  finishedAt?: string | null | undefined;
  jobStatus: RunStatus;
  liveNowMs: number;
}): number | null {
  const startMs = input.startedAt ? new Date(input.startedAt).getTime() : null;
  if (startMs == null || !Number.isFinite(startMs)) return null;

  const jobActive = ACTIVE_JOB_STATUSES.has(input.jobStatus);
  let endMs: number | null = null;
  if (input.finishedAt) {
    const finishedMs = new Date(input.finishedAt).getTime();
    if (Number.isFinite(finishedMs)) endMs = finishedMs;
  }
  if (endMs == null) {
    endMs = jobActive ? input.liveNowMs : null;
  }
  if (endMs == null) return null;
  return Math.max(0, (endMs - startMs) / 1000);
}

export function resolveStageTimings(input: ResolveStageTimingsInput): ResolvedStageTimings {
  const jobActive = ACTIVE_JOB_STATUSES.has(input.jobStatus);
  const endMs = jobActive
    ? input.liveNowMs
    : input.finishedAt
      ? new Date(input.finishedAt).getTime()
      : input.logs.length
        ? new Date(input.logs[input.logs.length - 1]!.created_at).getTime()
        : input.liveNowMs;

  const activeCanonicalId = resolveActiveCanonicalId(input.logs);
  const stages = CANONICAL_STAGES.map((def) =>
    resolveOneStage(def, input, activeCanonicalId, jobActive, endMs),
  );

  const highsSubStages = stages.filter((s) => s.highsSubStage);
  const hasHighsKeys =
    highsSubStages.some((s) => s.source === "measured") ||
    readTimingValue(input.modelTimings, "solver_seconds") !== null ||
    readTimingValue(input.modelTimings, "solver_run_seconds") !== null;

  const highsTotal = hasHighsKeys
    ? resolveHighsTotal(highsSubStages, input.modelTimings)
    : { seconds: null, source: null };

  const nonHighsStages = stages.filter((s) => !s.highsSubStage);
  const currentStage =
    stages.find((s) => s.status === "running") ??
    (activeCanonicalId ? stages.find((s) => s.id === activeCanonicalId) ?? null : null);

  const rawSolverStatus = input.modelTimings?.solver_status;
  const solverStatus =
    typeof rawSolverStatus === "string" && rawSolverStatus.trim()
      ? rawSolverStatus
      : null;

  return {
    stages: nonHighsStages,
    highsSubStages: hasHighsKeys ? highsSubStages : [],
    highsTotalSeconds: highsTotal.seconds,
    highsTotalSource: highsTotal.source,
    solverStatus,
    currentStage,
    totalSeconds: getJobTotalDurationSeconds({
      startedAt: input.startedAt,
      finishedAt: input.finishedAt,
      jobStatus: input.jobStatus,
      liveNowMs: input.liveNowMs,
    }),
    jobActive,
  };
}

export function formatReadableDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds == null || !Number.isFinite(totalSeconds)) return "—";
  const safeSeconds = Math.max(0, Math.round(totalSeconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;

  if (hours > 0) return `${hours} h ${minutes} min ${seconds} s`;
  if (minutes > 0) return `${minutes} min ${seconds} s`;
  return `${seconds} s`;
}

/** Las 3 etapas más lentas con medición disponible (para resumen compacto). */
export function getTopSlowStages(
  resolved: ResolvedStageTimings,
  limit = 3,
): Array<{ label: string; durationSeconds: number }> {
  const all = [...resolved.stages, ...resolved.highsSubStages].filter(
    (s) => s.durationSeconds !== null && s.source === "measured",
  );
  return all
    .sort((a, b) => (b.durationSeconds ?? 0) - (a.durationSeconds ?? 0))
    .slice(0, limit)
    .map((s) => ({ label: s.label, durationSeconds: s.durationSeconds! }));
}
