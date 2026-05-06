/**
 * Modal con el detalle del reporte de calidad de datos de un escenario:
 *   - bound conflicts (lower > upper) clasificados real_conflict / numeric_precision
 *   - year exclusions (años eliminados por YearSplit=0 en todos sus timeslices)
 *
 * Permite:
 *   - Refrescar el reporte (re-detectar y re-aplicar dead_year exclusion)
 *   - Aplicar auto-fix sólo a numeric_precision (lower toma valor del upper)
 *
 * Backend: GET/POST /api/v1/scenarios/{id}/data-quality* (ver scenariosApi).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Modal } from "@/shared/components/Modal";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { scenariosApi } from "@/features/scenarios/api/scenariosApi";
import { paths } from "@/routes/paths";
import type {
  BoundConflict,
  DataQualityReport,
  YearExclusion,
} from "@/types/domain";

type Props = {
  open: boolean;
  scenarioId: number;
  scenarioName: string;
  onClose: () => void;
  /** Callback opcional cuando se refresca/auto-fix; útil para que el padre
   *  recargue la lista de escenarios y actualice los badges. */
  onChanged?: () => void;
};

/**
 * Construye la URL del detalle del escenario con un query string que
 * `ScenarioDetailPage` lee al mount y aplica como filtros.
 *
 * Filtra ambos parámetros del par (lower y upper) y la tupla exacta
 * (region/technology/year) para que el usuario vea las dos filas conflictuantes
 * con las celdas resaltadas por valor.
 */
function buildConflictViewUrl(scenarioId: number, c: BoundConflict): string {
  const params = new URLSearchParams();
  params.set("dq_param_names", `${c.lower},${c.upper}`);
  if (typeof c.key.REGION === "string") {
    params.set("dq_region_names", c.key.REGION);
  }
  if (typeof c.key.TECHNOLOGY === "string") {
    params.set("dq_technology_names", c.key.TECHNOLOGY);
  }
  if (typeof c.key.YEAR === "number") {
    params.set("dq_year", String(c.key.YEAR));
  }
  return `${paths.scenarioDetail(scenarioId)}?${params.toString()}`;
}

function isReport(
  r: DataQualityReport | Record<string, never>,
): r is DataQualityReport {
  return Boolean(r && typeof r === "object" && "summary" in r);
}

function severityBadge(s: BoundConflict["severity"]) {
  return s === "real_conflict" ? (
    <Badge variant="danger">conflicto real</Badge>
  ) : (
    <Badge variant="warning">precisión decimal</Badge>
  );
}

function formatKey(key: BoundConflict["key"]): string {
  const parts: string[] = [];
  if (key.REGION) parts.push(`R=${key.REGION}`);
  if (key.TECHNOLOGY) parts.push(`T=${key.TECHNOLOGY}`);
  if (key.YEAR != null) parts.push(`Y=${key.YEAR}`);
  return parts.join(" · ");
}

