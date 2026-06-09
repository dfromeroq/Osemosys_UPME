import { formatReadableDuration } from "@/features/simulation/simulationStageTimings";
import type { RuntimeResourceSample } from "@/types/domain";

export type ResourceTimelineCapacity = {
  cpuCores?: number | null | undefined;
  totalRamGb?: number | null | undefined;
  currentCpuPercent?: number | null | undefined;
  currentRamUsedGb?: number | null | undefined;
};

const SEGMENT_COLORS = ["#0ea5e9", "#22c55e", "#f59e0b", "#a78bfa", "#ef4444", "#14b8a6"];

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function formatNumber(value: unknown, suffix = "", digits = 1): string {
  const num = asNumber(value);
  if (num === null) return "—";
  return `${num.toLocaleString("es-CO", { maximumFractionDigits: digits })}${suffix}`;
}

function mbToGb(value: unknown): number | null {
  const mb = asNumber(value);
  return mb === null ? null : mb / 1024;
}

function cleanStageName(stage: string | undefined): string {
  return (stage ?? "sample")
    .replace(/_seconds$/, "")
    .replace(/_complete$/, "")
    .replace(/_/g, " ");
}

function shortStageName(stage: string | undefined): string {
  const clean = cleanStageName(stage);
  return clean.length > 20 ? `${clean.slice(0, 18)}…` : clean;
}

function prepareSamples(samples: RuntimeResourceSample[]): RuntimeResourceSample[] {
  return samples
    .filter((sample) => asNumber(sample.elapsed_seconds) !== null)
    .sort((a, b) => (asNumber(a.elapsed_seconds) ?? 0) - (asNumber(b.elapsed_seconds) ?? 0));
}

