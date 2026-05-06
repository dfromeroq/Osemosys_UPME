/**
 * InfeasibilityReportPage — reporte unificado de infactibilidad para un job.
 *
 * Vista única (sustituye al modal legacy `InfeasibilityDiagnosticsPanel`).
 * Contiene:
 *   - Resumen (overview): años, tipos, tecnologías.
 *   - Top sospechosos: params con mayor desviación vs default OSeMOSYS.
 *   - Pestaña "Restricciones IIS": tabla expandible con related_params
 *     mostrando valor / default / diff / score.
 *   - Pestaña "Parámetros del escenario": historial de auditoría, con badge
 *     cuando el parámetro también aparece en el IIS.
 *   - Conflictos de bounds de variables + prefijos sin mapeo.
 *   - Botón de descarga JSON.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { scenariosApi } from "@/features/scenarios/api/scenariosApi";
import {
  ScenarioParamsTab,
  type ScenarioParamsForDiagnostics,
} from "@/features/simulation/components/ScenarioParamsTab";
import { simulationApi } from "@/features/simulation/api/simulationApi";
import { paths } from "@/routes/paths";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import type {
  ConstraintAnalysis,
  InfeasibilityDiagnostics,
  InfeasibilityOverview,
  ParamHit,
  RunResult,
} from "@/types/domain";

const CARD_STYLE: React.CSSProperties = {
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 8,
  padding: 16,
  background: "rgba(255,255,255,0.02)",
};

const DANGER_CARD_STYLE: React.CSSProperties = {
  ...CARD_STYLE,
  border: "1px solid rgba(220, 38, 38, 0.4)",
  background: "rgba(127, 29, 29, 0.12)",
};

const WARN_CARD_STYLE: React.CSSProperties = {
  ...CARD_STYLE,
  border: "1px solid rgba(245,158,11,0.45)",
  background: "rgba(120,53,15,0.14)",
};

const TABLE_STYLE: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 13,
};
const TH_STYLE: React.CSSProperties = {
  textAlign: "left",
  padding: "6px 8px",
  borderBottom: "1px solid rgba(255,255,255,0.15)",
  fontWeight: 600,
};
const TD_STYLE: React.CSSProperties = {
  padding: "6px 8px",
  borderBottom: "1px solid rgba(255,255,255,0.05)",
  verticalAlign: "top",
};

type TabId = "iis" | "scenarioParams";

const BOUND_TYPE_LABEL: Record<string, string> = {
  lower: "Límite inferior (≥)",
  upper: "Límite superior (≤)",
  equality: "Igualdad (=)",
};

type ViolationInfo = { label: string; detail: string; description: string };

function glpkViolationInfo(
  analysis: import("@/types/domain").ConstraintAnalysis,
): ViolationInfo | null {
  const act = analysis.body;
  const lb = analysis.lower;
  const ub = analysis.upper;
  const diff = analysis.violation;
  if (act == null || diff <= 0) return null;
  if (lb != null && act < lb) {
    return {
      label: "Límite inferior",
      detail: `act=${formatNumber(act, 4)} < lb=${formatNumber(lb, 4)} · Δ=${formatNumber(diff, 4)}`,
      description: `El modelo produce ${formatNumber(act, 4)} pero el límite inferior exige mínimo ${formatNumber(lb, 4)}.`,
    };
  }
  if (ub != null && act > ub) {
    return {
      label: "Límite superior",
      detail: `act=${formatNumber(act, 4)} > ub=${formatNumber(ub, 4)} · Δ=${formatNumber(diff, 4)}`,
      description: `El modelo produce ${formatNumber(act, 4)} pero el límite superior permite máximo ${formatNumber(ub, 4)}.`,
    };
  }
  if (diff > 0) {
    const sideLabel = analysis.side ? (BOUND_TYPE_LABEL[analysis.side] ?? analysis.side) : "Igualdad";
    return {
      label: sideLabel,
      detail: `Δ=${formatNumber(diff, 4)}`,
      description: `Restricción de igualdad no satisfecha — diferencia de ${formatNumber(diff, 4)}.`,
    };
  }
  return null;
}

function formatNumber(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs !== 0 && (abs < 1e-3 || abs >= 1e6)) return value.toExponential(digits - 1);
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

/** Normaliza un dict de "dimensiones" (ya sea del audit o del IIS) a una
 * representación canónica con claves OSeMOSYS mayúsculas, para poder construir
 * una clave de matching estable entre ambos mundos.
 *
 * El audit usa `region_name`, `technology_name`, `fuel_name`, `emission_name`,
 * `udc_name`, `year`; el IIS usa `REGION`, `TECHNOLOGY`, `FUEL`, `EMISSION`,
 * `UDC`, `YEAR`. Esta función acepta ambas formas. */
function normalizeIndices(
  raw: Record<string, unknown> | null | undefined,
): Record<string, string> {
  const r = raw ?? {};
  const pick = (...keys: string[]): string => {
    for (const k of keys) {
      const v = (r as Record<string, unknown>)[k];
      if (v !== undefined && v !== null && String(v).trim() !== "") {
        return String(v).trim();
      }
    }
    return "";
  };
  return {
    REGION: pick("REGION", "region_name"),
    TECHNOLOGY: pick("TECHNOLOGY", "technology_name"),
    FUEL: pick("FUEL", "fuel_name"),
    EMISSION: pick("EMISSION", "emission_name"),
    UDC: pick("UDC", "udc_name"),
    YEAR: pick("YEAR", "year"),
  };
}

/** Clave canónica (param, índices) usada para comparar entre IIS y audit. */
function paramIndicesKey(
  paramName: string,
  indices: Record<string, string>,
): string {
  const parts: string[] = [paramName.trim()];
  for (const k of ["REGION", "TECHNOLOGY", "FUEL", "EMISSION", "UDC", "YEAR"]) {
    const v = indices[k];
    if (v) parts.push(`${k}=${v}`);
  }
  return parts.join("|");
}

function renderIndices(indices: Record<string, string>): string {
  const entries = Object.entries(indices ?? {});
  if (entries.length === 0) return "—";
  return entries.map(([k, v]) => `${k}=${v}`).join(", ");
}

function scoreColor(score: number | null | undefined): {
  bg: string;
  border: string;
  fg: string;
} {
  // 0 → neutral, 1-49 → amarillo, 50-84 → naranja, 85-100 → rojo intenso.
  if (score === null || score === undefined) {
    return { bg: "rgba(148,163,184,0.14)", border: "rgba(148,163,184,0.3)", fg: "inherit" };
  }
  if (score <= 0) {
    return { bg: "rgba(34,197,94,0.14)", border: "rgba(34,197,94,0.34)", fg: "inherit" };
  }
  if (score < 50) {
    return { bg: "rgba(245,158,11,0.16)", border: "rgba(245,158,11,0.4)", fg: "inherit" };
  }
  if (score < 85) {
    return { bg: "rgba(234,88,12,0.18)", border: "rgba(234,88,12,0.45)", fg: "inherit" };
  }
  return { bg: "rgba(239,68,68,0.22)", border: "rgba(239,68,68,0.55)", fg: "#fecaca" };
}

