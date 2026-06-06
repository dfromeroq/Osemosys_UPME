import type { JsonValue, RunStatus, SimulationLog } from "@/types/domain";

export type StageTimingStatus = "pending" | "running" | "done";
export type StageTimingSource = "measured" | "live" | "inferred" | null;
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
  | "process_results_precompute"
  | "process_results_typed"
  | "process_results_intermediate"
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
  /** Sub-etapa del bloque de procesamiento de resultados. */
  resultsSubStage?: boolean;
  /** Claves legacy en model_timings si timingKey aún no existe. */
  fallbackTimingKeys?: string[];
};

/** Etapas de log que son marcadores (sin duración propia). */
export const MARKER_LOG_STAGES = new Set([
  "solver",
  "solver_start",
  "data_loaded",
  "instance_ready",
  "create_instance",
  "process_results",
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
    id: "process_results_precompute",
    label: "Precomputar agregados de actividad",
    timingKey: "process_results_precompute_seconds",
    source: "model_timings",
    logStages: ["process_results_precompute", "process_results"],
    resultsSubStage: true,
    fallbackTimingKeys: ["precompute_roa_aggregates_seconds"],
  },
  {
    id: "process_results_typed",
    label: "Extraer dispatch, capacidad y emisiones",
    timingKey: "process_results_typed_seconds",
    source: "model_timings",
    logStages: ["process_results_typed"],
    resultsSubStage: true,
    fallbackTimingKeys: ["extract_results_seconds"],
  },
  {
    id: "process_results_intermediate",
    label: "Extraer variables intermedias Pyomo",
    timingKey: "process_results_intermediate_seconds",
    source: "model_timings",
    logStages: ["process_results_intermediate"],
    resultsSubStage: true,
    fallbackTimingKeys: ["intermediate_vars_seconds"],
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

const PREAMBLE_STAGE_IDS: CanonicalStageId[] = [
  "extract_data",
  "data_processing",
  "declare_model",
  "create_instance",
];

const EPILOGUE_STAGE_IDS: CanonicalStageId[] = [
  "persist_results",
  "infeasibility_analysis",
];

/** Bloques contiguos del pipeline; entre bloques puede haber marcadores sin tiempo propio. */
const STAGE_BLOCKS: Array<{ first: number; last: number }> = [
  { first: 0, last: 3 },
  { first: 4, last: 7 },
  { first: 8, last: 10 },
  { first: 11, last: 12 },
];

function blockForStageIndex(stageIndex: number): { first: number; last: number } | null {
  return STAGE_BLOCKS.find((b) => stageIndex >= b.first && stageIndex <= b.last) ?? null;
}

function getStageIndex(id: CanonicalStageId): number {
  return CANONICAL_STAGES.findIndex((s) => s.id === id);
}

export type ResolvedStage = {
  id: CanonicalStageId;
  label: string;
  status: StageTimingStatus;
  durationSeconds: number | null;
  source: StageTimingSource;
  startedAt?: Date | undefined;
  highsSubStage?: boolean | undefined;
  resultsSubStage?: boolean | undefined;
};

export type StageGroupBlock = {
  title: string;
  stages: ResolvedStage[];
  totalSeconds: number | null;
  totalSource: "measured" | "derived" | null;
  solverStatus?: string | null;
};

export type ResolvedStageTimings = {
  /** Etapas previas al solve (insumos → instancia Pyomo). */
  preambleStages: ResolvedStage[];
  highsGroup: StageGroupBlock;
  resultsGroup: StageGroupBlock;
  /** Persistencia y análisis posterior. */
  epilogueStages: ResolvedStage[];
  /** @deprecated Usar preambleStages + epilogueStages. */
  stages: ResolvedStage[];
  /** @deprecated Usar highsGroup.stages. */
  highsSubStages: ResolvedStage[];
  highsTotalSeconds: number | null;
  highsTotalSource: "measured" | "derived" | null;
  /** @deprecated Usar resultsGroup.stages. */
  resultsSubStages: ResolvedStage[];
  resultsTotalSeconds: number | null;
  resultsTotalSource: "measured" | "derived" | null;
  solverStatus: string | null;
  currentStage: ResolvedStage | null;
  totalSeconds: number | null;
  jobActive: boolean;
};

export type ResolveStageTimingsInput = {
  logs: SimulationLog[];
  stageTimes?: Record<string, number | string> | null | undefined;
  modelTimings?: Record<string, JsonValue> | null | undefined;
  jobStatus: RunStatus;
  liveNowMs: number;
  startedAt?: string | null | undefined;
  finishedAt?: string | null | undefined;
};

function normalizeLogStage(stage: string | null | undefined): string {
  return (stage ?? "general").trim().toLowerCase();
}

function readTimingValue(
  dict: Record<string, JsonValue> | Record<string, number | string> | null | undefined,
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

function logTimestampMs(log: SimulationLog): number | null {
  const ms = new Date(log.created_at).getTime();
  return Number.isFinite(ms) ? ms : null;
}

function findEarliestLogForStage(logs: SimulationLog[], logStages: string[]): SimulationLog | null {
  const wanted = new Set(logStages.map((s) => s.toLowerCase()));
  let best: SimulationLog | null = null;
  let bestMs: number | null = null;
  for (const log of logs) {
    if (!wanted.has(normalizeLogStage(log.stage))) continue;
    const ms = logTimestampMs(log);
    if (ms == null) continue;
    if (bestMs == null || ms < bestMs) {
      best = log;
      bestMs = ms;
    }
  }
  return best;
}

function findEarliestLogMsForStages(logs: SimulationLog[], logStages: string[]): number | null {
  const log = findEarliestLogForStage(logs, logStages);
  return log ? logTimestampMs(log) : null;
}

function findNextCanonicalStageStartMs(logs: SimulationLog[], stageIndex: number): number | null {
  const nextDef = CANONICAL_STAGES[stageIndex + 1];
  if (!nextDef) return null;
  return findEarliestLogMsForStages(logs, nextDef.logStages);
}

/** Índice más avanzado alcanzado según los logs (ignora marcadores sin mapeo). */
function resolveReachedStageIndexFromLogs(logs: SimulationLog[]): number {
  let maxIdx = -1;
  for (const log of logs) {
    const canonical = LOG_STAGE_TO_CANONICAL.get(normalizeLogStage(log.stage));
    if (!canonical) continue;
    const idx = getStageIndex(canonical);
    if (idx > maxIdx) maxIdx = idx;
  }
  return maxIdx;
}

/** Índice de la etapa más avanzada con tiempo medido ya persistido en el worker. */
function resolveHighestCompletedStageIndexFromTimings(
  input: Pick<ResolveStageTimingsInput, "stageTimes" | "modelTimings">,
): number {
  let maxCompleted = -1;
  for (let i = 0; i < CANONICAL_STAGES.length; i++) {
    const def = CANONICAL_STAGES[i]!;
    const dict = def.source === "stage_times" ? input.stageTimes : input.modelTimings;
    if (readMeasuredTiming(dict, def) !== null) {
      maxCompleted = i;
    }
  }
  return maxCompleted;
}

/**
 * Índice efectivo de progreso: combina logs y timings parciales del worker.
 * Evita que el contador en vivo siga en una etapa cuando la siguiente ya terminó
 * en el backend pero el log aún no llegó al frontend.
 */
function resolveEffectiveReachedIndex(
  logs: SimulationLog[],
  input: Pick<ResolveStageTimingsInput, "stageTimes" | "modelTimings">,
): number {
  const fromLogs = resolveReachedStageIndexFromLogs(logs);
  const completedByTiming = resolveHighestCompletedStageIndexFromTimings(input);
  const fromTimings =
    completedByTiming >= 0
      ? Math.min(completedByTiming + 1, CANONICAL_STAGES.length - 1)
      : -1;
  return Math.max(fromLogs, fromTimings);
}

function resolveImmediatePreviousEndMs(
  stageIndex: number,
  input: ResolveStageTimingsInput,
): number | null {
  const prevDef = CANONICAL_STAGES[stageIndex - 1]!;
  const prevDict = prevDef.source === "stage_times" ? input.stageTimes : input.modelTimings;
  const prevMeasured = readMeasuredTiming(prevDict, prevDef);
  const prevStart = findEarliestLogMsForStages(input.logs, prevDef.logStages);
  if (prevMeasured != null && prevStart != null) {
    return prevStart + prevMeasured * 1000;
  }
  return findNextCanonicalStageStartMs(input.logs, stageIndex - 1);
}

function resolveLastBlockEndMs(
  stageIndex: number,
  input: ResolveStageTimingsInput,
): number | null {
  const block = blockForStageIndex(stageIndex);
  if (!block) return null;
  const blockIdx = STAGE_BLOCKS.indexOf(block);
  if (blockIdx <= 0) return null;

  const prevBlock = STAGE_BLOCKS[blockIdx - 1]!;
  const lastDef = CANONICAL_STAGES[prevBlock.last]!;
  const dict = lastDef.source === "stage_times" ? input.stageTimes : input.modelTimings;
  const measured = readMeasuredTiming(dict, lastDef);
  const start = findEarliestLogMsForStages(input.logs, lastDef.logStages);
  if (measured != null && start != null) {
    return start + measured * 1000;
  }
  return findNextCanonicalStageStartMs(input.logs, prevBlock.last);
}

/**
 * Fin de la etapa anterior (ancla mínima del inicio de la etapa actual).
 * Dentro de un bloque usa la etapa previa inmediata; entre bloques evita heredar
 * tiempos de bloques no contiguos (p. ej. create_instance → write_lp).
 */
function resolvePreviousStageEndMs(
  stageIndex: number,
  input: ResolveStageTimingsInput,
): number | null {
  if (stageIndex <= 0) return null;

  const block = blockForStageIndex(stageIndex);
  const prevBlock = blockForStageIndex(stageIndex - 1);

  if (block != null && block.first === stageIndex && block !== prevBlock) {
    if (stageIndex === 4) {
      // Tras create_instance hay marcadores (instance_ready, solver, …) sin duración propia.
      return findEarliestLogMsForStages(input.logs, CANONICAL_STAGES[stageIndex]!.logStages);
    }
    return (
      resolveLastBlockEndMs(stageIndex, input) ??
      findNextCanonicalStageStartMs(input.logs, stageIndex - 1)
    );
  }

  return resolveImmediatePreviousEndMs(stageIndex, input);
}

/**
 * Inicio de una etapa para contadores en vivo / inferencia.
 * Nunca puede ser anterior al fin de la etapa previa (evita heredar 1:17 de write_lp).
 */
function resolveStageStartMs(
  stageIndex: number,
  input: ResolveStageTimingsInput,
  def: CanonicalStageDef,
): number | null {
  const prevEnd = resolvePreviousStageEndMs(stageIndex, input);
  const ownLog = findEarliestLogMsForStages(input.logs, def.logStages);

  if (ownLog != null) {
    if (prevEnd != null && ownLog < prevEnd) {
      return prevEnd;
    }
    return ownLog;
  }

  if (prevEnd != null) return prevEnd;

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
    ...(def.resultsSubStage ? { resultsSubStage: true } : {}),
  };
}

function readMeasuredTiming(
  dict: Record<string, JsonValue> | Record<string, number | string> | null | undefined,
  def: CanonicalStageDef,
): number | null {
  const primary = readTimingValue(dict, def.timingKey);
  if (primary !== null) return primary;
  for (const key of def.fallbackTimingKeys ?? []) {
    const fallback = readTimingValue(dict, key);
    if (fallback !== null) return fallback;
  }
  return null;
}

function resolveOneStage(
  def: CanonicalStageDef,
  stageIndex: number,
  input: ResolveStageTimingsInput,
  reachedIndex: number,
  jobActive: boolean,
  endMs: number,
): ResolvedStage {
  const dict = def.source === "stage_times" ? input.stageTimes : input.modelTimings;
  const measured = readMeasuredTiming(dict, def);
  const startLog = findEarliestLogForStage(input.logs, def.logStages);
  const startMs = resolveStageStartMs(stageIndex, input, def);
  const startedAt =
    startMs != null
      ? new Date(startMs)
      : startLog
        ? new Date(startLog.created_at)
        : undefined;

  if (measured !== null) {
    return buildResolvedStage(def, startedAt, {
      status: "done",
      durationSeconds: measured,
      source: "measured",
    });
  }

  if (reachedIndex < 0) {
    return buildResolvedStage(def, startedAt, {
      status: "pending",
      durationSeconds: null,
      source: null,
    });
  }

  if (stageIndex < reachedIndex) {
    if (startMs != null && Number.isFinite(startMs)) {
      const nextStageMs = findNextCanonicalStageStartMs(input.logs, stageIndex);
      const endPointMs = nextStageMs ?? endMs;
      const inferredSeconds = Math.max(0, (endPointMs - startMs) / 1000);
      return buildResolvedStage(def, startedAt, {
        status: "done",
        durationSeconds: inferredSeconds > 0 ? inferredSeconds : null,
        source: inferredSeconds > 0 ? "inferred" : null,
      });
    }
    return buildResolvedStage(def, startedAt, {
      status: "done",
      durationSeconds: null,
      source: null,
    });
  }

  if (stageIndex === reachedIndex) {
    const nextStageMs = findNextCanonicalStageStartMs(input.logs, stageIndex);
    if (
      nextStageMs != null &&
      startMs != null &&
      Number.isFinite(startMs) &&
      nextStageMs > startMs
    ) {
      const inferredSeconds = Math.max(0, (nextStageMs - startMs) / 1000);
      return buildResolvedStage(def, startedAt, {
        status: "done",
        durationSeconds: inferredSeconds > 0 ? inferredSeconds : null,
        source: inferredSeconds > 0 ? "inferred" : null,
      });
    }

    if (jobActive) {
      const durationSeconds =
        startMs != null && Number.isFinite(startMs)
          ? Math.max(0, (endMs - startMs) / 1000)
          : null;
      return buildResolvedStage(def, startedAt, {
        status: "running",
        durationSeconds,
        source: startMs != null ? "live" : null,
      });
    }
    if (startMs != null && Number.isFinite(startMs)) {
      return buildResolvedStage(def, startedAt, {
        status: "done",
        durationSeconds: Math.max(0, (endMs - startMs) / 1000),
        source: "inferred",
      });
    }
    return buildResolvedStage(def, startedAt, {
      status: "done",
      durationSeconds: null,
      source: null,
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
  modelTimings?: Record<string, JsonValue> | null,
): { seconds: number | null; source: "measured" | "derived" | null } {
  const measuredSubs = highsSubStages
    .map((s) => (s.source === "measured" ? s.durationSeconds : null))
    .filter((v): v is number => v !== null);
  if (measuredSubs.length >= 2) {
    return {
      seconds: measuredSubs.reduce((sum, v) => sum + v, 0),
      source: "derived",
    };
  }

  const solverSeconds = readTimingValue(modelTimings, "solver_seconds");
  if (solverSeconds !== null) {
    return { seconds: solverSeconds, source: "measured" };
  }

  if (measuredSubs.length > 0) {
    return {
      seconds: measuredSubs.reduce((sum, v) => sum + v, 0),
      source: "derived",
    };
  }

  const timedSubs = highsSubStages
    .map((s) => (s.durationSeconds !== null ? s.durationSeconds : null))
    .filter((v): v is number => v !== null);
  if (timedSubs.length > 0) {
    return {
      seconds: timedSubs.reduce((sum, v) => sum + v, 0),
      source: "derived",
    };
  }

  const runOnly = readTimingValue(modelTimings, "solver_run_seconds");
  if (runOnly !== null) {
    return { seconds: runOnly, source: "measured" };
  }

  return { seconds: null, source: null };
}

function resolveResultsTotal(
  resultsSubStages: ResolvedStage[],
  modelTimings?: Record<string, JsonValue> | null,
): { seconds: number | null; source: "measured" | "derived" | null } {
  const measuredSubs = resultsSubStages
    .map((s) => (s.source === "measured" ? s.durationSeconds : null))
    .filter((v): v is number => v !== null);
  if (measuredSubs.length >= 2) {
    return {
      seconds: measuredSubs.reduce((sum, v) => sum + v, 0),
      source: "derived",
    };
  }

  const totalSeconds = readTimingValue(modelTimings, "results_processing_seconds");
  if (totalSeconds !== null) {
    return { seconds: totalSeconds, source: "measured" };
  }

  if (measuredSubs.length > 0) {
    return {
      seconds: measuredSubs.reduce((sum, v) => sum + v, 0),
      source: "derived",
    };
  }

  const timedSubs = resultsSubStages
    .map((s) => (s.durationSeconds !== null ? s.durationSeconds : null))
    .filter((v): v is number => v !== null);
  if (timedSubs.length > 0) {
    return {
      seconds: timedSubs.reduce((sum, v) => sum + v, 0),
      source: "derived",
    };
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

  const reachedIndex = resolveEffectiveReachedIndex(input.logs, input);
  const stages = CANONICAL_STAGES.map((def, stageIndex) =>
    resolveOneStage(def, stageIndex, input, reachedIndex, jobActive, endMs),
  );

  const stageById = new Map(stages.map((s) => [s.id, s]));
  const preambleStages = PREAMBLE_STAGE_IDS.map((id) => stageById.get(id)!);
  const epilogueStages = EPILOGUE_STAGE_IDS.map((id) => stageById.get(id)!);

  const highsSubStages = stages.filter((s) => s.highsSubStage);
  const highsTotal = resolveHighsTotal(highsSubStages, input.modelTimings);

  const resultsSubStages = stages.filter((s) => s.resultsSubStage);
  const resultsTotal = resolveResultsTotal(resultsSubStages, input.modelTimings);

  const nonGroupedStages = [...preambleStages, ...epilogueStages];
  const currentStage =
    stages.find((s) => s.status === "running") ??
    (reachedIndex >= 0 ? (stages[reachedIndex] ?? null) : null);

  const rawSolverStatus = input.modelTimings?.solver_status;
  const solverStatus =
    typeof rawSolverStatus === "string" && rawSolverStatus.trim()
      ? rawSolverStatus
      : null;

  return {
    preambleStages,
    highsGroup: {
      title: "Optimización HiGHS",
      stages: highsSubStages,
      totalSeconds: highsTotal.seconds,
      totalSource: highsTotal.source,
      solverStatus,
    },
    resultsGroup: {
      title: "Procesamiento de resultados",
      stages: resultsSubStages,
      totalSeconds: resultsTotal.seconds,
      totalSource: resultsTotal.source,
    },
    epilogueStages,
    stages: nonGroupedStages,
    highsSubStages,
    highsTotalSeconds: highsTotal.seconds,
    highsTotalSource: highsTotal.source,
    resultsSubStages,
    resultsTotalSeconds: resultsTotal.seconds,
    resultsTotalSource: resultsTotal.source,
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
  const all = [
    ...resolved.stages,
    ...resolved.highsSubStages,
    ...resolved.resultsSubStages,
  ].filter(
    (s) => s.durationSeconds !== null && s.source === "measured",
  );
  return all
    .sort((a, b) => (b.durationSeconds ?? 0) - (a.durationSeconds ?? 0))
    .slice(0, limit)
    .map((s) => ({ label: s.label, durationSeconds: s.durationSeconds! }));
}
