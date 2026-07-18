import { useMemo, useState } from "react";

import { scenariosApi } from "@/features/scenarios/api/scenariosApi";
import { simulationApi } from "@/features/simulation/api/simulationApi";
import { paths } from "@/routes/paths";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import type {
  FeasibilityRelaxationReport,
  InfeasibilityDiagnostics,
  SimulationSolver,
  StructuralFinding,
} from "@/types/domain";

type RecoverySuggestion = {
  id: string;
  priority: "high" | "medium";
  source: "structural" | "relaxation";
  title: string;
  explanation: string;
  parameter?: string;
  dimensions: Record<string, string>;
  currentValue?: number;
  suggestedValue?: number;
  minimumChange?: number;
};

const CARD: React.CSSProperties = {
  border: "1px solid rgba(34,197,94,0.32)",
  borderRadius: 8,
  padding: 16,
  background: "rgba(20,83,45,0.12)",
};

const STEP: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "26px 1fr",
  gap: 10,
  alignItems: "start",
};

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function formatNumber(value: number | undefined): string {
  if (value === undefined) return "—";
  const abs = Math.abs(value);
  return abs !== 0 && (abs < 1e-3 || abs >= 1e6)
    ? value.toExponential(5)
    : value.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function relaxationParameter(constraintType: string, side: string): string | undefined {
  const byConstraint: Record<string, string> = {
    TotalAnnualTechnologyActivityLowerlimit: "TotalTechnologyAnnualActivityLowerLimit",
    TotalAnnualTechnologyActivityUpperlimit: "TotalTechnologyAnnualActivityUpperLimit",
    TotalAnnualMaxNewCapacityConstraint: "TotalAnnualMaxCapacityInvestment",
    TotalAnnualMinNewCapacityConstraint: "TotalAnnualMinCapacityInvestment",
    TotalAnnualMaxCapacityConstraint: "TotalAnnualMaxCapacity",
    TotalAnnualMinCapacityConstraint: "TotalAnnualMinCapacity",
    AnnualEmissionsLimit: "AnnualEmissionLimit",
    ModelPeriodEmissionsLimit: "ModelPeriodEmissionLimit",
  };
  if (!byConstraint[constraintType]) return undefined;
  // Para restricciones conocidas el lado sólo confirma si el bound se reduce o aumenta.
  return side ? byConstraint[constraintType] : undefined;
}

function fromStructural(finding: StructuralFinding, index: number): RecoverySuggestion[] {
  const values = finding.values ?? {};
  const dimensions = finding.dimensions ?? {};
  if (finding.code === "PARAMETER_BOUND_CONFLICT") {
    const lower = String(values.lower_parameter ?? "");
    const upper = String(values.upper_parameter ?? "");
    const lowerValue = numberValue(values.lower_value);
    const upperValue = numberValue(values.upper_value);
    if (lower && upper && lowerValue !== undefined && upperValue !== undefined) {
      const gap = numberValue(values.gap) ?? Math.abs(lowerValue - upperValue);
      return [
        {
          id: `structural-${index}-lower`, priority: "high", source: "structural",
          title: `Reducir ${lower}`,
          explanation: `El límite inferior supera el máximo por ${formatNumber(gap)}. Igualarlo al máximo elimina este conflicto directo.`,
          parameter: lower, dimensions, currentValue: lowerValue, suggestedValue: upperValue,
          minimumChange: gap,
        },
        {
          id: `structural-${index}-upper`, priority: "high", source: "structural",
          title: `Aumentar ${upper}`,
          explanation: `El límite superior es menor que el mínimo por ${formatNumber(gap)}. Igualarlo al mínimo elimina este conflicto directo.`,
          parameter: upper, dimensions, currentValue: upperValue, suggestedValue: lowerValue,
          minimumChange: gap,
        },
      ];
    }
  }
  if (finding.code === "MANDATED_ANNUAL_ACTIVITY_WITHOUT_USABLE_CAPACITY") {
    const requiredActivity = numberValue(values.required_activity);
    const capacityActivity = numberValue(values.capacity_activity_upper_bound);
    if (requiredActivity !== undefined && capacityActivity !== undefined) {
      const gap = numberValue(values.gap) ?? Math.max(0, requiredActivity - capacityActivity);
      return [{
        id: `structural-${index}-activity-minimum`, priority: "high", source: "structural",
        title: "Reducir actividad mínima o aumentar capacidad disponible",
        explanation: `La actividad mínima excede el máximo físico por ${formatNumber(gap)}. Reducir el mínimo hasta la actividad disponible elimina esta contradicción necesaria.`,
        parameter: "TotalTechnologyAnnualActivityLowerLimit", dimensions,
        currentValue: requiredActivity, suggestedValue: capacityActivity, minimumChange: gap,
      }];
    }
  }
  if (finding.code === "RESIDUAL_CAPACITY_EXCEEDS_MAXIMUM") {
    const residual = numberValue(values.residual_capacity);
    const maximum = numberValue(values.total_annual_max_capacity);
    if (residual !== undefined && maximum !== undefined) {
      return [{
        id: `structural-${index}-max-capacity`, priority: "high", source: "structural",
        title: "Aumentar capacidad máxima o corregir capacidad residual",
        explanation: "La capacidad residual por sí sola excede el máximo total permitido.",
        parameter: "TotalAnnualMaxCapacity", dimensions, currentValue: maximum,
        suggestedValue: residual, minimumChange: residual - maximum,
      }];
    }
  }
  return [{
    id: `structural-${index}`, priority: "high", source: "structural",
    title: finding.code.replaceAll("_", " "), explanation: finding.message,
    dimensions,
  }];
}

function fromRelaxation(report: FeasibilityRelaxationReport | null | undefined): RecoverySuggestion[] {
  if (!report?.available) return [];
  return report.relaxations.slice(0, 20).map((entry, index) => {
    const parameter = relaxationParameter(entry.constraint_type, entry.side);
    const isLower = entry.side === "LB";
    const suggestedValue = isLower ? entry.bound - entry.slack : entry.bound + entry.slack;
    return {
      id: `relaxation-${index}`, priority: "medium", source: "relaxation",
      title: parameter ? `Ajustar ${parameter}` : `Revisar ${entry.constraint_type}`,
      explanation: entry.suggested_change,
      ...(parameter ? { parameter, suggestedValue } : {}),
      dimensions: entry.indices ?? {}, currentValue: entry.bound, minimumChange: entry.slack,
    };
  });
}

function buildSuggestions(diagnostics: InfeasibilityDiagnostics): RecoverySuggestion[] {
  const structural = (diagnostics.structural_findings ?? []).flatMap(fromStructural);
  const relaxation = fromRelaxation(diagnostics.feasibility_relaxation);
  const seen = new Set<string>();
  return [...structural, ...relaxation].filter((item) => {
    const key = `${item.parameter ?? item.title}|${JSON.stringify(item.dimensions)}|${item.suggestedValue ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function InfeasibilityRecoveryPlanner({
  diagnostics,
  scenarioId,
  solverName,
  sourceJobId,
  navigate,
}: {
  diagnostics: InfeasibilityDiagnostics;
  scenarioId: number | null;
  solverName: string;
  sourceJobId: number;
  navigate: (path: string) => void;
}) {
  const suggestions = useMemo(() => buildSuggestions(diagnostics), [diagnostics]);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [copied, setCopied] = useState(false);
  const [creatingCopy, setCreatingCopy] = useState(false);
  const [scenarioUpdated, setScenarioUpdated] = useState(false);
  const [relaunching, setRelaunching] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  if (suggestions.length === 0) return null;

  const chosen = suggestions.filter((item) => selected.has(item.id));
  const toggle = (id: string) => {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const normalizedSolver = solverName.trim().toLowerCase();
  const canRelaunch = ["highs", "glpk", "gurobi"].includes(normalizedSolver);
  const plan = {
    source_job_id: sourceJobId,
    scenario_id: scenarioId,
    created_in_browser_at: new Date().toISOString(),
    disclaimer: "Plan sugerido; no fue aplicado automáticamente al escenario.",
    selected_suggestions: chosen,
  };

  const copyPlan = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(plan, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      setMessage("No se pudo copiar. Selecciona las sugerencias y usa el editor del escenario.");
    }
  };

  const createSafeCopy = async () => {
    if (!scenarioId) return;
    if (!window.confirm("Se creará una copia del escenario. No se modificarán los datos originales. ¿Continuar?")) return;
    setCreatingCopy(true);
    setMessage(null);
    try {
      const copy = await scenariosApi.cloneScenario(scenarioId, {
        name: `Recuperación infactibilidad · escenario ${scenarioId}`,
        description: `Copia creada desde el diagnóstico del job ${sourceJobId}. Aplicar y validar el plan manualmente.`,
      });
      navigate(paths.scenarioDetail(copy.id));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo crear la copia del escenario.");
    } finally {
      setCreatingCopy(false);
    }
  };

  const relaunch = async () => {
    if (!scenarioId) return;
    if (!scenarioUpdated || !canRelaunch) return;
    if (!window.confirm("Se enviará una nueva simulación del escenario actualizado. ¿Continuar?")) return;
    setRelaunching(true);
    setMessage(null);
    try {
      const solver = normalizedSolver as SimulationSolver;
      const run = await simulationApi.submit(scenarioId, solver, {
        generateLp: true,
        display_name: `Validación recuperación · desde job ${sourceJobId}`,
        description: chosen.length
          ? `Plan de recuperación seleccionado: ${chosen.map((item) => item.parameter ?? item.title).join(", ")}`
          : `Validación posterior al diagnóstico del job ${sourceJobId}`,
      });
      navigate(paths.resultsDetail(run.id));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo enviar la simulación de validación.");
    } finally {
      setRelaunching(false);
    }
  };

  return (
    <section style={CARD}>
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 10 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 17 }}>Plan de recuperación guiado</h2>
          <p style={{ margin: "5px 0 0", fontSize: 13, opacity: 0.85 }}>
            Selecciona hipótesis cuantificadas, edita una copia segura y valida en una nueva corrida. Esta herramienta nunca cambia parámetros automáticamente.
          </p>
        </div>
        <Badge variant="success">{suggestions.length} sugerencias</Badge>
      </div>

      <div style={{ display: "grid", gap: 12, marginTop: 14 }}>
        {suggestions.slice(0, 30).map((item) => (
          <label key={item.id} style={{ display: "flex", gap: 10, padding: 10, borderRadius: 7, cursor: "pointer", background: selected.has(item.id) ? "rgba(34,197,94,0.12)" : "rgba(0,0,0,0.12)", border: `1px solid ${selected.has(item.id) ? "rgba(34,197,94,0.42)" : "rgba(255,255,255,0.08)"}` }}>
            <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggle(item.id)} style={{ marginTop: 3 }} />
            <span style={{ minWidth: 0 }}>
              <Badge variant={item.priority === "high" ? "danger" : "warning"}>{item.source === "structural" ? "ESTRUCTURAL" : "CUANTIFICADO"}</Badge>
              <strong style={{ display: "block", marginTop: 5, fontSize: 13 }}>{item.title}</strong>
              <span style={{ display: "block", marginTop: 3, fontSize: 12, opacity: 0.85 }}>{item.explanation}</span>
              {item.parameter ? <code style={{ display: "block", marginTop: 5, fontSize: 11 }}>{item.parameter} · {Object.entries(item.dimensions).map(([key, value]) => `${key}=${value}`).join(", ")}</code> : null}
              {item.suggestedValue !== undefined ? <small style={{ display: "block", marginTop: 3 }}>Valor sugerido: <strong>{formatNumber(item.suggestedValue)}</strong>{item.currentValue !== undefined ? ` (actual: ${formatNumber(item.currentValue)})` : ""}</small> : null}
            </span>
          </label>
        ))}
      </div>

      <div style={{ display: "grid", gap: 12, marginTop: 18 }}>
        <div style={STEP}>
          <strong style={{ width: 26, height: 26, display: "grid", placeItems: "center", borderRadius: "50%", background: "rgba(34,197,94,0.2)" }}>1</strong>
          <div><strong>Guardar el plan</strong><p style={{ margin: "3px 0 7px", fontSize: 12, opacity: 0.8 }}>Copia las sugerencias seleccionadas para documentar la hipótesis y aplicarla manualmente.</p><Button variant="ghost" onClick={() => void copyPlan()} disabled={chosen.length === 0}>{copied ? "Plan copiado" : `Copiar plan (${chosen.length})`}</Button></div>
        </div>
        <div style={STEP}>
          <strong style={{ width: 26, height: 26, display: "grid", placeItems: "center", borderRadius: "50%", background: "rgba(34,197,94,0.2)" }}>2</strong>
          <div><strong>Editar una copia segura</strong><p style={{ margin: "3px 0 7px", fontSize: 12, opacity: 0.8 }}>Recomendado: conserva el escenario original y aplica los cambios desde el editor de parámetros.</p><Button variant="ghost" onClick={() => void createSafeCopy()} disabled={!scenarioId || creatingCopy}>{creatingCopy ? "Creando copia…" : "Crear copia para recuperación"}</Button></div>
        </div>
        <div style={STEP}>
          <strong style={{ width: 26, height: 26, display: "grid", placeItems: "center", borderRadius: "50%", background: "rgba(34,197,94,0.2)" }}>3</strong>
          <div><strong>Validar la siguiente iteración</strong><p style={{ margin: "3px 0 7px", fontSize: 12, opacity: 0.8 }}>Tras guardar los cambios en el escenario elegido, confírmalo y envía una nueva simulación. El resultado tendrá LP para facilitar el siguiente diagnóstico.</p>{!canRelaunch ? <p style={{ margin: "3px 0 7px", color: "#fbbf24", fontSize: 12 }}>El solver original ({solverName || "desconocido"}) no es relanzable desde este asistente. Elige HiGHS, Gurobi o GLPK en Simulación.</p> : null}<label style={{ display: "flex", gap: 7, fontSize: 12, marginBottom: 8 }}><input type="checkbox" checked={scenarioUpdated} onChange={(event) => setScenarioUpdated(event.target.checked)} /> Confirmo que actualicé el escenario y deseo validarlo.</label><Button onClick={() => void relaunch()} disabled={!scenarioId || !scenarioUpdated || !canRelaunch || relaunching}>{relaunching ? "Enviando validación…" : "Relanzar y validar"}</Button></div>
        </div>
      </div>
      {message ? <p role="alert" style={{ margin: "12px 0 0", color: "#fecaca", fontSize: 12 }}>{message}</p> : null}
    </section>
  );
}