function ScoreChip({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) {
    return <span style={{ opacity: 0.65, fontSize: 12 }}>—</span>;
  }
  const c = scoreColor(score);
  return (
    <span
      title={`Score de desviación vs default: ${score.toFixed(2)} / 100`}
      style={{
        display: "inline-block",
        minWidth: 44,
        textAlign: "center",
        padding: "2px 8px",
        borderRadius: 999,
        background: c.bg,
        border: `1px solid ${c.border}`,
        color: c.fg,
        fontSize: 12,
        fontWeight: 700,
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {Math.round(score)}
    </span>
  );
}

type IISScenarioChange = {
  id: number;
  paramName: string;
  indices: Record<string, string>;
  oldValue: number | null;
  newValue: number | null;
  changedBy: string;
  createdAt: string;
  matchMode: "indices" | "paramOnly";
};

/** Sección destacada: cambios hechos al escenario (audit log) sobre
 * (parámetro, índices) que aparecen en el diagnóstico del IIS.
 *
 * Es el "smoking gun" del análisis — edits que tocan directamente las
 * restricciones infactibles. Si aparecen muchas filas aquí, son los cambios
 * más sospechosos de haber causado la infactibilidad.
 */
function IISScenarioChangesSection({
  changes,
  loading,
  hasIISParams,
  hasScenarioModifications,
  onOpenAuditTab,
}: {
  changes: IISScenarioChange[];
  loading: boolean;
  hasIISParams: boolean;
  hasScenarioModifications: boolean;
  onOpenAuditTab: () => void;
}) {
  // No mostramos la sección si ni siquiera hay parámetros del IIS (ej. HiGHS
  // sin IIS) o si el escenario no tiene cambios registrados.
  if (!hasIISParams || !hasScenarioModifications) return null;

  return (
    <section style={DANGER_CARD_STYLE}>
      <h2 style={{ margin: "0 0 4px 0", fontSize: 16 }}>
        🎯 Cambios del escenario que tocan el IIS ({changes.length})
      </h2>
      <p style={{ margin: "0 0 12px 0", fontSize: 12, opacity: 0.85 }}>
        Ediciones del historial de este escenario sobre
        (parámetro × índices) que aparecen en las restricciones del IIS.
        Son los cambios más probablemente relacionados con la infactibilidad.
        El historial completo —incluyendo edits que no tocan el IIS— está en la
        pestaña <em>Parámetros del escenario</em>.
      </p>
      {loading ? (
        <small style={{ opacity: 0.78 }}>Buscando cambios relacionados con el IIS…</small>
      ) : changes.length === 0 ? (
        <div
          style={{
            padding: 10,
            borderRadius: 8,
            background: "rgba(34,197,94,0.08)",
            border: "1px solid rgba(34,197,94,0.25)",
          }}
        >
          <small>
            Ningún edit del escenario cae sobre un <code>(parámetro, índices)</code>
            que aparezca en el IIS. Los parámetros que rompen el modelo podrían
            venir de los defaults del modelo o del ZIP de CSVs, no de ediciones
            hechas en la app. Ver <button type="button" onClick={onOpenAuditTab} style={{ background: "none", border: "none", color: "#93c5fd", cursor: "pointer", padding: 0, textDecoration: "underline" }}>Parámetros del escenario</button> para el historial completo.
          </small>
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={TABLE_STYLE}>
            <thead>
              <tr>
                <th style={TH_STYLE}>Parámetro</th>
                <th style={TH_STYLE}>Índices</th>
                <th style={TH_STYLE}>Valor anterior</th>
                <th style={TH_STYLE}>Nuevo valor</th>
                <th style={TH_STYLE}>|Diff|</th>
                <th style={TH_STYLE}>Usuario</th>
                <th style={TH_STYLE}>Fecha</th>
              </tr>
            </thead>
            <tbody>
              {[...changes]
                .sort((a, b) => {
                  const da = Math.abs((a.newValue ?? 0) - (a.oldValue ?? 0));
                  const db = Math.abs((b.newValue ?? 0) - (b.oldValue ?? 0));
                  return db - da;
                })
                .map((c) => {
                  const absDiff =
                    c.newValue !== null && c.oldValue !== null
                      ? Math.abs(c.newValue - c.oldValue)
                      : null;
                  return (
                    <tr key={c.id}>
                      <td style={TD_STYLE}>
                        <code style={{ fontSize: 12 }}>{c.paramName}</code>
                      </td>
                      <td style={TD_STYLE}>{renderIndices(c.indices)}</td>
                      <td style={{ ...TD_STYLE, fontVariantNumeric: "tabular-nums" }}>
                        {c.oldValue !== null ? formatNumber(c.oldValue, 6) : "—"}
                      </td>
                      <td
                        style={{
                          ...TD_STYLE,
                          fontVariantNumeric: "tabular-nums",
                          fontWeight: 600,
                        }}
                      >
                        {c.newValue !== null ? formatNumber(c.newValue, 6) : "—"}
                      </td>
                      <td
                        style={{
                          ...TD_STYLE,
                          fontVariantNumeric: "tabular-nums",
                          fontWeight: 600,
                        }}
                      >
                        {absDiff !== null ? formatNumber(absDiff, 6) : "—"}
                      </td>
                      <td style={{ ...TD_STYLE, fontSize: 12 }}>{c.changedBy}</td>
                      <td style={{ ...TD_STYLE, whiteSpace: "nowrap", fontSize: 12 }}>
                        {new Date(c.createdAt).toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function TopSuspectsSection({
  suspects,
  onPickConstraint,
}: {
  suspects: ParamHit[];
  onPickConstraint: (paramName: string) => void;
}) {
  if (!suspects || suspects.length === 0) return null;
  return (
    <section style={WARN_CARD_STYLE}>
      <h2 style={{ margin: "0 0 4px 0", fontSize: 16 }}>
        🔥 Top sospechosos ({suspects.length})
      </h2>
      <p style={{ margin: "0 0 12px 0", fontSize: 12, opacity: 0.85 }}>
        Parámetros del IIS con mayor <strong>|diff|</strong> (diferencia absoluta
        entre valor actual y default OSeMOSYS). Ordenados de mayor a menor;
        cuando el default es 0, el score satura en 100 por lo que la diferencia
        absoluta evita ese sesgo. Click en uno para saltar a la restricción
        relacionada.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {suspects.map((hit, i) => {
          const absDiff =
            typeof hit.diff_abs === "number" ? Math.abs(hit.diff_abs) : null;
          return (
            <button
              key={`${hit.param}-${i}`}
              type="button"
              onClick={() => onPickConstraint(hit.param)}
              style={{
                display: "grid",
                gap: 2,
                padding: "8px 10px",
                borderRadius: 8,
                border: "1px solid rgba(239,68,68,0.35)",
                background: "rgba(127,29,29,0.2)",
                color: "inherit",
                cursor: "pointer",
                textAlign: "left",
                minWidth: 220,
              }}
            >
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <code style={{ fontSize: 12 }}>{hit.param}</code>
                {absDiff !== null ? (
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: 999,
                      background: "rgba(239,68,68,0.22)",
                      border: "1px solid rgba(239,68,68,0.55)",
                      fontVariantNumeric: "tabular-nums",
                    }}
                    title={`|diff| = |${hit.value} − ${hit.default_value}|`}
                  >
                    |diff| {formatNumber(absDiff, 4)}
                  </span>
                ) : null}
                <ScoreChip score={hit.deviation_score} />
              </div>
              {Object.keys(hit.indices ?? {}).length > 0 ? (
                <small style={{ opacity: 0.8, fontSize: 11 }}>{renderIndices(hit.indices)}</small>
              ) : null}
              <small style={{ opacity: 0.85, fontSize: 11, fontVariantNumeric: "tabular-nums" }}>
                actual={formatNumber(hit.value, 4)} · default={formatNumber(hit.default_value, 4)}
              </small>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function ConstraintRow({
  analysis,
  expanded,
  onToggle,
  anchorId,
  isGlpk,
}: {
  analysis: ConstraintAnalysis;
  expanded: boolean;
  onToggle: () => void;
  anchorId?: string;
  isGlpk?: boolean;
}) {
  const maxAbsDiff = (analysis.related_params ?? []).reduce(
    (m, p) => Math.max(m, Math.abs(p.diff_abs ?? 0)),
    0,
  );
  return (
    <>
      <tr id={anchorId} style={{ cursor: "pointer" }} onClick={onToggle}>
        <td style={TD_STYLE}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <span aria-hidden="true" style={{ opacity: 0.7, width: 10 }}>
              {expanded ? "▾" : "▸"}
            </span>
            <code style={{ fontSize: 12 }}>{analysis.name}</code>
            {analysis.in_iis && (
              <span title={isGlpk ? "Restricción violada en la solución GLPK --nopresol" : "Parte del Irreducible Inconsistent Subsystem"}>
                <Badge variant="warning">{isGlpk ? "Violada" : "IIS"}</Badge>
              </span>
            )}
            {!analysis.has_mapping && (
              <span title="No hay mapeo estático a parámetros para este tipo">
                <Badge variant="neutral">sin mapeo</Badge>
              </span>
            )}
            {isGlpk && (() => {
              const vi = glpkViolationInfo(analysis);
              if (!vi) return null;
              return (
                <>
                  <span
                    style={{
                      fontSize: 11,
                      padding: "1px 6px",
                      borderRadius: 4,
                      background: "rgba(239,68,68,0.15)",
                      border: "1px solid rgba(239,68,68,0.35)",
                      color: "#fca5a5",
                      whiteSpace: "nowrap",
                    }}
                    title={vi.description}
                  >
                    {vi.label}
                  </span>
                  <span
                    style={{ fontSize: 11, opacity: 0.85, fontVariantNumeric: "tabular-nums", color: "#fca5a5" }}
                  >
                    {vi.detail}
                  </span>
                </>
              );
            })()}
          </div>
        </td>
        <td style={TD_STYLE}>
          <code style={{ fontSize: 12 }}>{analysis.constraint_type}</code>
        </td>
        <td style={TD_STYLE}>{renderIndices(analysis.indices)}</td>
        <td
          style={{
            ...TD_STYLE,
            fontVariantNumeric: "tabular-nums",
            fontWeight: 600,
          }}
          title="Mayor |diff| entre los parámetros relacionados de esta restricción"
        >
          {maxAbsDiff > 0
            ? formatNumber(maxAbsDiff, 4)
            : isGlpk && analysis.violation > 0
              ? formatNumber(analysis.violation, 4)
              : "—"}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={4} style={{ ...TD_STYLE, background: "rgba(255,255,255,0.03)" }}>
            {analysis.description && (
              <p style={{ margin: "0 0 8px 0", opacity: 0.85 }}>{analysis.description}</p>
            )}
            {isGlpk && (() => {
              const vi = glpkViolationInfo(analysis);
              if (!vi) return null;
              const sideLabel = analysis.side
                ? (BOUND_TYPE_LABEL[analysis.side] ?? analysis.side)
                : vi.label;
              return (
                <div style={{ marginBottom: 10, padding: "10px 12px", background: "rgba(220,38,38,0.08)", borderRadius: 6, border: "1px solid rgba(220,38,38,0.25)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span style={{ fontSize: 12, fontWeight: 700 }}>Violación — {sideLabel}</span>
                  </div>
                  <p style={{ margin: "0 0 8px", fontSize: 13, color: "#fca5a5" }}>
                    {vi.description}
                  </p>
                  <table style={{ ...TABLE_STYLE, fontSize: 12 }}>
                    <thead>
                      <tr>
                        <th style={TH_STYLE}>Valor actual (act)</th>
                        <th style={TH_STYLE}>
                          {analysis.lower != null && analysis.body != null && analysis.body < analysis.lower
                            ? "Límite inferior (lb)"
                            : "Límite superior (ub)"}
                        </th>
                        <th style={TH_STYLE}>Diferencia (Δ)</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td style={{ ...TD_STYLE, fontVariantNumeric: "tabular-nums" }}>{formatNumber(analysis.body, 6)}</td>
                        <td style={{ ...TD_STYLE, fontVariantNumeric: "tabular-nums" }}>
                          {formatNumber(analysis.lower ?? analysis.upper, 6)}
                        </td>
                        <td style={{ ...TD_STYLE, fontVariantNumeric: "tabular-nums", fontWeight: 700, color: "#fca5a5" }}>
                          {formatNumber(analysis.violation, 6)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              );
            })()}
            {analysis.related_params && analysis.related_params.length > 0 ? (
              <>
                <strong style={{ fontSize: 12, opacity: 0.85 }}>
                  Parámetros OSeMOSYS relacionados ({analysis.related_params.length})
                </strong>
                <table style={{ ...TABLE_STYLE, marginTop: 6 }}>
                  <thead>
                    <tr>
                      <th style={TH_STYLE}>Parámetro</th>
                      <th style={TH_STYLE}>Índices</th>
                      <th style={TH_STYLE}>Actual</th>
                      <th style={TH_STYLE}>Default</th>
                      <th style={TH_STYLE}>|Diff|</th>
                      <th style={TH_STYLE}>Diff</th>
                      <th style={TH_STYLE}>Score</th>
                      <th style={TH_STYLE}>Origen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...analysis.related_params]
                      .sort(
                        (a, b) =>
                          Math.abs(b.diff_abs ?? 0) - Math.abs(a.diff_abs ?? 0),
                      )
                      .map((hit, i) => (
                        <tr key={`${hit.param}-${i}`}>
                          <td style={TD_STYLE}>
                            <code style={{ fontSize: 12 }}>{hit.param}</code>
                          </td>
                          <td style={TD_STYLE}>{renderIndices(hit.indices)}</td>
                          <td style={{ ...TD_STYLE, fontVariantNumeric: "tabular-nums" }}>
                            {formatNumber(hit.value, 6)}
                          </td>
                          <td style={{ ...TD_STYLE, fontVariantNumeric: "tabular-nums", opacity: 0.85 }}>
                            {formatNumber(hit.default_value, 6)}
                          </td>
                          <td
                            style={{
                              ...TD_STYLE,
                              fontVariantNumeric: "tabular-nums",
                              fontWeight: 600,
                            }}
                          >
                            {hit.diff_abs != null
                              ? formatNumber(Math.abs(hit.diff_abs), 6)
                              : "—"}
                          </td>
                          <td style={{ ...TD_STYLE, fontVariantNumeric: "tabular-nums" }}>
                            {formatNumber(hit.diff_abs, 6)}
                          </td>
                          <td style={TD_STYLE}><ScoreChip score={hit.deviation_score} /></td>
                          <td style={TD_STYLE}>
                            {hit.is_default ? (
                              <span style={{ opacity: 0.7, fontSize: 12 }}>
                                sin CSV / usa default
                              </span>
                            ) : (
                              <span style={{ fontSize: 12 }}>CSV</span>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </>
            ) : (
              <em style={{ opacity: 0.7 }}>
                No hay mapeo a parámetros para este tipo de restricción.
              </em>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function OverviewChips({
  items,
  max = 12,
  emptyLabel = "(ninguno)",
}: {
  items: Record<string, number>;
  max?: number;
  emptyLabel?: string;
}) {
  const entries = Object.entries(items ?? {}).sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );
  if (entries.length === 0) {
    return <span style={{ opacity: 0.7, fontSize: 13 }}>{emptyLabel}</span>;
  }
  const visible = entries.slice(0, max);
  const overflow = entries.length - visible.length;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {visible.map(([name, count]) => (
        <span
          key={name}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "3px 8px",
            borderRadius: 999,
            background: "rgba(148,163,184,0.14)",
            border: "1px solid rgba(148,163,184,0.3)",
            fontSize: 12,
          }}
        >
          <code style={{ fontSize: 12 }}>{name}</code>
          <span style={{ opacity: 0.75 }}>×{count}</span>
        </span>
      ))}
      {overflow > 0 ? (
        <span style={{ fontSize: 12, opacity: 0.7, alignSelf: "center" }}>
          (+{overflow} más)
        </span>
      ) : null}
    </div>
  );
}

function OverviewSection({ overview }: { overview: InfeasibilityOverview }) {
  return (
    <section style={CARD_STYLE}>
      <h2 style={{ margin: "0 0 4px 0", fontSize: 16 }}>Resumen</h2>
      <p style={{ margin: "0 0 12px 0", fontSize: 12, opacity: 0.8 }}>
        Años, tipos y códigos únicos involucrados en la infactibilidad. El detalle por
        restricción está en la pestaña de abajo.
      </p>
      <div style={{ display: "grid", gap: 12 }}>
        <div>
          <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 4 }}>
            Años infactibles ({overview.years.length})
          </div>
          {overview.years.length === 0 ? (
            <span style={{ opacity: 0.7, fontSize: 13 }}>(ninguno detectado)</span>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {overview.years.map((y) => (
                <span
                  key={y}
                  style={{
                    padding: "3px 10px",
                    borderRadius: 999,
                    background: "rgba(239,68,68,0.15)",
                    border: "1px solid rgba(239,68,68,0.35)",
                    fontSize: 12,
                    fontWeight: 600,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {y}
                </span>
              ))}
            </div>
          )}
        </div>
        <div>
          <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 4 }}>
            Tipos de restricción ({Object.keys(overview.constraint_types ?? {}).length})
          </div>
          <OverviewChips items={overview.constraint_types ?? {}} />
        </div>
        <div>
          <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 4 }}>
            Tipos de variable ({Object.keys(overview.variable_types ?? {}).length})
          </div>
          <OverviewChips items={overview.variable_types ?? {}} />
        </div>
        <div>
          <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 4 }}>
            Tecnologías / Combustibles únicos (
            {Object.keys(overview.techs_or_fuels ?? {}).length})
          </div>
          <OverviewChips items={overview.techs_or_fuels ?? {}} max={18} />
        </div>
      </div>
    </section>
  );
}

export function InfeasibilityReportPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const jobId = runId ? Number(runId) : NaN;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [activeTab, setActiveTab] = useState<TabId>("iis");
  const [scenarioParams, setScenarioParams] = useState<ScenarioParamsForDiagnostics>({
    state: "none",
  });
  const [triggering, setTriggering] = useState(false);

  const refreshResult = useCallback(async () => {
    if (!Number.isFinite(jobId)) return;
    try {
      const data = await simulationApi.getResult(jobId);
      setResult(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el resultado.");
    }
  }, [jobId]);

  useEffect(() => {
    if (!Number.isFinite(jobId)) {
      setError("ID de job inválido.");
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    refreshResult().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [jobId, refreshResult]);

  // Retrocompat: si el backend no trae `diagnostic_status` pero ya hay datos
  // enriquecidos (iis/overview/top_suspects/constraint_analyses), tratarlo como
  // SUCCEEDED. Esto cubre jobs antiguos y evita el mensaje "Diagnóstico aún no
  // ejecutado" sobre un reporte ya completo.
  const rawDiagStatus = result?.infeasibility_diagnostics?.diagnostic_status;
  const hasEnrichedDiagnostic = Boolean(
    result?.infeasibility_diagnostics?.iis ||
      result?.infeasibility_diagnostics?.overview ||
      (result?.infeasibility_diagnostics?.top_suspects?.length ?? 0) > 0 ||
      (result?.infeasibility_diagnostics?.constraint_analyses?.length ?? 0) > 0,
  );
  const diagStatus = rawDiagStatus ?? (hasEnrichedDiagnostic ? "SUCCEEDED" : "NONE");
  const diagError = result?.infeasibility_diagnostics?.diagnostic_error ?? null;

  // Polling mientras el diagnóstico esté en QUEUED/RUNNING: cada 3 s consulta
  // el resultado hasta que transicione a SUCCEEDED/FAILED.
  useEffect(() => {
    if (diagStatus !== "QUEUED" && diagStatus !== "RUNNING") return;
    const id = window.setInterval(() => {
      void refreshResult();
    }, 3000);
    return () => window.clearInterval(id);
  }, [diagStatus, refreshResult]);

  const triggerDiagnostic = useCallback(async () => {
    if (!Number.isFinite(jobId)) return;
    setTriggering(true);
    try {
      await simulationApi.runInfeasibilityDiagnostic(jobId);
      await refreshResult();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo encolar el diagnóstico.");
    } finally {
      setTriggering(false);
    }
  }, [jobId, refreshResult]);

  const [cancelling, setCancelling] = useState(false);
  const cancelDiagnostic = useCallback(async () => {
    if (!Number.isFinite(jobId)) return;
    setCancelling(true);
    try {
      await simulationApi.cancelInfeasibilityDiagnostic(jobId);
      await refreshResult();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "No se pudo cancelar el diagnóstico.",
      );
    } finally {
      setCancelling(false);
    }
  }, [jobId, refreshResult]);

  // Tick de 1 s en vivo para actualizar el contador de segundos mientras el
  // diagnóstico está RUNNING.
  const [liveTickMs, setLiveTickMs] = useState<number>(() => Date.now());
  useEffect(() => {
    if (diagStatus !== "RUNNING") return;
    setLiveTickMs(Date.now());
    const id = window.setInterval(() => setLiveTickMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [diagStatus]);

  // Elapsed seconds derivados del started_at y el tick (para RUNNING) o del
  // diagnostic_seconds persistido (para SUCCEEDED/FAILED).
  const diagElapsedSeconds = useMemo<number | null>(() => {
    const d = result?.infeasibility_diagnostics ?? null;
    if (!d) return null;
    if (diagStatus === "RUNNING" && d.diagnostic_started_at) {
      const startedMs = new Date(d.diagnostic_started_at).getTime();
      if (Number.isFinite(startedMs)) {
        return Math.max(0, (liveTickMs - startedMs) / 1000);
      }
    }
    if (typeof d.diagnostic_seconds === "number") return d.diagnostic_seconds;
    return null;
  }, [result, diagStatus, liveTickMs]);

  // Cargar nombres de parámetros modificados del escenario (para la pestaña
  // "Parámetros del escenario" y para los badges cruzados).
  useEffect(() => {
    const sid = result?.scenario_id ?? null;
    if (!sid) {
      setScenarioParams({ state: "none" });
      return;
    }
    let cancelled = false;
    setScenarioParams({ state: "loading" });
    scenariosApi
      .getScenarioById(sid)
      .then((s) => {
        if (cancelled) return;
        const names = s.changed_param_names ?? [];
        setScenarioParams({ state: "loaded", names });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : "Error al cargar el escenario";
        setScenarioParams({ state: "error", message: msg });
      });
    return () => {
      cancelled = true;
    };
  }, [result?.scenario_id]);

  const diagnostics: InfeasibilityDiagnostics | null = result?.infeasibility_diagnostics ?? null;
  const solverName = (result?.solver_name ?? "").toString().toLowerCase();
  const isHighs = solverName === "highs";
  const isGurobi = solverName === "gurobi";
  const supportsIIS = isHighs || isGurobi;
  const isGlpk = !isHighs && !isGurobi && solverName === "glpk";
  const isGlpkEnriched =
    isGlpk &&
    diagnostics?.iis?.method === "glpk_nopresol" &&
    diagnostics?.iis?.available;
  const isGlpkTimeout =
    isGlpk &&
    !diagnostics?.iis?.available &&
    (diagnostics?.iis?.unavailable_reason ?? "").includes("timeout");
  const iisAvailable = Boolean(diagnostics?.iis?.available);

  // Para los solvers que soportan IIS (HiGHS / Gurobi) sólo mostramos las
  // restricciones cuando el IIS está disponible. En otros solvers se muestran
  // las violaciones heurísticas post-solve.
  const analyses = useMemo<ConstraintAnalysis[]>(() => {
    const all = diagnostics?.constraint_analyses ?? [];
    if (supportsIIS) return iisAvailable ? all : [];
    return all;
  }, [diagnostics, supportsIIS, iisAvailable]);

  const topSuspects = useMemo<ParamHit[]>(() => {
    return diagnostics?.top_suspects ?? [];
  }, [diagnostics]);

  // Nombres de parámetros presentes en el IIS (via related_params) — para
  // badges cruzados en la pestaña de parámetros del escenario.
  const iisParamNames = useMemo<Set<string>>(() => {
    const s = new Set<string>();
    for (const a of analyses) {
      for (const p of a.related_params ?? []) {
        if (p.param) s.add(p.param);
      }
    }
    return s;
  }, [analyses]);

  // Claves "param|REGION=…|TECHNOLOGY=…|…" que aparecen en el IIS. Sirven para
  // hacer match exacto contra las entries del audit del escenario.
  const iisParamIndexKeys = useMemo<Set<string>>(() => {
    const keys = new Set<string>();
    for (const a of analyses) {
      for (const p of a.related_params ?? []) {
        if (!p.param) continue;
        const norm = normalizeIndices(p.indices as Record<string, unknown>);
        keys.add(paramIndicesKey(p.param, norm));
      }
    }
    return keys;
  }, [analyses]);

  // Fetch del audit de los parámetros modificados del escenario que ALSO
  // aparecen en el IIS, y filtro por match exacto de (param, índices).
  const [iisChangesLoading, setIisChangesLoading] = useState(false);
  const [iisChanges, setIisChanges] = useState<IISScenarioChange[]>([]);
  useEffect(() => {
    const sid = result?.scenario_id ?? null;
    if (
      !sid ||
      scenarioParams.state !== "loaded" ||
      scenarioParams.names.length === 0 ||
      iisParamNames.size === 0
    ) {
      setIisChanges([]);
      return;
    }
    const candidateParamNames = scenarioParams.names.filter((n) =>
      iisParamNames.has(n),
    );
    if (candidateParamNames.length === 0) {
      setIisChanges([]);
      return;
    }

    let cancelled = false;
    setIisChangesLoading(true);
    (async () => {
      const rows: IISScenarioChange[] = [];
      // Fetch secuencial para no golpear el backend; son pocos params (cap al
      // intersección entre IIS y modificados). Limit alto para traer todo el
      // historial del param en una sola request.
      for (const paramName of candidateParamNames) {
        try {
          const page = await scenariosApi.listOsemosysParamAudit(sid, paramName, {
            offset: 0,
            limit: 500,
          });
          for (const item of page.items) {
            const indices = normalizeIndices(
              (item.dimensions_json as Record<string, unknown>) ?? null,
            );
            const key = paramIndicesKey(paramName, indices);
            if (iisParamIndexKeys.has(key)) {
              rows.push({
                id: item.id,
                paramName,
                indices,
                oldValue: item.old_value,
                newValue: item.new_value,
                changedBy: item.changed_by,
                createdAt: item.created_at,
                matchMode: "indices",
              });
            }
          }
        } catch {
          // Per-param failures son silenciosos: no rompen el render global.
        }
      }
      if (cancelled) return;
      setIisChanges(rows);
      setIisChangesLoading(false);
    })();
    return () => {
      cancelled = true;
      setIisChangesLoading(false);
    };
  }, [result?.scenario_id, scenarioParams, iisParamNames, iisParamIndexKeys]);

  const downloadJson = useCallback(async () => {
    if (!Number.isFinite(jobId)) return;
    setDownloading(true);
    try {
      const { blob, filename } = await simulationApi.downloadInfeasibilityReport(jobId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "No se pudo descargar el reporte.";
      setError(msg);
    } finally {
      setDownloading(false);
    }
  }, [jobId]);

  const downloadIlp = useCallback(async () => {
    if (!Number.isFinite(jobId)) return;
    try {
      const { blob, filename } = await simulationApi.downloadIisIlp(jobId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "No se pudo descargar el .ilp.";
      setError(msg);
    }
  }, [jobId]);

  const toggleRow = useCallback((idx: number) => {
    setExpanded((prev) => ({ ...prev, [idx]: !prev[idx] }));
  }, []);

  const expandAll = useCallback(() => {
    const all: Record<number, boolean> = {};
    for (let i = 0; i < analyses.length; i++) all[i] = true;
    setExpanded(all);
  }, [analyses.length]);

  const collapseAll = useCallback(() => setExpanded({}), []);

  const allExpanded = useMemo(
    () => analyses.length > 0 && analyses.every((_, i) => expanded[i]),
    [analyses, expanded],
  );

  // Al clickear un "top sospechoso", expande la primera restricción que lo
  // contiene entre sus related_params y scrollea hasta ella.
  const tableRef = useRef<HTMLTableSectionElement>(null);
  const pickConstraintByParam = useCallback(
    (paramName: string) => {
      const idx = analyses.findIndex((a) =>
        (a.related_params ?? []).some((p) => p.param === paramName),
      );
      if (idx < 0) return;
      setExpanded((prev) => ({ ...prev, [idx]: true }));
      setActiveTab("iis");
      setTimeout(() => {
        const el = document.getElementById(`constraint-row-${idx}`);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 50);
    },
    [analyses],
  );

  if (loading) {
    return <p style={{ padding: 20 }}>Cargando reporte de infactibilidad…</p>;
  }
  if (error) {
    return (
      <div style={{ padding: 20, display: "grid", gap: 10 }}>
        <p style={{ color: "#fca5a5" }}>⚠ {error}</p>
        <Button onClick={() => navigate(paths.simulation)}>Volver a Simulación</Button>
      </div>
    );
  }
  if (!diagnostics) {
    return (
      <div style={{ padding: 20, display: "grid", gap: 10 }}>
        <p>Este job no tiene diagnóstico de infactibilidad registrado.</p>
        <Link to={paths.simulation}>← Volver a Simulación</Link>
      </div>
    );
  }

  const iis = diagnostics.iis;
  const varConflicts = diagnostics.var_bound_conflicts ?? [];
  const unmapped = diagnostics.unmapped_constraint_prefixes ?? [];

  const tabBtnStyle = (active: boolean): React.CSSProperties => ({
    padding: "8px 14px",
    borderRadius: 8,
    border: "1px solid rgba(255,255,255,0.15)",
    background: active ? "rgba(239,68,68,0.25)" : "rgba(255,255,255,0.04)",
    color: "inherit",
    cursor: "pointer",
    fontWeight: active ? 600 : 500,
    fontSize: 13,
  });

  return (
    <div style={{ padding: 20, display: "grid", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>
          Reporte de infactibilidad · Job #{result?.job_id}
        </h1>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <Button onClick={downloadJson} disabled={downloading}>
            {downloading ? "Descargando…" : "Descargar JSON"}
          </Button>
          {result?.job_id ? (
            <Link to={paths.resultsDetail(result.job_id)}>
              <Button variant="ghost">Ver resultados</Button>
            </Link>
          ) : null}
          <Link to={paths.simulation}>
            <Button variant="ghost">Volver</Button>
          </Link>
        </div>
      </div>

      <section style={DANGER_CARD_STYLE}>
        <h2 style={{ margin: "0 0 8px 0", fontSize: 16 }}>Estado general</h2>
        <div
          style={{
            display: "grid",
            gap: 6,
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
            marginBottom: 8,
          }}
        >
          <div>
            <div style={{ opacity: 0.7, fontSize: 12 }}>Solver</div>
            <div style={{ fontWeight: 600 }}>{result?.solver_name}</div>
          </div>
          <div>
            <div style={{ opacity: 0.7, fontSize: 12 }}>Estado</div>
            <Badge variant="danger">{result?.solver_status}</Badge>
          </div>
          <div>
            <div style={{ opacity: 0.7, fontSize: 12 }}>Restricciones</div>
            <div style={{ fontWeight: 600 }}>{analyses.length}</div>
          </div>
          <div>
            <div style={{ opacity: 0.7, fontSize: 12 }}>Conflictos de bounds</div>
            <div style={{ fontWeight: 600 }}>{varConflicts.length}</div>
          </div>
          <div>
            <div style={{ opacity: 0.7, fontSize: 12 }}>
              {isGlpk
                ? "Análisis GLPK"
                : `IIS (${solverName === "gurobi" ? "Gurobi" : "HiGHS"})`}
            </div>
            {iis?.available ? (
              <Badge variant="warning">
                {iis.constraint_names.length} restr
                {!isGlpk ? ` · ${iis.variable_names.length} vars` : ""}
                {" · "}{iis.method}
              </Badge>
            ) : isGlpkTimeout ? (
              <span style={{ opacity: 0.85, fontSize: 12, color: "#fbbf24" }}>
                ⏱ Timeout — se usa diagnóstico básico
              </span>
            ) : isGlpk && iis?.unavailable_reason ? (
              <span style={{ opacity: 0.75, fontSize: 12 }}>
                No disponible
              </span>
            ) : (
              <span style={{ opacity: 0.75, fontSize: 12 }}>
                No disponible — {iis?.unavailable_reason ?? "sin información"}
              </span>
            )}
          </div>
          <div>
            <div style={{ opacity: 0.7, fontSize: 12 }}>Tiempo del diagnóstico</div>
            {diagStatus === "SUCCEEDED" &&
            typeof result?.infeasibility_diagnostics?.diagnostic_seconds === "number" ? (
              <div
                style={{
                  fontWeight: 700,
                  fontVariantNumeric: "tabular-nums",
                }}
                title={
                  result.infeasibility_diagnostics.diagnostic_started_at
                    ? `Inició: ${new Date(
                        result.infeasibility_diagnostics.diagnostic_started_at,
                      ).toLocaleString()}  —  Fin: ${
                        result.infeasibility_diagnostics.diagnostic_finished_at
                          ? new Date(
                              result.infeasibility_diagnostics
                                .diagnostic_finished_at,
                            ).toLocaleString()
                          : "?"
                      }`
                    : undefined
                }
              >
                {result.infeasibility_diagnostics.diagnostic_seconds.toFixed(2)} s
              </div>
            ) : diagStatus === "RUNNING" && diagElapsedSeconds !== null ? (
              <div
                style={{
                  fontWeight: 700,
                  fontVariantNumeric: "tabular-nums",
                  color: "#fbbf24",
                }}
              >
                {diagElapsedSeconds.toFixed(1)} s (en curso)
              </div>
            ) : (
              <span style={{ opacity: 0.65, fontSize: 12 }}>—</span>
            )}
          </div>
        </div>
        {isGlpkTimeout ? (
          <p style={{ margin: 0, fontSize: 12, color: "#fbbf24" }}>
            <strong>⚠ Fuente:</strong> diagnóstico básico (Level 1) — GLPK --nopresol excedió
            el tiempo límite. Las restricciones mostradas son evaluaciones de Pyomo en el punto
            inicial y pueden contener falsos positivos. Para un análisis más preciso usa HiGHS.
          </p>
        ) : iis?.available && isGlpk ? (
          <p style={{ margin: 0, fontSize: 12, opacity: 0.8, color: "#fbbf24" }}>
            <strong>Fuente:</strong> GLPK --nopresol (heurístico, no es un IIS mínimo).
            Lista las restricciones que el modelo no satisface en la solución forzada.
            Pueden existir falsos positivos secundarios; prioriza los "top sospechosos".
          </p>
        ) : iis?.available ? (
          <p style={{ margin: 0, fontSize: 12, opacity: 0.8 }}>
            <strong>Fuente:</strong> IIS de{" "}
            {solverName === "gurobi" ? "Gurobi" : "HiGHS"} (subsistema
            irreducible). Remover cualquiera de estas restricciones vuelve el
            modelo factible.
          </p>
        ) : supportsIIS ? (
          <p style={{ margin: 0, fontSize: 12, color: "#fbbf24" }}>
            <strong>Fuente:</strong> ninguna. El IIS no se pudo computar para
            este modelo.
          </p>
        ) : (
          <p style={{ margin: 0, fontSize: 12, opacity: 0.8, color: "#fbbf24" }}>
            <strong>Fuente:</strong> violaciones post-solve (heurística, posibles falsos positivos).
          </p>
        )}

        {/* Conflictos por cota (Gurobi-only) */}
        {iis?.available && (iis.bound_conflicts ?? []).length > 0 ? (
          <details style={{ marginTop: 8 }}>
            <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
              Conflictos por cota ({(iis.bound_conflicts ?? []).length})
            </summary>
            <div
              style={{
                marginTop: 6,
                fontSize: 12,
                opacity: 0.85,
                maxHeight: 180,
                overflowY: "auto",
                fontFamily: "monospace",
              }}
            >
              {(iis.bound_conflicts ?? []).map((bc, i) => (
                <div key={`${bc.name}-${bc.side}-${i}`}>
                  <Badge variant={bc.side === "LB" ? "warning" : "info"}>
                    {bc.side}
                  </Badge>{" "}
                  {bc.name}
                </div>
              ))}
            </div>
          </details>
        ) : null}

        {/* Descarga del .ilp (solo Gurobi) */}
        {iis?.available && iis.ilp_path ? (
          <div style={{ marginTop: 8 }}>
            <Button
              className="btn btn--ghost"
              onClick={() => void downloadIlp()}
              title="Descarga el subsistema irreducible como archivo .ilp (formato LP) reproducible en Gurobi standalone u otra herramienta."
            >
              Descargar IIS (.ilp)
            </Button>
          </div>
        ) : null}
      </section>

      {/* Banner de estado del diagnóstico on-demand */}
      {!supportsIIS && !isGlpk && diagStatus === "NONE" ? (
        <section style={WARN_CARD_STYLE}>
          <strong style={{ fontSize: 14 }}>
            El diagnóstico detallado solo está disponible con HiGHS, Gurobi o GLPK.
          </strong>
          <p style={{ margin: "6px 0 0", fontSize: 13, opacity: 0.9 }}>
            Esta simulación corrió con {result?.solver_name?.toUpperCase() ?? "otro solver"}.
            Vuelve a lanzarla con HiGHS o Gurobi (IIS preciso) o con GLPK (análisis
            heurístico --nopresol) para habilitar el diagnóstico.
          </p>
          <p style={{ margin: "6px 0 0" }}>
            <Link to={paths.simulation}>Ir a Simulación</Link>
          </p>
        </section>
      ) : diagStatus === "NONE" ? (
        <section style={WARN_CARD_STYLE}>
          <strong style={{ fontSize: 14 }}>Diagnóstico aún no ejecutado.</strong>
          <p style={{ margin: "6px 0 10px", fontSize: 13, opacity: 0.9 }}>
            {isGlpk
              ? "El diagnóstico ejecuta GLPK nuevamente sin preprocesamiento (--nopresol) para detectar qué restricciones no se pueden satisfacer. Puede tardar hasta 25 minutos en modelos grandes."
              : "El análisis enriquecido (IIS + mapeo a parámetros OSeMOSYS + ranking de sospechosos) se ejecuta como una tarea aparte porque puede tardar varios segundos sobre modelos grandes."}
          </p>
          <Button onClick={() => void triggerDiagnostic()} disabled={triggering}>
            {triggering ? "Encolando…" : "Correr diagnóstico de infactibilidad"}
          </Button>
        </section>
      ) : diagStatus === "QUEUED" ? (
        <section style={WARN_CARD_STYLE}>
          <strong style={{ fontSize: 14 }}>
            ⏳ Diagnóstico en cola (aún no iniciado)
          </strong>
          <p style={{ margin: "6px 0 0", fontSize: 13, opacity: 0.9 }}>
            La tarea está encolada en Celery pero todavía no empezó a ejecutarse.
            Esto pasa cuando otra simulación está ocupando el worker o cuando el
            worker aún no recoge la tarea. Esta página se actualizará
            automáticamente cuando arranque la ejecución (poll cada 3 s).
          </p>
          <p style={{ margin: "10px 0 0" }}>
            <Button onClick={() => void cancelDiagnostic()} disabled={cancelling}>
              {cancelling ? "Cancelando…" : "Cancelar diagnóstico"}
            </Button>
          </p>
        </section>
      ) : diagStatus === "RUNNING" ? (
        <section style={WARN_CARD_STYLE}>
          <strong style={{ fontSize: 14 }}>
            ⚙️ Ejecutando diagnóstico de infactibilidad
            {diagElapsedSeconds !== null ? (
              <span
                style={{
                  marginLeft: 8,
                  padding: "2px 10px",
                  borderRadius: 999,
                  background: "rgba(245,158,11,0.2)",
                  border: "1px solid rgba(245,158,11,0.5)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {diagElapsedSeconds.toFixed(1)} s
              </span>
            ) : null}
          </strong>
          <p style={{ margin: "6px 0 0", fontSize: 13, opacity: 0.9 }}>
            {isGlpk
              ? "Se está ejecutando glpsol --nopresol sobre el LP del modelo. Puede tardar hasta 25 minutos en escenarios grandes. Esta página se actualizará automáticamente cuando termine."
              : "Se está corriendo el IIS sobre el modelo y mapeando las restricciones a los parámetros OSeMOSYS de entrada. Esta página se actualizará automáticamente cuando termine."}
            {result?.infeasibility_diagnostics?.diagnostic_started_at ? (
              <>
                {" "}Inició a las{" "}
                {new Date(
                  result.infeasibility_diagnostics.diagnostic_started_at,
                ).toLocaleTimeString()}
                .
              </>
            ) : null}
          </p>
          <p style={{ margin: "10px 0 0" }}>
            <Button onClick={() => void cancelDiagnostic()} disabled={cancelling}>
              {cancelling ? "Cancelando…" : "Cancelar diagnóstico"}
            </Button>
          </p>
        </section>
      ) : diagStatus === "FAILED" ? (
        <section style={DANGER_CARD_STYLE}>
          <strong style={{ fontSize: 14 }}>El diagnóstico falló.</strong>
          {diagError ? (
            <p style={{ margin: "6px 0 0", fontSize: 13 }}>
              <em>{diagError}</em>
            </p>
          ) : null}
          <p style={{ margin: "10px 0 0" }}>
            <Button onClick={() => void triggerDiagnostic()} disabled={triggering}>
              {triggering ? "Encolando…" : "Reintentar diagnóstico"}
            </Button>
          </p>
        </section>
      ) : null}

      {/* Bloques principales del reporte: solo se muestran cuando el diagnóstico
          ya corrió (SUCCEEDED) o el análisis heurístico previo dejó datos útiles. */}
      {diagStatus === "SUCCEEDED" || diagnostics.overview ? (
        <>
          {diagnostics.overview ? <OverviewSection overview={diagnostics.overview} /> : null}

          <TopSuspectsSection suspects={topSuspects} onPickConstraint={pickConstraintByParam} />

          {!isGlpk && (
            <IISScenarioChangesSection
              changes={iisChanges}
              loading={iisChangesLoading}
              hasIISParams={iisParamNames.size > 0}
              hasScenarioModifications={
                scenarioParams.state === "loaded" &&
                scenarioParams.names.length > 0
              }
              onOpenAuditTab={() => setActiveTab("scenarioParams")}
            />
          )}
        </>
      ) : null}

      {/* Pestañas + detalle: solo cuando hay diagnóstico disponible */}
      {diagStatus === "SUCCEEDED" || (!supportsIIS && analyses.length > 0) ? (
      <>
      <div role="tablist" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "iis"}
          style={tabBtnStyle(activeTab === "iis")}
          onClick={() => setActiveTab("iis")}
        >
          {isGlpk || !iis?.available ? "Restricciones violadas" : "Restricciones del IIS"} ({analyses.length})
        </button>
        {!isGlpk && (
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "scenarioParams"}
            style={tabBtnStyle(activeTab === "scenarioParams")}
            onClick={() => setActiveTab("scenarioParams")}
          >
            Parámetros del escenario
            {scenarioParams.state === "loaded"
              ? ` (${scenarioParams.names.length})`
              : ""}
          </button>
        )}
      </div>

      {activeTab === "iis" || isGlpk ? (
        <section style={CARD_STYLE}>
          {supportsIIS && !iisAvailable ? (
            <div style={WARN_CARD_STYLE}>
              <strong>
                {solverName === "gurobi" ? "Gurobi" : "HiGHS"} no produjo un
                IIS.
              </strong>{" "}
              No se muestran restricciones porque con este solver la única
              fuente confiable es el Irreducible Inconsistent Subsystem; las
              violaciones post-solve del diagnóstico heurístico no son
              aplicables.
              {iis?.unavailable_reason ? (
                <>
                  <br />
                  <em style={{ opacity: 0.85 }}>Motivo reportado: {iis.unavailable_reason}</em>
                </>
              ) : null}
              <br />
              Revisa los logs del solver o descarga el JSON para más contexto.
            </div>
          ) : analyses.length === 0 ? (
            <p style={{ opacity: 0.8 }}>
              No se detectaron violaciones explícitas de restricciones. Revisa los conflictos de
              bounds y los logs del solver.
            </p>
          ) : (
            <>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 8,
                  marginBottom: 8,
                  flexWrap: "wrap",
                }}
              >
                <small style={{ opacity: 0.78 }}>
                  Ordenadas de mayor a menor <strong>|diff|</strong> (diferencia
                  absoluta entre valor actual y default OSeMOSYS). Click en una fila
                  para ver sus parámetros relacionados.
                </small>
                <div style={{ display: "flex", gap: 8 }}>
                  <Button
                    variant="ghost"
                    onClick={allExpanded ? collapseAll : expandAll}
                    type="button"
                  >
                    {allExpanded ? "Colapsar todas" : "Expandir todas"}
                  </Button>
                </div>
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={TABLE_STYLE}>
                  <thead>
                    <tr>
                      <th style={TH_STYLE}>Restricción</th>
                      <th style={TH_STYLE}>Tipo</th>
                      <th style={TH_STYLE}>Índices</th>
                      <th style={TH_STYLE} title="Mayor |diff| (valor - default) entre sus parámetros relacionados. Las restricciones están ordenadas por este criterio.">
                        Máx |diff|
                      </th>
                    </tr>
                  </thead>
                  <tbody ref={tableRef}>
                    {analyses.map((a, i) => (
                      <ConstraintRow
                        key={`${a.name}-${i}`}
                        analysis={a}
                        expanded={!!expanded[i]}
                        onToggle={() => toggleRow(i)}
                        anchorId={`constraint-row-${i}`}
                        isGlpk={isGlpk}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      ) : (
        <section style={CARD_STYLE}>
          <ScenarioParamsTab
            scenarioParams={scenarioParams}
            scenarioId={result?.scenario_id ?? null}
            iisParamNames={iisParamNames}
          />
        </section>
      )}
      </>
      ) : null}

      {varConflicts.length > 0 && (
        <section style={CARD_STYLE}>
          <h2 style={{ margin: "0 0 12px 0", fontSize: 16 }}>
            Conflictos de bounds de variables ({varConflicts.length})
          </h2>
          <table style={TABLE_STYLE}>
            <thead>
              <tr>
                <th style={TH_STYLE}>Variable</th>
                <th style={TH_STYLE}>LB</th>
                <th style={TH_STYLE}>UB</th>
                <th style={TH_STYLE}>Gap</th>
              </tr>
            </thead>
            <tbody>
              {varConflicts.map((v, i) => (
                <tr key={`${v.name}-${i}`}>
                  <td style={TD_STYLE}>
                    <code style={{ fontSize: 12 }}>{v.name}</code>
                  </td>
                  <td style={TD_STYLE}>{formatNumber(v.lb)}</td>
                  <td style={TD_STYLE}>{formatNumber(v.ub)}</td>
                  <td style={{ ...TD_STYLE, color: "#fca5a5", fontWeight: 600 }}>
                    {formatNumber(v.gap)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {!isGlpk && unmapped.length > 0 && (
        <section style={CARD_STYLE}>
          <h2 style={{ margin: "0 0 8px 0", fontSize: 16 }}>Prefijos sin mapeo estático</h2>
          <p style={{ margin: "0 0 8px 0", fontSize: 13, opacity: 0.85 }}>
            Estos tipos de restricción se reportan sin traceo a parámetros. Agrégalos a{" "}
            <code>CONSTRAINT_PARAM_MAP</code> en{" "}
            <code>backend/app/simulation/core/infeasibility_analysis.py</code> si son recurrentes.
          </p>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {unmapped.map((p) => (
              <li key={p}>
                <code>{p}</code>
              </li>
            ))}
          </ul>
        </section>
      )}

    </div>
  );
}
