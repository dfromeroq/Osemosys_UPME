/**
 * SimulationPage - Encolar y gestionar simulaciones OSeMOSYS
 *
 * Funcionalidades:
 * - Seleccionar escenario y solver (HiGHS/GLPK) para encolar una simulación
 * - Ver historial de jobs con filtro por estado (QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED)
 * - Polling automático cada 3s cuando hay jobs activos (en cola o ejecutando)
 * - Cancelar jobs en curso
 * - Ver logs de cada ejecución en modal
 *
 * Endpoints usados:
 * - scenariosApi.listScenarios()
 * - simulationApi.listRuns(), submit(), cancel(), listLogs()
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useCurrentUser } from "@/app/providers/useCurrentUser";
import { useToast } from "@/app/providers/useToast";
import { scenariosApi } from "@/features/scenarios/api/scenariosApi";
import type { UdcConfig, UdcMultiplierEntry } from "@/features/scenarios/api/scenariosApi";
import { simulationApi } from "@/features/simulation/api/simulationApi";
import { RunDisplayNameEditor } from "@/features/simulation/components/RunDisplayNameEditor";
import { VisibilityToggle } from "@/features/simulation/components/VisibilityToggle";
import { getSimulationRunStatusDisplay } from "@/features/simulation/simulationRunStatus";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { DataTable } from "@/shared/components/DataTable";
import { ScenarioTagChip } from "@/shared/components/ScenarioTagChip";
import { Modal } from "@/shared/components/Modal";
import { RunTimingCell } from "@/shared/components/RunTimingCell";
import { paths } from "@/routes/paths";
import type {
  CsvSimulationResult,
  RunResult,
  Scenario,
  ScenarioEditPolicy,
  SimulationLog,
  SimulationOverview,
  SimulationRun,
  SimulationSolver,
  SimulationType,
} from "@/types/domain";

const ACTIVE_STATUSES = new Set(["QUEUED", "RUNNING"]);
const CSV_PREVIEW_LIMIT = 50;
const CRITICAL_SIMULATION_LOG_STAGES = new Set([
  "create_instance",
  "solver",
  "infeasibility_analysis_start",
]);
const CSV_SUBMIT_SPINNER_FRAMES = ["◐", "◓", "◑", "◒"];

const SIMULATION_LOG_STAGE_LABELS: Record<string, string> = {
  extract_data: "Leer insumos",
  build_model: "Preparar modelo",
  data_loaded: "Datos cargados",
  declare_model: "Declarar modelo",
  create_instance: "Crear la instancia",
  solver_start: "Preparar el solver",
  solver: "Resolver la optimización",
  infeasibility_analysis_start: "Analizando infactibilidad",
  infeasibility_analysis_complete: "Análisis de infactibilidad completado",
  complete: "Cerrar ejecución",
  persist_results: "Guardar resultados",
  end: "Finalizar",
  general: "General",
};

function getSolverStatusVariant(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("optimal")) return "success" as const;
  if (normalized.includes("infeasible") || normalized.includes("infactible")) return "danger" as const;
  return "warning" as const;
}

function getSolverLabel(solverName: SimulationSolver) {
  switch (solverName) {
    case "highs":
      return "HiGHS";
    case "glpk":
      return "GLPK";
    case "gurobi":
      return "Gurobi";
  }
}

/** Indica si el solver soporta el análisis de infactibilidad enriquecido
 * (IIS + mapeo a parámetros). HiGHS y Gurobi sí; GLPK no. */
function solverSupportsIIS(solverName: SimulationSolver): boolean {
  return solverName === "highs" || solverName === "gurobi";
}