function pointPath(
  samples: RuntimeResourceSample[],
  read: (sample: RuntimeResourceSample) => number | null,
  scaleMax: number,
  totalSeconds: number,
): string {
  const x0 = 48;
  const width = 1060;
  const y0 = 68;
  const height = 130;
  return samples
    .map((sample) => {
      const elapsed = asNumber(sample.elapsed_seconds) ?? 0;
      const value = clamp((read(sample) ?? 0) / Math.max(1, scaleMax), 0, 1);
      const x = x0 + (elapsed / Math.max(1, totalSeconds)) * width;
      const y = y0 + (1 - value) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function ResourceTimeline({
  samples,
  title = "Timeline de recursos por paso",
  capacity,
}: {
  samples: RuntimeResourceSample[];
  title?: string;
  capacity?: ResourceTimelineCapacity | undefined;
}) {
  const prepared = prepareSamples(samples);
  if (prepared.length < 2) return null;

  const totalSeconds = Math.max(...prepared.map((sample) => asNumber(sample.elapsed_seconds) ?? 0), 1);
  const cpuCores = Math.max(1, asNumber(capacity?.cpuCores) ?? 1);
  const maxSampleCpuCores = Math.max(
    1,
    ...prepared.map((sample) => ((asNumber(sample.process_cpu_percent) ?? 0) / 100)),
  );
  const cpuScale = Math.max(cpuCores, maxSampleCpuCores);
  const totalRamGb = Math.max(
    1,
    asNumber(capacity?.totalRamGb) ?? Math.max(...prepared.map((sample) => mbToGb(sample.rss_mb) ?? 0), 1),
  );
  const threadScale = Math.max(cpuCores, ...prepared.map((sample) => asNumber(sample.threads) ?? 0), 1);
  const maxRamGb = Math.max(...prepared.map((sample) => mbToGb(sample.rss_mb) ?? 0), 0);
  const maxCpuCores = Math.max(...prepared.map((sample) => (asNumber(sample.process_cpu_percent) ?? 0) / 100), 0);
  const maxThreads = Math.max(...prepared.map((sample) => asNumber(sample.threads) ?? 0), 0);
  const currentCpuCores =
    asNumber(capacity?.currentCpuPercent) !== null
      ? ((asNumber(capacity?.currentCpuPercent) ?? 0) / 100) * cpuCores
      : null;
  const currentRamGb = asNumber(capacity?.currentRamUsedGb);
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  const x0 = 48;
  const width = 900;
  const chartTop = 68;
  const chartHeight = 130;
  const segmentTop = 34;
  const segmentHeight = 18;
  const yFor = (value: number, scaleMax: number) =>
    chartTop + (1 - clamp(value / Math.max(1, scaleMax), 0, 1)) * chartHeight;
  const xFor = (elapsed: number) => x0 + (elapsed / totalSeconds) * width;

  const segments = prepared.slice(1).map((sample, idx) => {
    const previous = prepared[idx] ?? sample;
    const start = asNumber(previous.elapsed_seconds) ?? 0;
    const end = asNumber(sample.elapsed_seconds) ?? start;
    const duration = Math.max(0, end - start);
    return {
      key: `${sample.stage ?? "sample"}-${idx}`,
      label: cleanStageName(sample.stage),
      shortLabel: shortStageName(sample.stage),
      start,
      end,
      duration,
      color: SEGMENT_COLORS[idx % SEGMENT_COLORS.length],
      sample,
    };
  });

  return (
    <div style={{ display: "grid", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div className="text-xs text-slate-500">{title}</div>
        <div className="flex flex-wrap gap-3 text-xs text-slate-400">
          <span>CPU cap {formatNumber(cpuCores, " cores", 0)}</span>
          <span>RAM total {formatNumber(totalRamGb, " GB", 1)}</span>
          {currentCpuCores !== null ? <span>CPU actual {formatNumber(currentCpuCores, " cores", 1)}</span> : null}
          {currentRamGb !== null ? <span>RAM actual {formatNumber(currentRamGb, " GB", 1)}</span> : null}
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <svg
          role="img"
          aria-label="Timeline de duración, RAM, CPU e hilos por paso de simulación"
          viewBox="0 0 1160 250"
          style={{ minWidth: 1040, width: "100%", height: 270, display: "block" }}
        >
          <rect x="0" y="0" width="1160" height="250" rx="8" fill="rgba(2,6,23,0.35)" />

          {segments.map((segment) => {
            const x = xFor(segment.start);
            const segmentWidth = Math.max(2, xFor(segment.end) - x);
            const showText = segmentWidth > 78;
            return (
              <g key={segment.key}>
                <rect
                  x={x}
                  y={segmentTop}
                  width={segmentWidth}
                  height={segmentHeight}
                  rx="3"
                  fill={segment.color}
                  opacity="0.82"
                >
                  <title>{`${segment.label}: ${formatReadableDuration(segment.duration)}`}</title>
                </rect>
                {showText ? (
                  <text x={x + 6} y={segmentTop + 13} fill="#020617" fontSize="10" fontWeight="700">
                    {segment.shortLabel}
                  </text>
                ) : null}
              </g>
            );
          })}

          {ticks.map((tick) => {
            const x = x0 + tick * width;
            return (
              <g key={tick}>
                <line x1={x} y1={chartTop} x2={x} y2={chartTop + chartHeight} stroke="rgba(148,163,184,0.15)" />
                <text x={x} y="222" textAnchor="middle" fill="rgba(148,163,184,0.82)" fontSize="10">
                  {formatReadableDuration(totalSeconds * tick)}
                </text>
              </g>
            );
          })}
          {[0, 0.5, 1].map((tick) => {
            const y = chartTop + (1 - tick) * chartHeight;
            return (
              <g key={tick}>
                <line x1={x0} y1={y} x2={x0 + width} y2={y} stroke="rgba(148,163,184,0.12)" />
                <text x="8" y={y + 4} fill="rgba(56,189,248,0.82)" fontSize="10">
                  {formatNumber(tick * totalRamGb, "", 0)}
                </text>
                <text x="1118" y={y + 4} fill="rgba(245,158,11,0.85)" fontSize="10">
                  {formatNumber(tick * cpuScale, "", 1)}
                </text>
              </g>
            );
          })}
          <text x="8" y="64" fill="rgba(56,189,248,0.82)" fontSize="10">GB</text>
          <text x="1090" y="64" fill="rgba(245,158,11,0.85)" fontSize="10">cores/hilos</text>

          {currentCpuCores !== null ? (
            <g>
              <line
                x1={x0}
                y1={yFor(currentCpuCores, cpuScale)}
                x2={x0 + width}
                y2={yFor(currentCpuCores, cpuScale)}
                stroke="#f97316"
                strokeDasharray="5 5"
                opacity="0.7"
              />
              <text
                x={x0 + width - 6}
                y={yFor(currentCpuCores, cpuScale) - 4}
                textAnchor="end"
                fill="#fed7aa"
                fontSize="10"
              >
                CPU actual {formatNumber(currentCpuCores, " cores", 1)}
              </text>
            </g>
          ) : null}
          {currentRamGb !== null ? (
            <g>
              <line
                x1={x0}
                y1={yFor(currentRamGb, totalRamGb)}
                x2={x0 + width}
                y2={yFor(currentRamGb, totalRamGb)}
                stroke="#67e8f9"
                strokeDasharray="5 5"
                opacity="0.7"
              />
              <text
                x={x0 + 6}
                y={yFor(currentRamGb, totalRamGb) - 4}
                fill="#a5f3fc"
                fontSize="10"
              >
                RAM actual {formatNumber(currentRamGb, " GB", 1)}
              </text>
            </g>
          ) : null}

          <polyline
            fill="none"
            stroke="#38bdf8"
            strokeWidth="2.2"
            points={pointPath(prepared, (sample) => mbToGb(sample.rss_mb), totalRamGb, totalSeconds)}
          />
          <polyline
            fill="none"
            stroke="#f59e0b"
            strokeWidth="2.2"
            points={pointPath(
              prepared,
              (sample) => (asNumber(sample.process_cpu_percent) ?? 0) / 100,
              cpuScale,
              totalSeconds,
            )}
          />
          <polyline
            fill="none"
            stroke="#a78bfa"
            strokeWidth="2.2"
            points={pointPath(prepared, (sample) => asNumber(sample.threads), threadScale, totalSeconds)}
          />

          {prepared.map((sample, idx) => {
            const elapsed = asNumber(sample.elapsed_seconds) ?? 0;
            const x = xFor(elapsed);
            const label = cleanStageName(sample.stage);
            return (
              <g key={`${sample.stage ?? "sample"}-${idx}`}>
                <circle cx={x} cy={yFor(mbToGb(sample.rss_mb) ?? 0, totalRamGb)} r="3" fill="#38bdf8">
                  <title>{`${label}: RAM ${formatNumber(mbToGb(sample.rss_mb), " GB", 2)}`}</title>
                </circle>
                <circle
                  cx={x}
                  cy={yFor((asNumber(sample.process_cpu_percent) ?? 0) / 100, cpuScale)}
                  r="3"
                  fill="#f59e0b"
                >
                  <title>{`${label}: CPU ${formatNumber((asNumber(sample.process_cpu_percent) ?? 0) / 100, " cores", 2)}`}</title>
                </circle>
                <circle cx={x} cy={yFor(asNumber(sample.threads) ?? 0, threadScale)} r="3" fill="#a78bfa">
                  <title>{`${label}: hilos ${formatNumber(sample.threads)}`}</title>
                </circle>
              </g>
            );
          })}

          <g transform="translate(54 18)" fontSize="11" fill="rgba(203,213,225,0.92)">
            <circle cx="0" cy="0" r="4" fill="#38bdf8" />
            <text x="9" y="4">RAM sim max {formatNumber(maxRamGb, " GB", 2)} / total {formatNumber(totalRamGb, " GB", 1)}</text>
            <circle cx="245" cy="0" r="4" fill="#f59e0b" />
            <text x="254" y="4">CPU sim max {formatNumber(maxCpuCores, " cores", 2)} / cap {formatNumber(cpuScale, " cores", 0)}</text>
            <circle cx="485" cy="0" r="4" fill="#a78bfa" />
            <text x="494" y="4">Hilos max {formatNumber(maxThreads, "", 0)} / escala {formatNumber(threadScale, "", 0)}</text>
            <rect x="670" y="-4" width="16" height="8" rx="2" fill="#22c55e" />
            <text x="694" y="4">Duración</text>
          </g>
        </svg>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-3 text-left font-medium">Tramo</th>
              <th className="py-1 pr-3 text-right font-medium">Duración</th>
              <th className="py-1 pr-3 text-right font-medium">CPU</th>
              <th className="py-1 pr-3 text-right font-medium">RAM sim</th>
              <th className="py-1 text-right font-medium">Hilos</th>
            </tr>
          </thead>
          <tbody>
            {segments.slice(-8).map((segment) => (
              <tr key={`${segment.key}-row`} className="border-t border-slate-800/70">
                <td className="py-1 pr-3 text-slate-200">
                  <span
                    aria-hidden
                    style={{
                      display: "inline-block",
                      width: 8,
                      height: 8,
                      borderRadius: 2,
                      background: segment.color,
                      marginRight: 6,
                    }}
                  />
                  {segment.label}
                </td>
                <td className="py-1 pr-3 text-right font-mono text-slate-300">
                  {formatReadableDuration(segment.duration)}
                </td>
                <td className="py-1 pr-3 text-right font-mono text-slate-300">
                  {formatNumber((asNumber(segment.sample.process_cpu_percent) ?? 0) / 100, " cores", 2)}
                </td>
                <td className="py-1 pr-3 text-right font-mono text-slate-300">
                  {formatNumber(mbToGb(segment.sample.rss_mb), " GB", 2)}
                </td>
                <td className="py-1 text-right font-mono text-slate-300">
                  {formatNumber(segment.sample.threads)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