export function DataQualityModal({
  open,
  scenarioId,
  scenarioName,
  onClose,
  onChanged,
}: Props) {
  const navigate = useNavigate();
  const handleNavigateToConflict = (c: BoundConflict) => {
    onClose();
    navigate(buildConflictViewUrl(scenarioId, c));
  };

  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<DataQualityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | "refresh" | "fix">(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await scenariosApi.getDataQuality(scenarioId);
      setReport(isReport(res.data_quality_warnings) ? res.data_quality_warnings : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error cargando datos");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, scenarioId]);

  const handleRefresh = async () => {
    setBusy("refresh");
    setFeedback(null);
    setError(null);
    try {
      const res = await scenariosApi.refreshDataQuality(scenarioId);
      setReport(isReport(res.data_quality_warnings) ? res.data_quality_warnings : null);
      setFeedback("Reporte actualizado.");
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al refrescar");
    } finally {
      setBusy(null);
    }
  };

  const handleAutoFix = async () => {
    if (!confirm(
      "¿Aplicar auto-fix a los conflictos por precisión decimal? " +
      "Cada `lower` tomará el valor del `upper` correspondiente. " +
      "Los conflictos reales NO se modifican."
    )) return;
    setBusy("fix");
    setFeedback(null);
    setError(null);
    try {
      const res = await scenariosApi.fixNumericPrecisionConflicts(scenarioId);
      setReport(res.data_quality_warnings);
      setFeedback(
        `Auto-fix aplicado: ${res.fixed_n_tuples} tupla(s) corregida(s). ` +
        `Antes: ${res.before.n_numeric_precision} precision · ` +
        `Después: ${res.after.n_numeric_precision} precision.`
      );
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al aplicar auto-fix");
    } finally {
      setBusy(null);
    }
  };

  const summary = report?.summary;
  const nReal = summary?.n_bound_real_conflict ?? 0;
  const nPrecision = summary?.n_bound_numeric_precision ?? 0;
  const nExclusions = summary?.n_year_exclusions ?? 0;

  return (
    <Modal
      open={open}
      title={`Calidad de datos · ${scenarioName}`}
      onClose={onClose}
      wide
      footer={
        <div style={{ display: "flex", gap: 8, justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ fontSize: 12, opacity: 0.7 }}>
            {report?.detected_at ? `Detectado: ${new Date(report.detected_at).toLocaleString()} (${report.detected_during})` : ""}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="ghost" onClick={() => void handleRefresh()} disabled={busy !== null}>
              {busy === "refresh" ? "Refrescando..." : "Refrescar"}
            </Button>
            <Button
              variant="primary"
              onClick={() => void handleAutoFix()}
              disabled={busy !== null || nPrecision === 0}
              title={nPrecision === 0 ? "No hay conflictos de precisión decimal" : "Corrige los conflictos numeric_precision"}
            >
              {busy === "fix" ? "Aplicando..." : `Auto-fix decimales (${nPrecision})`}
            </Button>
            <Button variant="ghost" onClick={onClose}>Cerrar</Button>
          </div>
        </div>
      }
    >
      {loading ? (
        <div style={{ padding: 16, opacity: 0.75 }}>Cargando reporte...</div>
      ) : error ? (
        <div style={{ padding: 16, color: "var(--danger, #ef4444)" }}>{error}</div>
      ) : !report ? (
        <div style={{ padding: 16, opacity: 0.75 }}>
          Aún no se ha ejecutado la validación para este escenario. Pulsa <strong>Refrescar</strong> para detectar conflictos
          y aplicar la exclusión automática de años con YearSplit=0.
        </div>
      ) : (
        <div style={{ display: "grid", gap: 16 }}>
          {feedback && (
            <div style={{
              padding: "8px 12px",
              borderRadius: 8,
              background: "rgba(34,197,94,0.14)",
              border: "1px solid rgba(34,197,94,0.34)",
              fontSize: 13,
            }}>{feedback}</div>
          )}

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Badge variant={nReal > 0 ? "danger" : "neutral"}>
              {nReal} conflictos reales
            </Badge>
            <Badge variant={nPrecision > 0 ? "warning" : "neutral"}>
              {nPrecision} precisión decimal
            </Badge>
            <Badge variant={nExclusions > 0 ? "info" : "neutral"}>
              {nExclusions} año(s) excluidos
            </Badge>
          </div>

          {nReal > 0 && (
            <div style={{
              padding: "10px 12px",
              borderRadius: 8,
              background: "rgba(239,68,68,0.10)",
              border: "1px solid rgba(239,68,68,0.30)",
              fontSize: 13,
              lineHeight: 1.5,
            }}>
              <strong>Atención:</strong> hay {nReal} conflicto(s) <em>real(es)</em> donde lower &gt; upper con diferencia
              significativa (gap ≥ 1e-4). El auto-fix <strong>no</strong> los toca; debes corregir los valores
              manualmente en la BD o en el escenario.
            </div>
          )}

          <BoundConflictsTable
            conflicts={report.bound_conflicts}
            onView={handleNavigateToConflict}
          />
          <YearExclusionsTable exclusions={report.year_exclusions} />
        </div>
      )}
    </Modal>
  );
}

function BoundConflictsTable({
  conflicts,
  onView,
}: {
  conflicts: BoundConflict[];
  onView: (c: BoundConflict) => void;
}) {
  if (conflicts.length === 0) {
    return (
      <section>
        <h4 style={{ margin: "0 0 8px 0", fontSize: 14 }}>Bound conflicts</h4>
        <div style={{ opacity: 0.7, fontSize: 13 }}>Sin conflictos lower &gt; upper.</div>
      </section>
    );
  }
  // Ordenar real_conflict primero, luego por |gap| descendente.
  const ordered = [...conflicts].sort((a, b) => {
    if (a.severity !== b.severity) return a.severity === "real_conflict" ? -1 : 1;
    return Math.abs(b.gap) - Math.abs(a.gap);
  });
  return (
    <section>
      <h4 style={{ margin: "0 0 8px 0", fontSize: 14 }}>Bound conflicts ({conflicts.length})</h4>
      <div style={{ overflowX: "auto", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead style={{ background: "rgba(255,255,255,0.04)" }}>
            <tr>
              <th style={th}>Severidad</th>
              <th style={th}>Lower / Upper</th>
              <th style={th}>Tupla</th>
              <th style={{ ...th, textAlign: "right" }}>value_lower</th>
              <th style={{ ...th, textAlign: "right" }}>value_upper</th>
              <th style={{ ...th, textAlign: "right" }}>gap</th>
              <th style={{ ...th, textAlign: "center" }}></th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((c, i) => (
              <tr key={i} style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                <td style={td}>{severityBadge(c.severity)}</td>
                <td style={td}>
                  <div style={{ fontWeight: 600 }}>{c.lower}</div>
                  <div style={{ opacity: 0.65, fontSize: 11 }}>vs {c.upper}</div>
                </td>
                <td style={td}>{formatKey(c.key)}</td>
                <td style={{ ...td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{c.value_lower.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                <td style={{ ...td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{c.value_upper.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                <td style={{ ...td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{c.gap.toExponential(2)}</td>
                <td style={{ ...td, textAlign: "center" }}>
                  <button
                    type="button"
                    onClick={() => onView(c)}
                    title="Abrir el visor de datos del escenario filtrado por esta tupla"
                    style={{
                      background: c.severity === "real_conflict"
                        ? "rgba(239,68,68,0.18)"
                        : "rgba(255,255,255,0.06)",
                      border: c.severity === "real_conflict"
                        ? "1px solid rgba(239,68,68,0.45)"
                        : "1px solid rgba(255,255,255,0.18)",
                      borderRadius: 6,
                      padding: "3px 10px",
                      fontSize: 11,
                      color: c.severity === "real_conflict" ? "#fca5a5" : "inherit",
                      cursor: "pointer",
                    }}
                  >
                    Ver →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function YearExclusionsTable({ exclusions }: { exclusions: YearExclusion[] }) {
  if (exclusions.length === 0) {
    return (
      <section>
        <h4 style={{ margin: "0 0 8px 0", fontSize: 14 }}>Años excluidos</h4>
        <div style={{ opacity: 0.7, fontSize: 13 }}>
          Ningún año eliminado del horizonte.
        </div>
      </section>
    );
  }
  return (
    <section>
      <h4 style={{ margin: "0 0 8px 0", fontSize: 14 }}>Años excluidos del horizonte ({exclusions.length})</h4>
      <div style={{ fontSize: 12, opacity: 0.75, marginBottom: 6 }}>
        Estos años fueron eliminados de <code>osemosys_param_value</code> porque todos sus timeslices tenían YearSplit=0.
        Esta exclusión se aplica automáticamente al importar y al refrescar.
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {exclusions.map((e) => (
          <Badge key={e.year} variant="info">
            {e.year} ({e.n_timeslices_zero}/{e.n_timeslices_total} timeslices = 0)
          </Badge>
        ))}
      </div>
    </section>
  );
}

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 10px",
  fontWeight: 500,
  color: "var(--muted, #94a3b8)",
};
const td: React.CSSProperties = {
  padding: "8px 10px",
  verticalAlign: "top",
};
