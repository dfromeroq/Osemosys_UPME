import { useMemo } from "react";
import {
  formatReadableDuration,
  resolveStageTimings,
  type ResolveStageTimingsInput,
  type ResolvedStage,
  type StageGroupBlock,
} from "@/features/simulation/simulationStageTimings";

type Props = ResolveStageTimingsInput & {
  compact?: boolean;
};

function StageStatusIcon({ status }: { status: ResolvedStage["status"] }) {
  if (status === "done") {
    return (
      <span
        aria-hidden
        style={{ color: "rgba(74,222,128,0.95)", fontSize: 14, lineHeight: 1 }}
        title="Completada"
      >
        ✓
      </span>
    );
  }
  if (status === "running") {
    return (
      <span
        aria-hidden
        style={{ color: "rgba(96,165,250,0.95)", fontSize: 14, lineHeight: 1 }}
        title="En curso"
      >
        ◉
      </span>
    );
  }
  return (
    <span
      aria-hidden
      style={{ color: "rgba(148,163,184,0.55)", fontSize: 14, lineHeight: 1 }}
      title="Pendiente"
    >
      ○
    </span>
  );
}

function StageRow({
  stage,
  indent = false,
  compact = false,
}: {
  stage: ResolvedStage;
  indent?: boolean;
  compact?: boolean;
}) {
  const durationLabel =
    stage.durationSeconds !== null
      ? formatReadableDuration(stage.durationSeconds)
      : stage.status === "pending"
        ? "Pendiente"
        : "—";

  const sourceHint =
    stage.source === "measured"
      ? "medido"
      : stage.source === "live"
        ? stage.status === "running"
          ? "en curso"
          : "estimado"
        : stage.source === "inferred"
          ? "estimado"
          : null;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: compact ? "auto 1fr auto" : "auto 1fr auto auto",
        gap: 8,
        alignItems: "center",
        padding: compact ? "4px 0" : "6px 0",
        paddingLeft: indent ? 20 : 0,
      }}
    >
      <StageStatusIcon status={stage.status} />
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontWeight: stage.status === "running" ? 700 : 500,
            fontSize: compact ? 12 : 13,
          }}
        >
          {stage.label}
        </div>
        {!compact && sourceHint ? (
          <div style={{ fontSize: 11, opacity: 0.65 }}>{sourceHint}</div>
        ) : null}
      </div>
      <div
        style={{
          fontWeight: 700,
          fontVariantNumeric: "tabular-nums",
          fontSize: compact ? 13 : 15,
          textAlign: "right",
          whiteSpace: "nowrap",
        }}
      >
        {durationLabel}
      </div>
      {!compact && sourceHint ? (
        <span
          style={{
            fontSize: 10,
            opacity: 0.6,
            padding: "2px 6px",
            borderRadius: 999,
            border: "1px solid rgba(148,163,184,0.25)",
            whiteSpace: "nowrap",
          }}
        >
          {sourceHint}
        </span>
      ) : null}
    </div>
  );
}

function StageGroupSection({
  group,
  compact,
  withBorder,
}: {
  group: StageGroupBlock;
  compact: boolean;
  withBorder: boolean;
}) {
  const hasActivity = group.stages.some((s) => s.status !== "pending");

  return (
    <div
      style={{
        display: "grid",
        gap: 4,
        padding: withBorder ? (compact ? "8px 0 0" : "10px 0 0") : 0,
        borderTop: withBorder ? "1px solid rgba(96,165,250,0.18)" : undefined,
        opacity: hasActivity ? 1 : 0.88,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 8,
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontWeight: 700, fontSize: compact ? 12 : 13 }}>{group.title}</span>
        {group.totalSeconds !== null ? (
          <span
            style={{
              fontWeight: 800,
              fontVariantNumeric: "tabular-nums",
              fontSize: compact ? 13 : 15,
            }}
          >
            {formatReadableDuration(group.totalSeconds)}
            {group.totalSource === "derived" ? (
              <span style={{ fontSize: 10, opacity: 0.65, marginLeft: 6 }}>(suma)</span>
            ) : null}
          </span>
        ) : null}
      </div>
      {group.solverStatus ? (
        <div style={{ fontSize: 11, opacity: 0.75 }}>
          Estado del solver: {group.solverStatus}
        </div>
      ) : null}
      {group.stages.map((stage) => (
        <StageRow key={stage.id} stage={stage} indent compact={compact} />
      ))}
    </div>
  );
}

export function SimulationStageTimeline(props: Props) {
  const {
    compact = false,
    logs,
    stageTimes,
    modelTimings,
    jobStatus,
    liveNowMs,
    startedAt,
    finishedAt,
  } = props;
  const resolved = useMemo(
    () =>
      resolveStageTimings({
        logs,
        stageTimes,
        modelTimings,
        jobStatus,
        liveNowMs,
        startedAt,
        finishedAt,
      }),
    [logs, stageTimes, modelTimings, jobStatus, liveNowMs, startedAt, finishedAt],
  );

  const isSolverInfeasible =
    typeof resolved.solverStatus === "string" &&
    /(infeasible|infactible)/i.test(resolved.solverStatus);
  const shouldHideInfeasibilityPendingRow = (stage: ResolvedStage): boolean =>
    stage.id === "infeasibility_analysis" &&
    stage.status === "pending" &&
    jobStatus === "SUCCEEDED" &&
    !isSolverInfeasible;

  const visibleEpilogueStages = resolved.epilogueStages.filter(
    (stage) => !shouldHideInfeasibilityPendingRow(stage),
  );

  const allStages = [
    ...resolved.preambleStages,
    ...resolved.highsGroup.stages,
    ...resolved.resultsGroup.stages,
    ...visibleEpilogueStages,
  ];

  if (compact && resolved.totalSeconds === null && allStages.every((s) => s.status === "pending")) {
    return null;
  }

  return (
    <div
      style={{
        display: "grid",
        gap: compact ? 8 : 12,
        padding: compact ? 10 : 12,
        borderRadius: 14,
        border: "1px solid rgba(96,165,250,0.22)",
        background: "linear-gradient(180deg, rgba(37,99,235,0.12), rgba(15,23,42,0.28))",
      }}
      title="El tiempo se mide en el worker, no por intervalo entre registros."
    >
      {!compact ? (
        <div style={{ fontSize: 12, opacity: 0.72, lineHeight: 1.45 }}>
          Tiempos medidos en el worker (no por intervalo entre registros de log).
        </div>
      ) : null}

      <div style={{ display: "grid", gap: 2 }}>
        {resolved.preambleStages.map((stage) => (
          <StageRow key={stage.id} stage={stage} compact={compact} />
        ))}

        <StageGroupSection group={resolved.highsGroup} compact={compact} withBorder />

        <StageGroupSection group={resolved.resultsGroup} compact={compact} withBorder />

        {visibleEpilogueStages.map((stage) => (
          <StageRow key={stage.id} stage={stage} compact={compact} />
        ))}
      </div>
    </div>
  );
}
