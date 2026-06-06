import { formatReadableDuration } from "@/features/simulation/simulationStageTimings";
import type { RuntimeResourceSample } from "@/types/domain";

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatCompactNumber(value: unknown, suffix = ""): string {
  const num = asNumber(value);
  if (num === null) return "—";
  return `${num.toLocaleString("es-CO", { maximumFractionDigits: 1 })}${suffix}`;
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

export function ResourceTimeline({
  samples,
  title = "Timeline de recursos por paso",
}: {
  samples: RuntimeResourceSample[];
  title?: string;
}) {
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
      <div className="text-xs text-slate-500">{title}</div>
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