function formatReadableDuration(totalSeconds: number) {
  const safeSeconds = Math.max(0, Math.round(totalSeconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;

  if (hours > 0) return `${hours} h ${minutes} min ${seconds} s`;
  if (minutes > 0) return `${minutes} min ${seconds} s`;
  return `${seconds} s`;
}

function getSimulationLogDurationSeconds(log: SimulationLog, nextLog?: SimulationLog) {
  const createdAt = new Date(log.created_at);
  const nextCreatedAt = nextLog ? new Date(nextLog.created_at) : null;
  if (!nextCreatedAt || !Number.isFinite(nextCreatedAt.getTime()) || !Number.isFinite(createdAt.getTime())) {
    return null;
  }
  return Math.max(0, (nextCreatedAt.getTime() - createdAt.getTime()) / 1000);
}

function normalizeSimulationLogStage(stage: string | null) {
  return (stage ?? "general").trim().toLowerCase();
}

function formatSimulationLogStage(stage: string | null) {
  const key = normalizeSimulationLogStage(stage);
  const mappedLabel = SIMULATION_LOG_STAGE_LABELS[key];
  if (mappedLabel) return mappedLabel;

  const normalized = key.replace(/_/g, " ").trim();
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function isCriticalSimulationLogStage(stage: string | null) {
  return CRITICAL_SIMULATION_LOG_STAGES.has(normalizeSimulationLogStage(stage));
}

function getSimulationLogVariant(log: SimulationLog) {
  const eventType = (log.event_type ?? "").toLowerCase();
  if (eventType.includes("error")) return "danger" as const;
  if (isCriticalSimulationLogStage(log.stage)) return "info" as const;
  if (eventType.includes("warn")) return "warning" as const;
  if (eventType.includes("info")) return "info" as const;
  if (eventType.includes("stage")) return "neutral" as const;
  return "neutral" as const;
}

function formatCsvValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    return value.toLocaleString(undefined, {
      maximumFractionDigits: Number.isInteger(value) ? 0 : 4,
    });
  }
  if (typeof value === "boolean") return value ? "Sí" : "No";
  if (Array.isArray(value) || typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function toCsvSimulationResult(result: RunResult): CsvSimulationResult {
  const base: CsvSimulationResult = {
    solver_name: result.solver_name,
    objective_value: result.objective_value,
    solver_status: result.solver_status,
    coverage_ratio: result.coverage_ratio,
    total_demand: result.total_demand,
    total_dispatch: result.total_dispatch,
    total_unmet: result.total_unmet,
    dispatch: result.dispatch,
    unmet_demand: result.unmet_demand,
    new_capacity: result.new_capacity,
    annual_emissions: result.annual_emissions,
    stage_times: result.stage_times,
    model_timings: result.model_timings,
  };
  return {
    ...base,
    ...(result.sol ? { sol: result.sol } : {}),
    ...(result.intermediate_variables ? { intermediate_variables: result.intermediate_variables } : {}),
    ...(result.infeasibility_diagnostics ? { infeasibility_diagnostics: result.infeasibility_diagnostics } : {}),
  };
}

function getCsvColumns(rows: Array<Record<string, unknown>>, preferredColumns: string[]) {
  const presentPreferred = preferredColumns.filter((column) =>
    rows.some((row) => Object.prototype.hasOwnProperty.call(row, column)),
  );
  const extraColumns = Array.from(
    new Set(rows.flatMap((row) => Object.keys(row)).filter((column) => !presentPreferred.includes(column))),
  );
  return [...presentPreferred, ...extraColumns];
}

function CsvMetricCard({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "danger" | "success" }) {
  return (
    <div
      style={{
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 12,
        padding: 14,
        background:
          tone === "danger"
            ? "rgba(127,29,29,0.18)"
            : tone === "success"
              ? "rgba(20,83,45,0.18)"
              : "rgba(255,255,255,0.02)",
      }}
    >
      <div style={{ fontSize: 12, opacity: 0.7 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function TablePagination({
  page,
  totalPages,
  onPrevious,
  onNext,
}: {
  page: number;
  totalPages: number;
  onPrevious: () => void;
  onNext: () => void;
}) {
  if (totalPages <= 1) return null;

  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <small style={{ opacity: 0.78 }}>
        Página {page} de {totalPages}
      </small>
      <div style={{ display: "flex", gap: 8 }}>
        <Button variant="ghost" onClick={onPrevious} disabled={page <= 1} type="button">
          Anterior
        </Button>
        <Button variant="ghost" onClick={onNext} disabled={page >= totalPages} type="button">
          Siguiente
        </Button>
      </div>
    </div>
  );
}

function CsvResultTableSection({
  title,
  rows,
  preferredColumns,
  emptyMessage,
  defaultOpen = false,
}: {
  title: string;
  rows: Array<Record<string, unknown>>;
  preferredColumns: string[];
  emptyMessage: string;
  defaultOpen?: boolean;
}) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(rows.length / CSV_PREVIEW_LIMIT));
  const clampedPage = Math.max(1, Math.min(page, totalPages));
  const pageStart = (clampedPage - 1) * CSV_PREVIEW_LIMIT;
  const visibleRows = rows.slice(pageStart, pageStart + CSV_PREVIEW_LIMIT);
  const columns = getCsvColumns(visibleRows, preferredColumns);

  return (
    <details
      open={defaultOpen}
      style={{
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 12,
        padding: 12,
        background: "rgba(255,255,255,0.02)",
      }}
    >
      <summary style={{ cursor: "pointer", fontWeight: 600 }}>
        {title} ({rows.length})
      </summary>
      <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
        {rows.length ? (
          <>
            <small style={{ opacity: 0.78 }}>
              Mostrando {pageStart + 1} a {pageStart + visibleRows.length} de {rows.length} filas.
            </small>
            <TablePagination
              page={clampedPage}
              totalPages={totalPages}
              onPrevious={() =>
                setPage((current) => Math.max(1, Math.min(current, totalPages) - 1))
              }
              onNext={() =>
                setPage((current) => Math.min(totalPages, Math.max(1, Math.min(current, totalPages)) + 1))
              }
            />
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr>
                    {columns.map((column) => (
                      <th
                        key={column}
                        style={{
                          textAlign: "left",
                          padding: "6px 8px",
                          borderBottom: "1px solid rgba(255,255,255,0.2)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row, rowIndex) => (
                    <tr key={`${title}-${rowIndex}`}>
                      {columns.map((column) => (
                        <td
                          key={column}
                          style={{
                            padding: "6px 8px",
                            borderBottom: "1px solid rgba(255,255,255,0.08)",
                            verticalAlign: "top",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {formatCsvValue(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <small style={{ opacity: 0.78 }}>{emptyMessage}</small>
        )}
      </div>
    </details>
  );
}

export function SimulationPage() {
  const { user } = useCurrentUser();
  const { push } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [runs, setRuns] = useState<SimulationRun[]>([]);
  const [overview, setOverview] = useState<SimulationOverview | null>(null);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [errorRuns, setErrorRuns] = useState<string | null>(null);
  const [logsByJob, setLogsByJob] = useState<Record<number, SimulationLog[]>>({});
  const [logsOpenForJob, setLogsOpenForJob] = useState<number | null>(null);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [solverName, setSolverName] = useState<SimulationSolver>("highs");
  /** Nombre opcional al encolar desde escenario (si está vacío, el backend usa el nombre del escenario). */
  const [newRunDisplayName, setNewRunDisplayName] = useState("");
  const [csvSolverName, setCsvSolverName] = useState<SimulationSolver>("highs");
  // Si el usuario marca estos checkboxes al encolar, el pipeline corre el
  // análisis enriquecido de infactibilidad (IIS + mapeo a parámetros) inline
  // cuando el modelo es infactible. Por defecto NO (útil para pruebas locales).
  const [runIisAnalysis, setRunIisAnalysis] = useState<boolean>(false);
  const [generateLp, setGenerateLp] = useState<boolean>(false);
  const [csvRunIisAnalysis, setCsvRunIisAnalysis] = useState<boolean>(false);
  const [csvGenerateLp, setCsvGenerateLp] = useState<boolean>(false);
  const [csvRunDisplayName, setCsvRunDisplayName] = useState("");
  const [csvZipFile, setCsvZipFile] = useState<File | null>(null);
  const [csvInputName, setCsvInputName] = useState("");
  const [csvSimulationType, setCsvSimulationType] = useState<SimulationType>("NATIONAL");
  const [csvSaveAsScenario, setCsvSaveAsScenario] = useState(false);
  const [csvScenarioName, setCsvScenarioName] = useState("");
  const [csvScenarioDescription, setCsvScenarioDescription] = useState("");
  const [csvScenarioEditPolicy, setCsvScenarioEditPolicy] = useState<ScenarioEditPolicy>("OWNER_ONLY");
  const [csvSubmitting, setCsvSubmitting] = useState(false);
  const [csvResult, setCsvResult] = useState<CsvSimulationResult | null>(null);
  const [csvResultOpen, setCsvResultOpen] = useState(false);
  const [csvTrackedJobId, setCsvTrackedJobId] = useState<number | null>(null);
  const [csvResultSourceJobId, setCsvResultSourceJobId] = useState<number | null>(null);
  const [csvLoadingResultForJobId, setCsvLoadingResultForJobId] = useState<number | null>(null);
  const [csvSubmitPhase, setCsvSubmitPhase] = useState<"uploading" | "importing_scenario" | null>(null);
  const [csvSubmitStartedAt, setCsvSubmitStartedAt] = useState<number | null>(null);
  const [csvSubmitElapsedSeconds, setCsvSubmitElapsedSeconds] = useState(0);
  const [cancellingJobId, setCancellingJobId] = useState<number | null>(null);
  const [triggeringDiagnosticFor, setTriggeringDiagnosticFor] = useState<number | null>(null);
  const [cancellingDiagnosticFor, setCancellingDiagnosticFor] = useState<number | null>(null);
  // Tick de 1 s usado para refrescar los contadores de segundos en vivo cuando
  // algún diagnóstico está RUNNING.
  const [liveTickMs, setLiveTickMs] = useState<number>(() => Date.now());
  const [simulationTab, setSimulationTab] = useState<"osemosys" | "csv">("osemosys");
  const [scenarioDropdownOpen, setScenarioDropdownOpen] = useState(false);
  const scenarioDropdownRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!scenarioDropdownOpen) return;
    function onDocumentClick(e: MouseEvent) {
      if (scenarioDropdownRef.current && !scenarioDropdownRef.current.contains(e.target as Node)) {
        setScenarioDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocumentClick);
    return () => document.removeEventListener("mousedown", onDocumentClick);
  }, [scenarioDropdownOpen]);

  const [udcConfig, setUdcConfig] = useState<UdcConfig | null>(null);
  const [udcOpen, setUdcOpen] = useState(false);
  const [udcSaving, setUdcSaving] = useState(false);
  const [udcNewTech, setUdcNewTech] = useState("");
  const [udcNewValue, setUdcNewValue] = useState("0");

  const formatBytes = useCallback((bytes: number) => {
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024;
      unitIndex += 1;
    }
    return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
  }, []);

  useEffect(() => {
    const id = Number(selectedScenario);
    if (!id) { setUdcConfig(null); return; }
    void scenariosApi.getUdcConfig(id).then(setUdcConfig).catch(() => setUdcConfig(null));
  }, [selectedScenario]);

  useEffect(() => {
    if (!csvSubmitting || csvSubmitStartedAt == null) {
      setCsvSubmitElapsedSeconds(0);
      return;
    }
    setCsvSubmitElapsedSeconds(Math.max(0, Math.floor((Date.now() - csvSubmitStartedAt) / 1000)));
    const timer = window.setInterval(() => {
      setCsvSubmitElapsedSeconds(Math.max(0, Math.floor((Date.now() - csvSubmitStartedAt) / 1000)));
    }, 250);
    return () => window.clearInterval(timer);
  }, [csvSubmitting, csvSubmitStartedAt]);

  async function saveUdcConfig() {
    const id = Number(selectedScenario);
    if (!id || !udcConfig) return;
    setUdcSaving(true);
    try {
      const saved = await scenariosApi.updateUdcConfig(id, udcConfig);
      setUdcConfig(saved);
      push("Configuración UDC guardada.", "success");
    } catch (e) {
      push(e instanceof Error ? e.message : "Error guardando UDC.", "error");
    } finally {
      setUdcSaving(false);
    }
  }

  /** Recarga el historial de jobs. Trae un lote amplio porque el filtrado
   * ahora es 100% client-side desde los filtros por columna del DataTable.
   * `silent=true` evita mostrar el skeleton (usado por el polling en background). */
  const refreshRuns = useCallback(async (silent = false) => {
    if (!silent) setLoadingRuns(true);
    setErrorRuns(null);
    try {
      const params = {
        scope: "global" as const,
        cantidad: 200,
        offset: 1,
      };
      const [res, overviewRes] = await Promise.all([simulationApi.listRuns(params), simulationApi.getOverview()]);
      setRuns(res.data);
      setOverview(overviewRes);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "No se pudo cargar el historial de simulaciones.";
      setErrorRuns(message);
      if (!silent) push(message, "error");
    } finally {
      if (!silent) setLoadingRuns(false);
    }
  }, [push]);

  useEffect(() => {
    if (!user) return;
    setLoadingScenarios(true);
    void scenariosApi
      .listScenarios({ cantidad: 200, offset: 1 })
      .then((res) => setScenarios(res.data))
      .catch(() => setScenarios([]))
      .finally(() => setLoadingScenarios(false));
  }, [user]);

  // Preselecciona un escenario cuando se llega desde la tabla de /app/scenarios
  // con `?scenario=<id>`. Se hace una vez que la lista está cargada y el id es
  // válido; luego se limpia el query param para que un refresh no vuelva a
  // sobrescribir cualquier selección manual del usuario.
  useEffect(() => {
    const raw = searchParams.get("scenario");
    if (!raw || scenarios.length === 0) return;
    const exists = scenarios.some((s) => String(s.id) === raw);
    if (!exists) return;
    setSelectedScenario(raw);
    setSimulationTab("osemosys");
    const next = new URLSearchParams(searchParams);
    next.delete("scenario");
    setSearchParams(next, { replace: true });
  }, [scenarios, searchParams, setSearchParams]);

  // Polling cada 3s mientras haya jobs en cola/ejecución o diagnósticos en curso
  useEffect(() => {
    const hasActiveJob = runs.some((run) => ACTIVE_STATUSES.has(run.status));
    const hasActiveDiagnostic = runs.some(
      (run) =>
        run.diagnostic_status === "QUEUED" || run.diagnostic_status === "RUNNING",
    );
    if (!hasActiveJob && !hasActiveDiagnostic) return;
    const timer = window.setInterval(() => {
      void refreshRuns(true);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [refreshRuns, runs]);

  // Tick de 1 s para que los contadores de segundos ("Diagnosticando (X s)…")
  // se actualicen en vivo mientras haya al menos un diagnóstico RUNNING.
  useEffect(() => {
    const hasRunningDiagnostic = runs.some(
      (run) => run.diagnostic_status === "RUNNING",
    );
    if (!hasRunningDiagnostic) return;
    setLiveTickMs(Date.now());
    const id = window.setInterval(() => setLiveTickMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [runs]);

  useEffect(() => {
    if (!user) return;
    void refreshRuns();
  }, [refreshRuns, user]);

  useEffect(() => {
    if (!csvTrackedJobId) return;
    const trackedRun = runs.find((run) => run.id === csvTrackedJobId);
    if (!trackedRun) return;

    if (trackedRun.status === "SUCCEEDED") {
      if (csvLoadingResultForJobId === csvTrackedJobId || csvResultSourceJobId === csvTrackedJobId) {
        return;
      }
      setCsvLoadingResultForJobId(csvTrackedJobId);
      void simulationApi
        .getResult(csvTrackedJobId)
        .then((result) => {
          setCsvResult(toCsvSimulationResult(result));
          setCsvResultSourceJobId(csvTrackedJobId);
          setCsvResultOpen(true);
          push(`Resultados del job CSV ${csvTrackedJobId} disponibles.`, "success");
        })
        .catch((error) => {
          const detail =
            error instanceof Error ? error.message : "No se pudieron cargar los resultados del job CSV.";
          push(detail, "error");
        })
        .finally(() => {
          setCsvLoadingResultForJobId(null);
          setCsvTrackedJobId(null);
        });
      return;
    }

    if (trackedRun.status === "FAILED") {
      push(
        trackedRun.error_message
          ? `La simulación CSV falló: ${trackedRun.error_message}`
          : "La simulación CSV falló.",
        "error",
      );
      setCsvTrackedJobId(null);
      return;
    }

    if (trackedRun.status === "CANCELLED") {
      push("La simulación CSV fue cancelada.", "info");
      setCsvTrackedJobId(null);
    }
  }, [csvLoadingResultForJobId, csvResultSourceJobId, csvTrackedJobId, push, runs]);

  /** Encola una simulación para el escenario y solver seleccionados */
  async function runSimulation() {
    const scenarioId = Number(selectedScenario);
    if (!scenarioId) {
      push("Selecciona un escenario antes de ejecutar.", "error");
      return;
    }
    setSubmitting(true);
    try {
      await simulationApi.submit(scenarioId, solverName, {
        runIisAnalysis,
        generateLp,
        display_name: newRunDisplayName.trim() || null,
      });
      push("Simulación encolada correctamente.", "success");
      setNewRunDisplayName("");
      await refreshRuns();
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Error enviando simulación.";
      push(detail, "error");
    } finally {
      setSubmitting(false);
    }
  }

  /** Cancela un job en curso; actualiza UI optimista antes de confirmar */
  const [deleteCandidateJob, setDeleteCandidateJob] = useState<SimulationRun | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<number | null>(null);

  async function confirmDeleteJob() {
    if (!deleteCandidateJob) return;
    const id = deleteCandidateJob.id;
    setDeletingJobId(id);
    try {
      await simulationApi.deleteJob(id);
      push(`Simulación ${id} eliminada.`, "success");
      setDeleteCandidateJob(null);
      await refreshRuns();
    } catch (error) {
      const detail = error instanceof Error ? error.message : "No se pudo eliminar.";
      push(detail, "error");
    } finally {
      setDeletingJobId(null);
    }
  }

  async function cancelSimulation(jobId: number) {
    setCancellingJobId(jobId);
    setRuns((prev) =>
      prev.map((r) => (r.id === jobId ? { ...r, status: "CANCELLED" as const } : r))
    );
    try {
      await simulationApi.cancel(jobId);
      push(`Simulación ${jobId} cancelada.`, "info");
      await refreshRuns();
    } catch (error) {
      const detail = error instanceof Error ? error.message : "No se pudo cancelar.";
      push(detail, "error");
      await refreshRuns();
    } finally {
      setCancellingJobId(null);
    }
  }

  /** Cancela un diagnóstico en QUEUED/RUNNING y refresca la lista. */
  async function cancelDiagnostic(jobId: number) {
    setCancellingDiagnosticFor(jobId);
    try {
      await simulationApi.cancelInfeasibilityDiagnostic(jobId);
      push(`Diagnóstico del job ${jobId} cancelado.`, "info");
      await refreshRuns();
    } catch (error) {
      const detail =
        error instanceof Error ? error.message : "No se pudo cancelar el diagnóstico.";
      push(detail, "error");
    } finally {
      setCancellingDiagnosticFor(null);
    }
  }

  /** Dispara el análisis de infactibilidad (IIS + mapeo a parámetros) para un
   * job HiGHS infactible. El análisis se ejecuta en un worker Celery aparte;
   * refrescamos el listado para ver el nuevo estado. */
  async function requestDiagnostic(jobId: number) {
    setTriggeringDiagnosticFor(jobId);
    try {
      await simulationApi.runInfeasibilityDiagnostic(jobId);
      push(`Diagnóstico de infactibilidad del job ${jobId} encolado.`, "info");
      await refreshRuns();
    } catch (error) {
      const detail =
        error instanceof Error
          ? error.message
          : "No se pudo encolar el diagnóstico.";
      push(detail, "error");
    } finally {
      setTriggeringDiagnosticFor(null);
    }
  }

  /** Descarga el archivo `.lp` del modelo Pyomo (cuando la corrida fue
   * lanzada con `generate_lp=true`). */
  async function downloadLpForJob(jobId: number) {
    try {
      const { blob, filename } = await simulationApi.downloadLpFile(jobId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      const detail =
        error instanceof Error
          ? error.message
          : "No se pudo descargar el archivo .lp.";
      push(detail, "error");
    }
  }

  /** Carga los logs de un job y abre el modal */
  async function loadLogs(jobId: number) {
    try {
      setLoadingLogs(true);
      const res = await simulationApi.listLogs(jobId, 100, 1);
      setLogsByJob((prev) => ({ ...prev, [jobId]: res.data }));
      setLogsOpenForJob(jobId);
    } catch {
      push("No se pudieron cargar logs del job.", "error");
    } finally {
      setLoadingLogs(false);
    }
  }

  async function runCsvSimulation() {
    if (!csvZipFile) {
      push("Selecciona un archivo ZIP con los CSV antes de ejecutar.", "error");
      return;
    }
    if (csvSaveAsScenario && !csvScenarioName.trim()) {
      push("El nombre del escenario es obligatorio cuando eliges guardar el ZIP como escenario.", "error");
      return;
    }
    setCsvSubmitting(true);
    setCsvResultOpen(false);
    setCsvResult(null);
    setCsvResultSourceJobId(null);
    setCsvTrackedJobId(null);
    setCsvSubmitPhase(csvSaveAsScenario ? "importing_scenario" : "uploading");
    setCsvSubmitStartedAt(Date.now());
    try {
      const job = await simulationApi.submitFromCsv(
        csvZipFile,
        csvSolverName,
        csvRunIisAnalysis,
        {
          input_name: csvInputName,
          simulation_type: csvSimulationType,
          save_as_scenario: csvSaveAsScenario,
          scenario_name: csvScenarioName,
          description: csvScenarioDescription,
          edit_policy: csvScenarioEditPolicy,
          display_name: csvInputName.trim() || null,
        },
        { generateLp: csvGenerateLp },
      );
      setCsvTrackedJobId(job.id);
      setRuns((prev) => [job, ...prev.filter((run) => run.id !== job.id)]);
      push(
        csvSaveAsScenario
          ? `Escenario creado y simulación encolada como job ${job.id}.`
          : `Simulación desde CSV encolada como job ${job.id}.`,
        "success",
      );
      setCsvInputName("");
      await refreshRuns();
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Error ejecutando simulación desde CSV.";
      push(detail, "error");
    } finally {
      setCsvSubmitPhase(null);
      setCsvSubmitStartedAt(null);
      setCsvSubmitting(false);
    }
  }

  function downloadCsvResultJson() {
    if (!csvResult) return;
    const blob = new Blob([JSON.stringify(csvResult, null, 2)], { type: "application/json" });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "simulation_from_csv_result.json";
    link.click();
    window.URL.revokeObjectURL(url);
  }

  // Filtrado por estado seleccionado (ALL = sin filtrar)

  const handleRunDisplayNameSaved = useCallback((jobId: number, next: string | null) => {
    setRuns((prev) => prev.map((r) => (r.id === jobId ? { ...r, display_name: next } : r)));
  }, []);

  const handleVisibilityChanged = useCallback((jobId: number, next: boolean) => {
    setRuns((prev) => prev.map((r) => (r.id === jobId ? { ...r, is_public: next } : r)));
  }, []);

  const currentUserId = user?.id ?? null;
  const ownedSet = useMemo(
    () => new Set(runs.filter((r) => r.user_id === currentUserId).map((r) => r.id)),
    [runs, currentUserId],
  );

  const selectedLogs = logsOpenForJob ? logsByJob[logsOpenForJob] ?? [] : [];
  const csvSpinnerFrame =
    CSV_SUBMIT_SPINNER_FRAMES[csvSubmitElapsedSeconds % CSV_SUBMIT_SPINNER_FRAMES.length] ?? "◐";
  const csvEstimatedDurationLabel =
    csvSubmitPhase === "importing_scenario" ? "1 a 4 min" : "10 a 30 s";
  const csvCurrentPhaseLabel =
    csvSubmitPhase === "importing_scenario"
      ? "Importando ZIP como escenario"
      : "Subiendo ZIP y creando el job";

  // Job mostrado en el modal de registros (para saber si sigue corriendo).
  const selectedLogsJob = useMemo(
    () => (logsOpenForJob ? runs.find((r) => r.id === logsOpenForJob) ?? null : null),
    [logsOpenForJob, runs],
  );
  const selectedLogsJobActive = selectedLogsJob
    ? ACTIVE_STATUSES.has(selectedLogsJob.status)
    : false;

  // Tick reactivo para contadores en vivo (refresca cada segundo mientras el
  // modal está abierto sobre un job en curso).
  const [liveNowMs, setLiveNowMs] = useState<number>(() => Date.now());
  useEffect(() => {
    if (logsOpenForJob === null || !selectedLogsJobActive) return;
    setLiveNowMs(Date.now());
    const id = window.setInterval(() => setLiveNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [logsOpenForJob, selectedLogsJobActive]);

  // Polling: mientras el modal esté abierto sobre un job activo, re-cargamos
  // los logs cada 3 s para que los nuevos stages del backend (incluido
  // "infeasibility_analysis_start"/"_complete") aparezcan sin intervención.
  // Llamamos directamente a la API (sin pasar por loadLogs) para no depender
  // de una función que se recrea en cada render.
  useEffect(() => {
    if (logsOpenForJob === null || !selectedLogsJobActive) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await simulationApi.listLogs(logsOpenForJob, 100, 1);
        if (cancelled) return;
        setLogsByJob((prev) => ({ ...prev, [logsOpenForJob]: res.data }));
      } catch {
        // silencioso: errores de red esporádicos no deben cerrar el modal
      }
    };
    const id = window.setInterval(() => {
      void poll();
    }, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [logsOpenForJob, selectedLogsJobActive]);

  // Resumen para el banner del modal: tiempo total desde el primer evento y
  // duración del stage actual (último evento). Si el job ya terminó, congela
  // los contadores al instante del último evento.
  const logsBanner = useMemo(() => {
    const firstLog = selectedLogs[0];
    const lastLog = selectedLogs[selectedLogs.length - 1];
    if (!firstLog || !lastLog) return null;
    const firstMs = new Date(firstLog.created_at).getTime();
    const lastMs = new Date(lastLog.created_at).getTime();
    const endMs = selectedLogsJobActive ? liveNowMs : lastMs;
    const totalSeconds = Number.isFinite(firstMs) ? Math.max(0, (endMs - firstMs) / 1000) : 0;
    const currentStageSeconds = Number.isFinite(lastMs)
      ? Math.max(0, (endMs - lastMs) / 1000)
      : 0;

    // Detectar si el análisis de infactibilidad está EN CURSO:
    // el último evento es "infeasibility_analysis_start" y NO hay aún un
    // "infeasibility_analysis_complete" posterior.
    const lastStage = normalizeSimulationLogStage(lastLog.stage);
    const infeasAnalysisRunning =
      selectedLogsJobActive && lastStage === "infeasibility_analysis_start";

    // Instante en que comenzó el análisis (si ya empezó, esté corriendo o no).
    const startEvent = [...selectedLogs]
      .reverse()
      .find((l) => normalizeSimulationLogStage(l.stage) === "infeasibility_analysis_start");
    const infeasStartedAt = startEvent ? new Date(startEvent.created_at) : null;
    const infeasElapsedSeconds = infeasStartedAt
      ? Math.max(0, (endMs - infeasStartedAt.getTime()) / 1000)
      : null;

    return {
      firstAt: new Date(firstMs),
      lastAt: new Date(lastMs),
      totalSeconds,
      currentStageSeconds,
      currentStageName: lastLog.stage,
      infeasAnalysisRunning,
      infeasStartedAt,
      infeasElapsedSeconds,
    };
  }, [selectedLogs, selectedLogsJobActive, liveNowMs]);

  return (
    <section style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Button
          variant={simulationTab === "osemosys" ? "primary" : "ghost"}
          onClick={() => setSimulationTab("osemosys")}
        >
          Simulación OSeMOSYS
        </Button>
        <Button
          variant={simulationTab === "csv" ? "primary" : "ghost"}
          onClick={() => setSimulationTab("csv")}
        >
          Simulación desde CSV
        </Button>
      </div>
      {simulationTab === "osemosys" ? (
      <article className="pageSection" style={{ display: "grid", gap: 12 }}>
        <h1 style={{ margin: 0 }}>Simulación OSeMOSYS</h1>
        <small style={{ opacity: 0.78 }}>
          Encola ejecuciones y revisa la cola global.
        </small>
        <div
          style={{
            display: "grid",
            gap: 10,
            gridTemplateColumns:
              "minmax(220px, 1.1fr) minmax(200px, 1fr) minmax(160px, 220px) auto auto",
            alignItems: "end",
          }}
        >
          <label className="field" style={{ margin: 0 }}>
            <span className="field__label">Escenario</span>
            {(() => {
              const selected = scenarios.find((s) => String(s.id) === selectedScenario);
              return (
                <div ref={scenarioDropdownRef} style={{ position: "relative" }}>
                  <button
                    type="button"
                    className="field__input"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                      textAlign: "left",
                      cursor: loadingScenarios ? "not-allowed" : "pointer",
                      opacity: loadingScenarios ? 0.6 : 1,
                    }}
                    disabled={loadingScenarios}
                    onClick={() => setScenarioDropdownOpen((v) => !v)}
                  >
                    <span style={{ display: "flex", alignItems: "center", gap: 4, minWidth: 0, flex: 1, flexWrap: "wrap" }}>
                      {(selected?.tags ?? (selected?.tag ? [selected.tag] : [])).map((t) => (
                        <ScenarioTagChip key={t.id} tag={t} size="sm" />
                      ))}
                      <span
                        style={{
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          opacity: selected ? 1 : 0.6,
                        }}
                      >
                        {selected ? selected.name : loadingScenarios ? "Cargando escenarios..." : "Selecciona..."}
                      </span>
                    </span>
                    <span style={{ opacity: 0.7 }}>{scenarioDropdownOpen ? "▴" : "▾"}</span>
                  </button>
                  {scenarioDropdownOpen ? (
                    <div
                      role="listbox"
                      style={{
                        position: "absolute",
                        top: "calc(100% + 4px)",
                        left: 0,
                        right: 0,
                        zIndex: 20,
                        background: "#0f172a",
                        border: "1px solid rgba(255,255,255,0.2)",
                        borderRadius: 12,
                        padding: 4,
                        maxHeight: 320,
                        overflowY: "auto",
                        boxShadow: "0 10px 30px rgba(0,0,0,0.4)",
                      }}
                    >
                      <div
                        role="option"
                        aria-selected={selectedScenario === ""}
                        onClick={() => {
                          setSelectedScenario("");
                          setScenarioDropdownOpen(false);
                        }}
                        style={{
                          padding: "8px 10px",
                          borderRadius: 8,
                          cursor: "pointer",
                          opacity: 0.7,
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.06)")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                      >
                        Selecciona...
                      </div>
                      {scenarios.map((s) => (
                        <div
                          key={s.id}
                          role="option"
                          aria-selected={String(s.id) === selectedScenario}
                          onClick={() => {
                            setSelectedScenario(String(s.id));
                            setScenarioDropdownOpen(false);
                          }}
                          style={{
                            padding: "8px 10px",
                            borderRadius: 8,
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            background:
                              String(s.id) === selectedScenario ? "rgba(56,189,248,0.15)" : "transparent",
                          }}
                          onMouseEnter={(e) => {
                            if (String(s.id) !== selectedScenario)
                              e.currentTarget.style.background = "rgba(255,255,255,0.06)";
                          }}
                          onMouseLeave={(e) => {
                            if (String(s.id) !== selectedScenario)
                              e.currentTarget.style.background = "transparent";
                          }}
                        >
                          <span style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                            {(s.tags ?? (s.tag ? [s.tag] : [])).map((t) => (
                              <ScenarioTagChip key={t.id} tag={t} size="sm" />
                            ))}
                          </span>
                          <span
                            style={{
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {s.name}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })()}
          </label>
          <label className="field" style={{ margin: 0 }}>
            <span className="field__label">Nombre del resultado (opcional)</span>
            <input
              className="field__input"
              type="text"
              maxLength={255}
              value={newRunDisplayName}
              onChange={(e) => setNewRunDisplayName(e.target.value)}
              placeholder="Ej. Caso base 2030 — sensibilidad"
              disabled={submitting}
              autoComplete="off"
            />
          </label>
          <label className="field" style={{ margin: 0 }}>
            <span className="field__label">Solver</span>
            <select
              className="field__input"
              value={solverName}
              onChange={(e) => {
                const next = e.target.value as SimulationSolver;
                setSolverName(next);
                if (!solverSupportsIIS(next)) setRunIisAnalysis(false);
              }}
            >
              <option value="highs">HiGHS</option>
              <option value="glpk">GLPK</option>
              <option value="gurobi">Gurobi</option>
            </select>
          </label>
          <Button variant="primary" onClick={runSimulation} disabled={submitting || !selectedScenario}>
            {submitting ? "Encolando..." : "Ejecutar simulación"}
          </Button>
          <Button variant="ghost" onClick={() => refreshRuns()} disabled={loadingRuns}>
            Refrescar estado
          </Button>
        </div>
        <label
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            fontSize: 13,
            opacity: 0.9,
            cursor: "pointer",
            userSelect: "none",
            width: "fit-content",
          }}
          title={
            solverSupportsIIS(solverName)
              ? "Cuando el modelo sea infactible, el pipeline corre automáticamente el IIS y mapea las restricciones a los parámetros OSeMOSYS. Tarda más pero te ahorra lanzar el diagnóstico manualmente."
              : "El diagnóstico automático requiere HiGHS o Gurobi. Cambia el solver para habilitar esta opción."
          }
        >
          <input
            type="checkbox"
            checked={runIisAnalysis}
            disabled={!solverSupportsIIS(solverName)}
            onChange={(e) => setRunIisAnalysis(e.target.checked)}
          />
          <span>
            Correr diagnóstico de infactibilidad automáticamente{" "}
            <span style={{ opacity: 0.7 }}>(HiGHS o Gurobi)</span>
          </span>
        </label>
        <label
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            fontSize: 13,
            opacity: 0.9,
            cursor: "pointer",
            userSelect: "none",
            width: "fit-content",
          }}
          title="Escribe el modelo a tmp/lp-files/sim_<id>_<nombre>_<timestamp>.lp antes de resolver. Útil para inspeccionar el modelo o reproducirlo en otro solver."
        >
          <input
            type="checkbox"
            checked={generateLp}
            onChange={(e) => setGenerateLp(e.target.checked)}
          />
          <span>
            Guardar archivo .lp del modelo{" "}
            <span style={{ opacity: 0.7 }}>(tmp/lp-files/)</span>
          </span>
        </label>
        <small style={{ opacity: 0.72, margin: 0 }}>
          Si dejas el nombre vacío, se usará el nombre del escenario como etiqueta de la corrida.
        </small>
      </article>
      ) : null}

      {simulationTab === "csv" ? (
      <article className="pageSection" style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "grid", gap: 4 }}>
          <h2 style={{ margin: 0 }}>Simulación desde CSV</h2>
          <small style={{ opacity: 0.78 }}>
            Sube un ZIP con CSV ya procesados (`YEAR.csv`, `REGION.csv`, `TECHNOLOGY.csv`, etc.) para encolar una corrida persistida y consultarla luego en el historial.
          </small>
        </div>
        <div
          style={{
            display: "grid",
            gap: 10,
            gridTemplateColumns:
              "minmax(220px, 1fr) minmax(180px, 240px) minmax(180px, 220px) minmax(200px, 1fr) auto",
            alignItems: "end",
          }}
        >
          <label className="field" style={{ margin: 0 }}>
            <span className="field__label">ZIP de CSV</span>
            <input
              className="field__input"
              type="file"
              accept=".zip,application/zip"
              onChange={(e) => {
                const nextFile = e.target.files?.[0] ?? null;
                setCsvZipFile(nextFile);
                if (csvSaveAsScenario && nextFile && !csvScenarioName.trim()) {
                  setCsvScenarioName(nextFile.name.replace(/\.zip$/i, ""));
                }
              }}
            />
          </label>
          <label className="field" style={{ margin: 0 }}>
            <span className="field__label">
              {csvSaveAsScenario
                ? "Nombre visible de la simulación (opcional)"
                : "Nombre visible de la corrida"}
            </span>
            <input
              className="field__input"
              value={csvInputName}
              onChange={(e) => setCsvInputName(e.target.value)}
              placeholder={
                csvSaveAsScenario
                  ? "Ej: Corrida base importada desde CSV"
                  : (csvZipFile?.name ?? "Ej: Modelo nacional abril")
              }
              disabled={csvSubmitting}
              autoComplete="off"
            />
          </label>
          <label className="field" style={{ margin: 0 }}>
            <span className="field__label">Nombre del resultado (opcional)</span>
            <input
              className="field__input"
              type="text"
              maxLength={255}
              value={csvRunDisplayName}
              onChange={(e) => setCsvRunDisplayName(e.target.value)}
              placeholder="Ej. Prueba importación Q1"
              disabled={csvSubmitting}
              autoComplete="off"
            />
          </label>
          <label className="field" style={{ margin: 0 }}>
            <span className="field__label">Solver</span>
            <select
              className="field__input"
              value={csvSolverName}
              onChange={(e) => {
                const next = e.target.value as SimulationSolver;
                setCsvSolverName(next);
                if (!solverSupportsIIS(next)) setCsvRunIisAnalysis(false);
              }}
            >
              <option value="highs">HiGHS</option>
              <option value="glpk">GLPK</option>
              <option value="gurobi">Gurobi</option>
            </select>
          </label>
          <label className="field" style={{ margin: 0 }}>
            <span className="field__label">Tipo de simulación</span>
            <select
              className="field__input"
              value={csvSimulationType}
              onChange={(e) => setCsvSimulationType(e.target.value as SimulationType)}
            >
              <option value="NATIONAL">Nacional</option>
              <option value="REGIONAL">Regional</option>
            </select>
          </label>
          <Button variant="primary" onClick={runCsvSimulation} disabled={csvSubmitting || !csvZipFile}>
            {csvSubmitting
              ? (csvSaveAsScenario ? "Creando escenario..." : "Encolando...")
              : "Ejecutar desde CSV"}
          </Button>
        </div>
        <label
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            fontSize: 13,
            opacity: 0.9,
            cursor: "pointer",
            userSelect: "none",
            width: "fit-content",
          }}
          title={
            solverSupportsIIS(csvSolverName)
              ? "Cuando el modelo sea infactible, el pipeline corre automáticamente el IIS y mapea las restricciones a los parámetros OSeMOSYS."
              : "El diagnóstico automático requiere HiGHS o Gurobi. Cambia el solver para habilitar esta opción."
          }
        >
          <input
            type="checkbox"
            checked={csvRunIisAnalysis}
            disabled={!solverSupportsIIS(csvSolverName)}
            onChange={(e) => setCsvRunIisAnalysis(e.target.checked)}
          />
          <span>
            Correr diagnóstico de infactibilidad automáticamente{" "}
            <span style={{ opacity: 0.7 }}>(HiGHS o Gurobi)</span>
          </span>
        </label>
        <label
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            fontSize: 13,
            opacity: 0.9,
            cursor: "pointer",
            userSelect: "none",
            width: "fit-content",
          }}
          title="Escribe el modelo a tmp/lp-files/sim_<id>_<nombre>_<timestamp>.lp antes de resolver."
        >
          <input
            type="checkbox"
            checked={csvGenerateLp}
            onChange={(e) => setCsvGenerateLp(e.target.checked)}
          />
          <span>
            Guardar archivo .lp del modelo{" "}
            <span style={{ opacity: 0.7 }}>(tmp/lp-files/)</span>
          </span>
        </label>
        <label style={{ display: "flex", gap: 8, alignItems: "center", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={csvSaveAsScenario}
            onChange={(e) => {
              const checked = e.target.checked;
              setCsvSaveAsScenario(checked);
              if (checked && csvZipFile && !csvScenarioName.trim()) {
                setCsvScenarioName(csvZipFile.name.replace(/\.zip$/i, ""));
              }
            }}
          />
          <span>Guardar estos CSV como escenario y correr sobre ese escenario</span>
        </label>
        {csvSaveAsScenario ? (
          <div
            style={{
              border: "1px solid rgba(255,255,255,0.08)",
              background: "rgba(255,255,255,0.03)",
              borderRadius: 12,
              padding: 12,
              display: "grid",
              gap: 4,
            }}
          >
            <strong style={{ fontSize: 13 }}>Este flujo tarda más.</strong>
            <small style={{ opacity: 0.78 }}>
              Primero importa el ZIP completo como escenario y luego encola la simulación. Puede tardar varios minutos antes de devolver el job.
            </small>
          </div>
        ) : null}
        {csvSaveAsScenario ? (
          <div
            style={{
              display: "grid",
              gap: 10,
              gridTemplateColumns: "minmax(220px, 1fr) minmax(220px, 1fr) minmax(180px, 220px)",
              alignItems: "end",
            }}
          >
            <label className="field" style={{ margin: 0 }}>
              <span className="field__label">Nombre del escenario</span>
              <input
                className="field__input"
                value={csvScenarioName}
                onChange={(e) => setCsvScenarioName(e.target.value)}
                placeholder="Ej: Escenario nacional CSV"
              />
            </label>
            <label className="field" style={{ margin: 0 }}>
              <span className="field__label">Descripción</span>
              <input
                className="field__input"
                value={csvScenarioDescription}
                onChange={(e) => setCsvScenarioDescription(e.target.value)}
                placeholder="Opcional"
              />
            </label>
            <label className="field" style={{ margin: 0 }}>
              <span className="field__label">Política de edición</span>
              <select
                className="field__input"
                value={csvScenarioEditPolicy}
                onChange={(e) => setCsvScenarioEditPolicy(e.target.value as ScenarioEditPolicy)}
              >
                <option value="OWNER_ONLY">Solo propietario</option>
                <option value="OPEN">Abierta</option>
                <option value="RESTRICTED">Restringida</option>
              </select>
            </label>
          </div>
        ) : null}
        {csvZipFile ? (
          <small style={{ opacity: 0.78 }}>
            Archivo seleccionado: <strong>{csvZipFile.name}</strong>
          </small>
        ) : null}
        {csvSubmitting ? (
          <div
            style={{
              border: "1px solid rgba(255,255,255,0.08)",
              background:
                csvSubmitPhase === "importing_scenario"
                  ? "linear-gradient(135deg, rgba(59,130,246,0.14), rgba(15,23,42,0.22))"
                  : "linear-gradient(135deg, rgba(16,185,129,0.14), rgba(15,23,42,0.22))",
              borderRadius: 12,
              padding: 12,
              display: "grid",
              gap: 8,
            }}
          >
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <span
                aria-hidden="true"
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 999,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: "rgba(255,255,255,0.08)",
                  fontSize: 16,
                  fontWeight: 700,
                }}
              >
                {csvSpinnerFrame}
              </span>
              <div style={{ display: "grid", gap: 2 }}>
                <strong>{csvCurrentPhaseLabel}...</strong>
                <small style={{ opacity: 0.78 }}>
                  {csvSubmitPhase === "importing_scenario"
                    ? "El backend está guardando los insumos del ZIP antes de encolar la simulación."
                    : "El backend está validando el ZIP y preparando la corrida."}
                </small>
              </div>
            </div>
            <div
              style={{
                display: "grid",
                gap: 6,
                gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
              }}
            >
              <div
                style={{
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                  padding: "8px 10px",
                  background: "rgba(255,255,255,0.04)",
                }}
              >
                <small style={{ display: "block", opacity: 0.7 }}>Tiempo transcurrido</small>
                <strong>{formatReadableDuration(csvSubmitElapsedSeconds)}</strong>
              </div>
              <div
                style={{
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                  padding: "8px 10px",
                  background: "rgba(255,255,255,0.04)",
                }}
              >
                <small style={{ display: "block", opacity: 0.7 }}>Tiempo estimado</small>
                <strong>{csvEstimatedDurationLabel}</strong>
              </div>
            </div>
            <small style={{ opacity: 0.72 }}>
              {csvSubmitPhase === "importing_scenario"
                ? "Si el ZIP es grande, esta fase puede tardar más de lo normal. No cierres la página."
                : "La respuesta debería llegar pronto con el identificador del job."}
            </small>
          </div>
        ) : null}
        {csvResult ? (
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button variant="ghost" onClick={() => setCsvResultOpen(true)}>
              Ver últimos resultados
            </Button>
          </div>
        ) : null}
        {csvTrackedJobId ? (
          <small style={{ opacity: 0.78 }}>
            Job CSV en seguimiento: <strong>#{csvTrackedJobId}</strong>. Se abrirá automáticamente cuando termine.
          </small>
        ) : null}
      </article>
      ) : null}

      {simulationTab === "osemosys" && selectedScenario && udcConfig ? (
        <article className="pageSection" style={{ display: "grid", gap: 10 }}>
          <div
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
            onClick={() => setUdcOpen(!udcOpen)}
          >
            <h2 style={{ margin: 0 }}>
              Configuración UDC (Restricciones definidas por usuario)
              <span style={{ marginLeft: 10, fontSize: 13, fontWeight: 400, color: udcConfig.enabled ? "#4ade80" : "#9ca3af" }}>
                {udcConfig.enabled ? "● activo" : "● inactivo"}
              </span>
            </h2>
            <span style={{ fontSize: 18 }}>{udcOpen ? "▲" : "▼"}</span>
          </div>

          {udcOpen ? (
            <div style={{ display: "grid", gap: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", userSelect: "none" }}>
                <input
                  type="checkbox"
                  checked={udcConfig.enabled}
                  onChange={(e) => {
                    const enabled = e.target.checked;
                    setUdcConfig({
                      ...udcConfig,
                      enabled,
                      multipliers: enabled && udcConfig.multipliers.length === 0
                        ? [{ type: "TotalCapacity" as const, tech_dict: {} }]
                        : udcConfig.multipliers,
                    });
                  }}
                />
                Habilitar UDC en esta simulación
              </label>

              {udcConfig.enabled && (
              <div style={{ display: "flex", gap: 16, alignItems: "end", flexWrap: "wrap" }}>
                <label className="field" style={{ margin: 0, width: 200 }}>
                  <span className="field__label">Tipo de restricción (UDCTag)</span>
                  <select
                    className="field__input"
                    value={udcConfig.tag_value}
                    onChange={(e) =>
                      setUdcConfig({ ...udcConfig, tag_value: Number(e.target.value) as 0 | 1 })
                    }
                  >
                    <option value={0}>0 — Desigualdad (≤)</option>
                    <option value={1}>1 — Igualdad (=)</option>
                  </select>
                </label>
              </div>
              )}

              {udcConfig.enabled && udcConfig.multipliers.map((mult, mIdx) => (
                <div key={mIdx} style={{ border: "1px solid rgba(255,255,255,0.15)", borderRadius: 8, padding: 12, display: "grid", gap: 8 }}>
                  <div style={{ display: "flex", gap: 12, alignItems: "end" }}>
                    <label className="field" style={{ margin: 0, width: 220 }}>
                      <span className="field__label">Tipo de multiplicador</span>
                      <select
                        className="field__input"
                        value={mult.type}
                        onChange={(e) => {
                          const updated = [...udcConfig.multipliers];
                          updated[mIdx] = { ...mult, type: e.target.value as UdcMultiplierEntry["type"] };
                          setUdcConfig({ ...udcConfig, multipliers: updated });
                        }}
                      >
                        <option value="TotalCapacity">TotalCapacity</option>
                        <option value="NewCapacity">NewCapacity</option>
                        <option value="Activity">Activity</option>
                      </select>
                    </label>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        const updated = udcConfig.multipliers.filter((_, i) => i !== mIdx);
                        setUdcConfig({ ...udcConfig, multipliers: updated });
                      }}
                    >
                      Eliminar multiplicador
                    </Button>
                  </div>

                  <div style={{ maxHeight: 300, overflow: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid rgba(255,255,255,0.2)" }}>Tecnología</th>
                          <th style={{ textAlign: "right", padding: "4px 8px", borderBottom: "1px solid rgba(255,255,255,0.2)" }}>Valor</th>
                          <th style={{ width: 40 }}></th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(mult.tech_dict).map(([tech, val]) => (
                          <tr key={tech}>
                            <td style={{ padding: "2px 8px" }}>{tech}</td>
                            <td style={{ padding: "2px 8px", textAlign: "right" }}>
                              <input
                                type="number"
                                step="any"
                                style={{ width: 100, textAlign: "right" }}
                                value={val}
                                onChange={(e) => {
                                  const updated = [...udcConfig.multipliers];
                                  updated[mIdx] = {
                                    ...mult,
                                    tech_dict: { ...mult.tech_dict, [tech]: Number(e.target.value) },
                                  };
                                  setUdcConfig({ ...udcConfig, multipliers: updated });
                                }}
                              />
                            </td>
                            <td>
                              <button
                                type="button"
                                style={{ cursor: "pointer", border: "none", background: "none", color: "rgba(248,113,113,0.9)" }}
                                onClick={() => {
                                  const rest = { ...mult.tech_dict };
                                  delete rest[tech];
                                  const updated = [...udcConfig.multipliers];
                                  updated[mIdx] = { ...mult, tech_dict: rest };
                                  setUdcConfig({ ...udcConfig, multipliers: updated });
                                }}
                              >
                                ✕
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div style={{ display: "flex", gap: 8, alignItems: "end" }}>
                    <label className="field" style={{ margin: 0, flex: 1 }}>
                      <span className="field__label">Agregar tecnología</span>
                      <input
                        className="field__input"
                        placeholder="Ej: PWRNUC"
                        value={udcNewTech}
                        onChange={(e) => setUdcNewTech(e.target.value)}
                      />
                    </label>
                    <label className="field" style={{ margin: 0, width: 120 }}>
                      <span className="field__label">Valor</span>
                      <input
                        className="field__input"
                        type="number"
                        step="any"
                        value={udcNewValue}
                        onChange={(e) => setUdcNewValue(e.target.value)}
                      />
                    </label>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        if (!udcNewTech.trim()) return;
                        const updated = [...udcConfig.multipliers];
                        updated[mIdx] = {
                          ...mult,
                          tech_dict: { ...mult.tech_dict, [udcNewTech.trim()]: Number(udcNewValue) },
                        };
                        setUdcConfig({ ...udcConfig, multipliers: updated });
                        setUdcNewTech("");
                        setUdcNewValue("0");
                      }}
                    >
                      Agregar
                    </Button>
                  </div>
                </div>
              ))}

              <div style={{ display: "flex", gap: 8 }}>
                {udcConfig.enabled && (
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setUdcConfig({
                        ...udcConfig,
                        multipliers: [
                          ...udcConfig.multipliers,
                          { type: "TotalCapacity", tech_dict: {} },
                        ],
                      })
                    }
                  >
                    + Agregar multiplicador
                  </Button>
                )}
                <Button variant="primary" onClick={saveUdcConfig} disabled={udcSaving}>
                  {udcSaving ? "Guardando..." : "Guardar configuración UDC"}
                </Button>
              </div>
            </div>
          ) : null}
        </article>
      ) : null}

      <article className="pageSection" style={{ display: "grid", gap: 10 }}>
        <h2 style={{ margin: 0 }}>Resumen operativo</h2>
        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
          {[
            { label: "En cola", value: overview?.queued_count ?? 0 },
            { label: "Ejecutando", value: overview?.running_count ?? 0 },
            { label: "Activas", value: overview?.active_count ?? 0 },
            { label: "Total visibles", value: overview?.total_count ?? runs.length },
            { label: "RAM total", value: formatBytes(overview?.services_memory_total_bytes ?? 0) },
          ].map((item) => (
            <div key={item.label} style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, padding: 14 }}>
              <div style={{ fontSize: 12, opacity: 0.7 }}>{item.label}</div>
              <div style={{ fontSize: 24, fontWeight: 700 }}>{item.value}</div>
            </div>
          ))}
        </div>
      </article>

      <article className="pageSection" style={{ display: "grid", gap: 10 }}>
        <div className="toolbarRow">
          <h2 style={{ margin: 0 }}>Cola global y ejecuciones</h2>
        </div>
        {loadingRuns ? (
          <div style={{ display: "grid", gap: 8 }}>
            <div className="skeletonLine" />
            <div className="skeletonLine" />
            <div className="skeletonLine" />
          </div>
        ) : null}
        {!loadingRuns && errorRuns ? (
          <div style={{ border: "1px solid rgba(239,68,68,0.4)", borderRadius: 12, padding: 12 }}>
            <strong>Error cargando jobs</strong>
            <p style={{ marginBottom: 0 }}>{errorRuns}</p>
          </div>
        ) : null}
        {!loadingRuns && !errorRuns && runs.length === 0 ? (
          <div style={{ border: "1px dashed rgba(255,255,255,0.2)", borderRadius: 12, padding: 12 }}>
            No hay jobs para el filtro seleccionado.
          </div>
        ) : null}
        <DataTable
          rows={runs}
          rowKey={(r) => String(r.id)}
          columns={[
            {
              key: "display_name",
              header: "Nombre del resultado",
              render: (r) => (
                <RunDisplayNameEditor
                  jobId={r.id}
                  value={r.display_name ?? null}
                  onSaved={handleRunDisplayNameSaved}
                  compact
                />
              ),
              filter: {
                type: "text",
                getValue: (r) => r.display_name ?? "",
                placeholder: "Nombre…",
              },
            },
            {
              key: "scenario",
              header: "Escenario",
              render: (r) =>
                r.scenario_name ??
                (r.input_mode === "CSV_UPLOAD"
                  ? r.input_name ?? "CSV upload"
                  : r.scenario_id === null
                    ? "—"
                    : `#${r.scenario_id}`),
              filter: {
                type: "multiselect",
                getValue: (r) =>
                  r.scenario_name ??
                  (r.input_mode === "CSV_UPLOAD"
                    ? r.input_name ?? "CSV upload"
                    : r.scenario_id === null
                      ? "—"
                      : `#${r.scenario_id}`),
                placeholder: "Escenario…",
              },
            },
            {
              key: "id",
              header: "ID ejecución",
              render: (r) => <span style={{ fontFamily: "monospace", opacity: 0.75 }}>{r.id}</span>,
              filter: {
                type: "text",
                getValue: (r) => String(r.id),
                placeholder: "#id",
              },
            },
            {
              key: "scenario_tag",
              header: "Etiquetas",
              render: (r) => {
                const tags =
                  r.scenario_tags && r.scenario_tags.length > 0
                    ? r.scenario_tags
                    : r.scenario_tag
                    ? [r.scenario_tag]
                    : [];
                if (tags.length === 0) {
                  return <span style={{ opacity: 0.65 }}>—</span>;
                }
                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {tags.map((t) => (
                      <ScenarioTagChip key={t.id} tag={t} size="sm" />
                    ))}
                  </div>
                );
              },
              filter: {
                type: "multiselect",
                getValue: (r) => {
                  const tags =
                    r.scenario_tags && r.scenario_tags.length > 0
                      ? r.scenario_tags
                      : r.scenario_tag
                      ? [r.scenario_tag]
                      : [];
                  return tags.length ? tags.map((t) => t.name).join(", ") : "—";
                },
                placeholder: "Etiquetas…",
              },
            },
            {
              key: "user",
              header: "Usuario",
              render: (r) => r.username ?? r.user_id,
              filter: {
                type: "multiselect",
                getValue: (r) => r.username ?? String(r.user_id ?? "—"),
                placeholder: "Usuario…",
              },
            },
            {
              key: "solver",
              header: "Solver",
              render: (r) => {
                const label = getSolverLabel(r.solver_name);
                const threads = r.solver_threads_used;
                return threads != null && threads > 0
                  ? `${label} (${threads}h)`
                  : label;
              },
              filter: {
                type: "multiselect",
                getValue: (r) => getSolverLabel(r.solver_name),
                options: [
                  { value: "HiGHS", label: "HiGHS" },
                  { value: "GLPK", label: "GLPK" },
                  { value: "Gurobi", label: "Gurobi" },
                ],
              },
            },
            {
              key: "status",
              header: "Estado",
              render: (r) => {
                const { variant, label } = getSimulationRunStatusDisplay(r);
                return <Badge variant={variant}>{label}</Badge>;
              },
              filter: {
                type: "multiselect",
                getValue: (r) => r.status,
                getLabel: (v) =>
                  ({
                    QUEUED: "En cola",
                    RUNNING: "En ejecución",
                    SUCCEEDED: "Exitosa",
                    FAILED: "Fallida",
                    CANCELLED: "Cancelada",
                  })[v] ?? v,
                options: [
                  { value: "QUEUED", label: "En cola" },
                  { value: "RUNNING", label: "En ejecución" },
                  { value: "SUCCEEDED", label: "Exitosa" },
                  { value: "FAILED", label: "Fallida" },
                  { value: "CANCELLED", label: "Cancelada" },
                ],
              },
            },
            {
              key: "visibility",
              header: "Visibilidad",
              render: (r) => (
                <VisibilityToggle
                  jobId={r.id}
                  isPublic={r.is_public ?? true}
                  canEdit={ownedSet.has(r.id)}
                  onChanged={(next) => handleVisibilityChanged(r.id, next)}
                  compact
                />
              ),
              filter: {
                type: "multiselect",
                getValue: (r) => ((r.is_public ?? true) ? "public" : "private"),
                options: [
                  { value: "public", label: "Público" },
                  { value: "private", label: "Privado" },
                ],
              },
            },
            { key: "progress", header: "Progreso", render: (r) => `${r.progress}%` },
            {
              key: "queue",
              header: "Cola",
              render: (r) => (r.queue_position ?? "—"),
            },
            {
              key: "timing",
              header: "Tiempo",
              render: (r) => {
                // Si está corriendo (sin finished_at) usamos liveTickMs para
                // que el cronómetro avance.
                const isRunning = r.status === "RUNNING" && !!r.started_at && !r.finished_at;
                return (
                  <RunTimingCell
                    startedAt={r.started_at ?? null}
                    finishedAt={r.finished_at ?? null}
                    queuedAt={r.queued_at}
                    liveTickMs={isRunning ? liveTickMs : undefined}
                    onClick={() => void loadLogs(r.id)}
                    title="Ver registros (logs) de la ejecución"
                  />
                );
              },
            },
            {
              key: "actions",
              header: "Acciones",
              render: (r) => {
                const isInfeasible = !!r.is_infeasible_result;
                const solver = (r.solver_name ?? "").toLowerCase();
                const diagStatus = r.diagnostic_status ?? "NONE";
                const busy = triggeringDiagnosticFor === r.id;
                const diagCancelBusy = cancellingDiagnosticFor === r.id;
                const cancelBusy = cancellingJobId === r.id;
                const iconBtn =
                  "inline-flex h-8 w-8 items-center justify-center rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
                const sch = {
                  primary:
                    "border-slate-700 text-slate-300 hover:border-cyan-500/50 hover:bg-cyan-500/10 hover:text-cyan-300",
                  neutral:
                    "border-slate-700 text-slate-300 hover:border-slate-400/60 hover:bg-slate-500/10 hover:text-slate-100",
                  danger:
                    "border-rose-900/60 text-rose-300 hover:border-rose-500/60 hover:bg-rose-500/10 hover:text-rose-200",
                  warning:
                    "border-amber-900/60 text-amber-300 hover:border-amber-500/60 hover:bg-amber-500/10 hover:text-amber-200",
                  warningActive:
                    "border-amber-500/60 bg-amber-500/15 text-amber-200",
                  mutedInfo:
                    "border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-300 cursor-help",
                } as const;
                const svg = (children: ReactNode) => (
                  <svg
                    width={16}
                    height={16}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    {children}
                  </svg>
                );
                const icons = {
                  chart: svg(
                    <>
                      <path d="M3 3v18h18" />
                      <path d="M7 17V9" />
                      <path d="M12 17V5" />
                      <path d="M17 17v-7" />
                    </>,
                  ),
                  logs: svg(
                    <>
                      <polyline points="4 17 10 11 4 5" />
                      <line x1="12" y1="19" x2="20" y2="19" />
                    </>,
                  ),
                  alert: svg(
                    <>
                      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                      <line x1="12" y1="9" x2="12" y2="13" />
                      <line x1="12" y1="17" x2="12.01" y2="17" />
                    </>,
                  ),
                  infeasDoc: svg(
                    <>
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <path d="M14 2v6h6" />
                      <line x1="12" y1="12" x2="12" y2="15" />
                      <line x1="12" y1="18" x2="12.01" y2="18" />
                    </>,
                  ),
                  clock: svg(
                    <>
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </>,
                  ),
                  spinner: svg(
                    <>
                      <line x1="12" y1="2" x2="12" y2="6" />
                      <line x1="12" y1="18" x2="12" y2="22" />
                      <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
                      <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
                      <line x1="2" y1="12" x2="6" y2="12" />
                      <line x1="18" y1="12" x2="22" y2="12" />
                      <line x1="4.93" y1="19.07" x2="7.76" y2="16.24" />
                      <line x1="16.24" y1="7.76" x2="19.07" y2="4.93" />
                    </>,
                  ),
                  diagnose: svg(
                    <>
                      <circle cx="11" cy="11" r="7" />
                      <line x1="21" y1="21" x2="16.65" y2="16.65" />
                      <line x1="11" y1="8" x2="11" y2="11" />
                      <line x1="11" y1="13" x2="11.01" y2="13" />
                    </>,
                  ),
                  info: svg(
                    <>
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="16" x2="12" y2="12" />
                      <line x1="12" y1="8" x2="12.01" y2="8" />
                    </>,
                  ),
                  x: svg(
                    <>
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </>,
                  ),
                  trash: svg(
                    <>
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                      <path d="M10 11v6" />
                      <path d="M14 11v6" />
                      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                    </>,
                  ),
                  download: svg(
                    <>
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </>,
                  ),
                } as const;

                const runningSeconds =
                  diagStatus === "RUNNING" && r.diagnostic_started_at
                    ? Math.max(
                        0,
                        Math.floor(
                          (liveTickMs -
                            new Date(r.diagnostic_started_at).getTime()) /
                            1000,
                        ),
                      )
                    : null;

                const buttons: ReactNode[] = [];

                // Abrir resultados: solo para simulaciones exitosas y factibles
                // (las QUEUED / RUNNING / FAILED / CANCELLED / infactibles no
                // tienen output numérico que graficar).
                if (r.status === "SUCCEEDED" && !isInfeasible) {
                  buttons.push(
                    <Link
                      key="open"
                      to={paths.resultsDetail(r.id)}
                      className={`${iconBtn} ${sch.primary}`}
                      title="Abrir resultados (gráficas)"
                      aria-label="Abrir resultados"
                    >
                      {icons.chart}
                    </Link>,
                  );
                }

                // Registros / logs (siempre disponible)
                buttons.push(
                  <button
                    key="logs"
                    type="button"
                    onClick={() => void loadLogs(r.id)}
                    className={`${iconBtn} ${sch.neutral}`}
                    title="Ver registros (logs) del job"
                    aria-label="Ver registros"
                  >
                    {icons.logs}
                  </button>,
                );

                // Descargar .lp del modelo si el job lo persistió.
                if (r.has_lp_file) {
                  buttons.push(
                    <button
                      key="download-lp"
                      type="button"
                      onClick={() => void downloadLpForJob(r.id)}
                      className={`${iconBtn} ${sch.neutral}`}
                      title="Descargar archivo .lp del modelo Pyomo"
                      aria-label="Descargar .lp"
                    >
                      {icons.download}
                    </button>,
                  );
                }

                // Error (si hay mensaje persistido)
                if (r.error_message) {
                  buttons.push(
                    <span
                      key="error"
                      role="img"
                      className={`${iconBtn} ${sch.danger} cursor-help`}
                      title={`Error: ${r.error_message}`}
                      aria-label={`Error: ${r.error_message}`}
                    >
                      {icons.alert}
                    </span>,
                  );
                }

                // Infactible + HiGHS / Gurobi / GLPK: flujo del diagnóstico
                if (
                  isInfeasible &&
                  (solver === "highs" || solver === "gurobi" || solver === "glpk")
                ) {
                  if (diagStatus === "SUCCEEDED") {
                    const secs =
                      typeof r.diagnostic_seconds === "number"
                        ? ` — ${r.diagnostic_seconds.toFixed(1)} s`
                        : "";
                    buttons.push(
                      <Link
                        key="diag-view"
                        to={paths.infeasibilityReport(r.id)}
                        className={`${iconBtn} ${sch.warning}`}
                        title={`Ver reporte de infactibilidad (IIS + mapeo a parámetros)${secs}`}
                        aria-label="Ver reporte de infactibilidad"
                      >
                        {icons.infeasDoc}
                      </Link>,
                    );
                  } else if (diagStatus === "QUEUED") {
                    buttons.push(
                      <span
                        key="diag-queued"
                        role="img"
                        className={`${iconBtn} ${sch.neutral} cursor-help`}
                        title="Diagnóstico de infactibilidad en cola — aún no inició."
                        aria-label="Diagnóstico en cola"
                      >
                        {icons.clock}
                      </span>,
                    );
                    buttons.push(
                      <button
                        key="diag-cancel"
                        type="button"
                        onClick={() => void cancelDiagnostic(r.id)}
                        disabled={diagCancelBusy}
                        className={`${iconBtn} ${sch.danger}`}
                        title={
                          diagCancelBusy
                            ? "Cancelando diagnóstico…"
                            : "Cancelar diagnóstico"
                        }
                        aria-label="Cancelar diagnóstico"
                      >
                        {icons.x}
                      </button>,
                    );
                  } else if (diagStatus === "RUNNING") {
                    buttons.push(
                      <span
                        key="diag-running"
                        role="img"
                        className={`${iconBtn} ${sch.warningActive} animate-spin [animation-duration:2s] cursor-help`}
                        title={
                          runningSeconds != null
                            ? `Ejecutando diagnóstico de infactibilidad — ${runningSeconds} s`
                            : "Ejecutando diagnóstico de infactibilidad"
                        }
                        aria-label="Ejecutando diagnóstico"
                      >
                        {icons.spinner}
                      </span>,
                    );
                    buttons.push(
                      <button
                        key="diag-cancel"
                        type="button"
                        onClick={() => void cancelDiagnostic(r.id)}
                        disabled={diagCancelBusy}
                        className={`${iconBtn} ${sch.danger}`}
                        title={
                          diagCancelBusy
                            ? "Cancelando diagnóstico…"
                            : "Cancelar diagnóstico en curso"
                        }
                        aria-label="Cancelar diagnóstico"
                      >
                        {icons.x}
                      </button>,
                    );
                  } else if (diagStatus === "NONE" || diagStatus === "FAILED") {
                    const titleText = busy
                      ? "Encolando diagnóstico…"
                      : diagStatus === "FAILED" && r.diagnostic_error
                        ? `Reintentar diagnóstico — último intento falló: ${r.diagnostic_error}`
                        : solver === "glpk"
                          ? "Correr diagnóstico de infactibilidad (GLPK --nopresol · puede tardar varios minutos en modelos grandes)"
                          : "Correr diagnóstico de infactibilidad (IIS + mapeo a parámetros)";
                    buttons.push(
                      <button
                        key="diag-run"
                        type="button"
                        onClick={() => void requestDiagnostic(r.id)}
                        disabled={busy}
                        className={`${iconBtn} ${sch.warning}`}
                        title={titleText}
                        aria-label={
                          diagStatus === "FAILED"
                            ? "Reintentar diagnóstico"
                            : "Correr diagnóstico"
                        }
                      >
                        {icons.diagnose}
                      </button>,
                    );
                  }
                }

                // Infactible + solver no soportado (ni highs/gurobi/glpk)
                if (
                  isInfeasible &&
                  solver !== "highs" &&
                  solver !== "gurobi" &&
                  solver !== "glpk"
                ) {
                  buttons.push(
                    <span
                      key="diag-unsupported"
                      role="img"
                      className={`${iconBtn} ${sch.mutedInfo}`}
                      title="Este solver no expone IIS. Para diagnóstico detallado, vuelve a correr la simulación con HiGHS, Gurobi o GLPK."
                      aria-label="Diagnóstico no disponible con este solver"
                    >
                      {icons.info}
                    </span>,
                  );
                }

                // Cancelar simulación activa (QUEUED/RUNNING)
                if (ACTIVE_STATUSES.has(r.status)) {
                  buttons.push(
                    <button
                      key="cancel-sim"
                      type="button"
                      onClick={() => void cancelSimulation(r.id)}
                      disabled={cancelBusy}
                      className={`${iconBtn} ${sch.danger}`}
                      title={
                        cancelBusy
                          ? "Cancelando simulación…"
                          : "Cancelar simulación"
                      }
                      aria-label="Cancelar simulación"
                    >
                      {icons.x}
                    </button>,
                  );
                }

                // Eliminar job (dueño o admin, solo si no está activo).
                // Eliminación permanente — queda registro en el Historial.
                const canDeleteJob =
                  ownedSet.has(r.id) || Boolean(user?.can_manage_scenarios);
                if (!ACTIVE_STATUSES.has(r.status) && canDeleteJob) {
                  const deleteBusy = deletingJobId === r.id;
                  const isOwner = ownedSet.has(r.id);
                  buttons.push(
                    <button
                      key="delete-job"
                      type="button"
                      onClick={() => setDeleteCandidateJob(r)}
                      disabled={deleteBusy}
                      className={`${iconBtn} ${sch.danger}`}
                      title={
                        deleteBusy
                          ? "Eliminando simulación…"
                          : isOwner
                            ? "Eliminar simulación permanentemente"
                            : "Eliminar como administrador (no eres dueño)"
                      }
                      aria-label="Eliminar simulación"
                    >
                      {icons.trash}
                    </button>,
                  );
                }

                return (
                  <div className="flex items-center gap-1.5 flex-nowrap">
                    {buttons}
                  </div>
                );
              },
            },
          ]}
          searchableText={(r) =>
            `${r.id} ${r.display_name ?? ""} ${r.scenario_name ?? ""} ${r.input_name ?? ""} ${r.username ?? ""} ${r.status} ${r.queue_position ?? ""}`
          }
        />
      </article>

      <Modal
        open={csvResultOpen && csvResult !== null}
        title="Resultados de simulación desde CSV"
        onClose={() => setCsvResultOpen(false)}
        wide
        footer={
          csvResult ? (
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" }}>
              <Button variant="ghost" onClick={downloadCsvResultJson}>
                Descargar JSON completo
              </Button>
              <Button variant="primary" onClick={() => setCsvResultOpen(false)}>
                Cerrar
              </Button>
            </div>
          ) : undefined
        }
      >
        {csvResult ? (
          <div style={{ display: "grid", gap: 16 }}>
            <div
              style={{
                display: "flex",
                gap: 10,
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
              }}
            >
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <Badge variant={getSolverStatusVariant(csvResult.solver_status)}>{csvResult.solver_status}</Badge>
                <span>Solver: {getSolverLabel(csvResult.solver_name)}</span>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gap: 10,
                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              }}
            >
              <CsvMetricCard
                label="Estado del solver"
                value={csvResult.solver_status}
                tone={
                  getSolverStatusVariant(csvResult.solver_status) === "danger"
                    ? "danger"
                    : getSolverStatusVariant(csvResult.solver_status) === "success"
                      ? "success"
                      : "default"
                }
              />
              <CsvMetricCard label="Valor objetivo" value={csvResult.objective_value.toLocaleString()} />
              <CsvMetricCard label="Cobertura" value={`${(csvResult.coverage_ratio * 100).toFixed(2)}%`} />
              <CsvMetricCard label="Demanda total" value={csvResult.total_demand.toLocaleString()} />
              <CsvMetricCard label="Unmet total" value={csvResult.total_unmet.toLocaleString()} />
            </div>

            <div style={{ display: "grid", gap: 12 }}>
              <CsvResultTableSection
                key={`csv-dispatch-${csvResult.dispatch.length}`}
                title="Dispatch"
                rows={csvResult.dispatch}
                preferredColumns={["region", "region_id", "year", "technology_name", "technology_id", "fuel_name", "dispatch", "cost"]}
                emptyMessage="No se generaron filas de dispatch."
                defaultOpen
              />
              <CsvResultTableSection
                key={`csv-newcap-${csvResult.new_capacity.length}`}
                title="New Capacity"
                rows={csvResult.new_capacity}
                preferredColumns={["region", "region_id", "year", "technology_name", "technology_id", "new_capacity"]}
                emptyMessage="No se generaron filas de nueva capacidad."
              />
              <CsvResultTableSection
                key={`csv-unmet-${csvResult.unmet_demand.length}`}
                title="Unmet Demand"
                rows={csvResult.unmet_demand}
                preferredColumns={["region", "region_id", "year", "unmet_demand"]}
                emptyMessage="No se registró demanda no atendida."
              />
              <CsvResultTableSection
                key={`csv-emissions-${csvResult.annual_emissions.length}`}
                title="Annual Emissions"
                rows={csvResult.annual_emissions}
                preferredColumns={["region", "region_id", "year", "emission_name", "annual_emissions"]}
                emptyMessage="No se generaron emisiones anuales."
              />
            </div>

            {csvResult.infeasibility_diagnostics ? (
              <div
                style={{
                  border: "1px solid rgba(220, 38, 38, 0.4)",
                  borderRadius: 12,
                  padding: 14,
                  display: "grid",
                  gap: 8,
                  background: "rgba(127, 29, 29, 0.12)",
                }}
              >
                <strong>Modelo infactible detectado</strong>
                <small style={{ opacity: 0.82 }}>
                  El reporte completo (IIS, parámetros sospechosos con desviación vs default,
                  historial de cambios del escenario, descarga JSON) vive en una página
                  dedicada.
                </small>
                {csvResultSourceJobId ? (
                  <Link
                    to={paths.infeasibilityReport(csvResultSourceJobId)}
                    className="btn btn--ghost"
                    style={{ justifySelf: "start", color: "rgba(248,113,113,0.95)" }}
                  >
                    ⚠ Ver reporte de infactibilidad del job #{csvResultSourceJobId}
                  </Link>
                ) : (
                  <small style={{ opacity: 0.75 }}>
                    (Este resultado no está asociado a un job persistido; descarga el JSON
                    para revisarlo.)
                  </small>
                )}
              </div>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <Modal
        open={logsOpenForJob !== null}
        title={logsOpenForJob ? `Registros de la ejecución ${logsOpenForJob}` : "Registros"}
        onClose={() => setLogsOpenForJob(null)}
      >
        {loadingLogs ? (
          <div style={{ display: "grid", gap: 8 }}>
            <div className="skeletonLine" />
            <div className="skeletonLine" />
            <div className="skeletonLine" />
          </div>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {selectedLogs.length ? (
              <>
                {logsBanner ? (
                  <div
                    style={{
                      display: "grid",
                      gap: 10,
                      padding: 12,
                      borderRadius: 14,
                      border: logsBanner.infeasAnalysisRunning
                        ? "1px solid rgba(245,158,11,0.5)"
                        : "1px solid rgba(148,163,184,0.25)",
                      background: logsBanner.infeasAnalysisRunning
                        ? "linear-gradient(180deg, rgba(120,53,15,0.22), rgba(15,23,42,0.3))"
                        : "linear-gradient(180deg, rgba(71,85,105,0.18), rgba(15,23,42,0.25))",
                    }}
                  >
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "baseline" }}>
                      <div>
                        <div style={{ fontSize: 12, opacity: 0.7 }}>Tiempo total</div>
                        <div style={{ fontSize: 22, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
                          {formatReadableDuration(logsBanner.totalSeconds)}
                          {selectedLogsJobActive ? (
                            <span style={{ fontSize: 12, marginLeft: 8, opacity: 0.75 }}>(en curso)</span>
                          ) : null}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 12, opacity: 0.7 }}>Etapa actual</div>
                        <div style={{ fontSize: 18, fontWeight: 700 }}>
                          {formatSimulationLogStage(logsBanner.currentStageName)}
                        </div>
                        <div style={{ fontSize: 13, opacity: 0.8, fontVariantNumeric: "tabular-nums" }}>
                          {formatReadableDuration(logsBanner.currentStageSeconds)}
                          {selectedLogsJobActive ? " desde su inicio" : ""}
                        </div>
                      </div>
                      <div style={{ marginLeft: "auto", fontSize: 12, opacity: 0.7, textAlign: "right" }}>
                        Primer evento: {logsBanner.firstAt.toLocaleTimeString()}
                        <br />
                        Último evento: {logsBanner.lastAt.toLocaleTimeString()}
                      </div>
                    </div>

                    {logsBanner.infeasAnalysisRunning ? (
                      <div
                        style={{
                          display: "grid",
                          gap: 4,
                          padding: 10,
                          borderRadius: 10,
                          border: "1px solid rgba(245,158,11,0.45)",
                          background: "rgba(120,53,15,0.28)",
                        }}
                      >
                        <strong style={{ fontSize: 14 }}>
                          ⚙️ Analizando infactibilidad…
                        </strong>
                        <span style={{ fontSize: 13, opacity: 0.9 }}>
                          El modelo salió infactible. Se está corriendo el IIS y mapeando
                          las restricciones a los parámetros OSeMOSYS de entrada. Esto puede
                          tardar varios segundos sobre modelos grandes.
                        </span>
                        {logsBanner.infeasStartedAt ? (
                          <span style={{ fontSize: 12, opacity: 0.85, fontVariantNumeric: "tabular-nums" }}>
                            Inició a las {logsBanner.infeasStartedAt.toLocaleTimeString()} ·
                            llevan {formatReadableDuration(logsBanner.infeasElapsedSeconds ?? 0)}
                          </span>
                        ) : null}
                      </div>
                    ) : logsBanner.infeasStartedAt && logsBanner.infeasElapsedSeconds !== null ? (
                      <div style={{ fontSize: 12, opacity: 0.8 }}>
                        Análisis de infactibilidad ejecutado: inició a las{" "}
                        {logsBanner.infeasStartedAt.toLocaleTimeString()} · duró{" "}
                        {formatReadableDuration(logsBanner.infeasElapsedSeconds)}.
                      </div>
                    ) : null}
                  </div>
                ) : null}

                <div
                  style={{
                    display: "grid",
                    gap: 10,
                    padding: 12,
                    borderRadius: 14,
                    border: "1px solid rgba(96,165,250,0.22)",
                    background: "linear-gradient(180deg, rgba(37,99,235,0.12), rgba(15,23,42,0.28))",
                  }}
                >
                  <div
                    style={{
                      display: "grid",
                      gap: 10,
                      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                    }}
                  >
                    {selectedLogs
                      .map((log, index) => ({
                        log,
                        durationSeconds: getSimulationLogDurationSeconds(log, selectedLogs[index + 1]),
                      }))
                      .filter(({ log }) => isCriticalSimulationLogStage(log.stage))
                      .map(({ log, durationSeconds }) => (
                        <article
                          key={`critical-${log.id}`}
                          style={{
                            display: "grid",
                            gap: 6,
                            padding: 12,
                            borderRadius: 12,
                            border: "1px solid rgba(96,165,250,0.24)",
                            background: "rgba(15,23,42,0.56)",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                            <span style={{ fontWeight: 700 }}>{formatSimulationLogStage(log.stage)}</span>
                          </div>
                          <div style={{ fontSize: 24, fontWeight: 800 }}>
                            {durationSeconds !== null ? formatReadableDuration(durationSeconds) : "En curso"}
                          </div>
                          <div style={{ fontSize: 13, opacity: 0.78 }}>
                            {new Date(log.created_at).toLocaleTimeString()}
                            {log.progress !== null ? ` · ${Math.round(log.progress)}%` : ""}
                          </div>
                          <div style={{ lineHeight: 1.45 }}>{log.message ?? "Sin detalle adicional."}</div>
                        </article>
                      ))}
                  </div>
                </div>

                <div style={{ display: "grid", gap: 10, maxHeight: "48vh", overflow: "auto", paddingRight: 4 }}>
                  {selectedLogs.map((log, index) => {
                    const durationSeconds = getSimulationLogDurationSeconds(log, selectedLogs[index + 1]);
                    const isCritical = isCriticalSimulationLogStage(log.stage);

                    return (
                      <article
                        key={log.id}
                        style={{
                          display: "grid",
                          gap: 8,
                          padding: 12,
                          borderRadius: 12,
                          border: isCritical ? "1px solid rgba(96,165,250,0.26)" : "1px solid rgba(255,255,255,0.08)",
                          background: isCritical ? "rgba(30,41,59,0.6)" : "rgba(255,255,255,0.03)",
                          boxShadow: isCritical ? "inset 3px 0 0 rgba(96,165,250,0.9)" : "none",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: 8,
                            alignItems: "center",
                          }}
                        >
                          <Badge variant={getSimulationLogVariant(log)}>{formatSimulationLogStage(log.stage)}</Badge>
                          <span style={{ fontSize: 13, opacity: 0.78 }}>{new Date(log.created_at).toLocaleTimeString()}</span>
                          {durationSeconds !== null ? (
                            <span style={{ fontSize: 13, opacity: 0.9, fontWeight: isCritical ? 700 : 500 }}>
                              Duración: {formatReadableDuration(durationSeconds)}
                            </span>
                          ) : null}
                          {log.progress !== null ? (
                            <span style={{ fontSize: 13, opacity: 0.78 }}>Progreso: {Math.round(log.progress)}%</span>
                          ) : null}
                        </div>
                        <div style={{ lineHeight: 1.5 }}>{log.message ?? "Sin detalle adicional."}</div>
                      </article>
                    );
                  })}
                </div>
              </>
            ) : (
              <div style={{ opacity: 0.78 }}>Sin logs disponibles.</div>
            )}
          </div>
        )}
      </Modal>

      <Modal
        open={deleteCandidateJob !== null}
        title="Eliminar simulación"
        onClose={() => (deletingJobId ? undefined : setDeleteCandidateJob(null))}
        footer={
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Button
              variant="ghost"
              onClick={() => setDeleteCandidateJob(null)}
              disabled={deletingJobId !== null}
            >
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={() => void confirmDeleteJob()}
              disabled={deletingJobId !== null}
              style={{
                background: "rgba(239,68,68,0.85)",
                borderColor: "rgba(239,68,68,0.9)",
              }}
            >
              {deletingJobId !== null ? "Eliminando…" : "Eliminar definitivamente"}
            </Button>
          </div>
        }
      >
        {deleteCandidateJob ? (
          <div style={{ display: "grid", gap: 10 }}>
            <p style={{ margin: 0 }}>
              ¿Eliminar la simulación{" "}
              <strong>
                {deleteCandidateJob.display_name ??
                  deleteCandidateJob.scenario_name ??
                  `Job #${deleteCandidateJob.id}`}
              </strong>{" "}
              (#{deleteCandidateJob.id})?
            </p>
            <div
              style={{
                border: "1px solid rgba(245,158,11,0.4)",
                background: "rgba(245,158,11,0.08)",
                borderRadius: 8,
                padding: 10,
                fontSize: 13,
                lineHeight: 1.5,
              }}
            >
              <strong>Esta acción no se puede deshacer.</strong> Se eliminan
              también los logs y resultados numéricos de esta corrida.
              <br />
              Queda un registro en el Historial de eliminaciones (quién, cuándo
              y snapshot de los campos clave).
            </div>
          </div>
        ) : null}
      </Modal>
    </section>
  );
}
