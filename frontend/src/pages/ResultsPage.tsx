/**
 * ResultsPage - Lista de resultados de simulaciones
 *
 * Muestra jobs de simulación con:
 *   - Filtros globales: estado + rango de fechas.
 *   - Filtro por columna (texto / select).
 *   - Favoritos siempre al tope (ordenados por fecha dentro de cada sección).
 *   - Control de visibilidad (público / privado) — solo editable por el dueño.
 *
 * Endpoints usados:
 *   - simulationApi.listRuns({ scope: "global", cantidad: 100 })
 *   - simulationApi.setFavorite / patchVisibility
 *   - scenariosApi.listScenarios() para mapear scenario_id a nombre
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { scenariosApi } from "@/features/scenarios/api/scenariosApi";
import { simulationApi } from "@/features/simulation/api/simulationApi";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { DataTable } from "@/shared/components/DataTable";
import { RunTimingCell } from "@/shared/components/RunTimingCell";
import { ScenarioTagChip } from "@/shared/components/ScenarioTagChip";
import { JobLogsModal } from "@/features/simulation/components/JobLogsModal";
import { RunDisplayNameEditor } from "@/features/simulation/components/RunDisplayNameEditor";
import { FavoriteStarButton } from "@/features/simulation/components/FavoriteStarButton";
import { VisibilityToggle } from "@/features/simulation/components/VisibilityToggle";
import { getSimulationRunStatusDisplay } from "@/features/simulation/simulationRunStatus";
import { paths } from "@/routes/paths";
import { useCurrentUser } from "@/app/providers/useCurrentUser";
import { savedChartsApi } from "@/features/reports/api/savedChartsApi";
import type {
  SavedReport,
  Scenario,
  SimulationRun,
} from "@/types/domain";

export function ResultsPage() {
  const { user } = useCurrentUser();
  const [runs, setRuns] = useState<SimulationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<SimulationRun["status"] | "ALL">("ALL");
  const [activeTab, setActiveTab] = useState<"results" | "infeasibility">("results");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [scenarioMap, setScenarioMap] = useState<Record<number, Scenario>>({});

  /** Run cuya "Ver reporte" se está abriendo (modal de selección de reporte). */
  const [viewReportRun, setViewReportRun] = useState<SimulationRun | null>(null);
  const [reports, setReports] = useState<SavedReport[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);
  const [reportsLoaded, setReportsLoaded] = useState(false);

  /** Job cuyo modal de registros está abierto. */
  const [logsOpenForJob, setLogsOpenForJob] = useState<number | null>(null);

  /** Carga jobs y escenarios en paralelo para tener nombres de escenario */
  const fetchRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [runsRes, scenariosRes] = await Promise.all([
        simulationApi.listRuns({ scope: "global", cantidad: 100, offset: 1 }),
        scenariosApi.listScenarios({ cantidad: 200 }),
      ]);
      setRuns(runsRes.data);
      setScenarioMap(Object.fromEntries(scenariosRes.data.map((s) => [s.id, s])));
    } catch (err: unknown) {
      setRuns([]);
      setError(err instanceof Error ? err.message : "No se pudieron cargar los jobs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchRuns();
  }, [fetchRuns]);

  // Carga perezosa de los reportes guardados — solo la primera vez que abren
  // el modal de "Ver reporte".
  useEffect(() => {
    if (viewReportRun == null || reportsLoaded || loadingReports) return;
    setLoadingReports(true);
    savedChartsApi
      .listReports()
      .then((rows) => {
        setReports(rows);
        setReportsLoaded(true);
      })
      .catch((err) => console.error("Error cargando reportes", err))
      .finally(() => setLoadingReports(false));
  }, [viewReportRun, reportsLoaded, loadingReports]);

  /**
   * Abre el dashboard del reporte pre-cargando `runId` en el slot `slotIdx`
   * (0-based). Se respetan los `default_job_ids` existentes del reporte para
   * rellenar los demás slots.
   */
  const openReportWithRun = useCallback(
    (report: SavedReport, runId: number, slotIdx: number) => {
      const defaults = Array.isArray(report.default_job_ids)
        ? [...report.default_job_ids]
        : [];
      const length = Math.max(defaults.length, slotIdx + 1);
      const slots: (number | null)[] = Array.from(
        { length },
        (_, i) => defaults[i] ?? null,
      );
      slots[slotIdx] = runId;
      window.sessionStorage.setItem(
        `dashboard-prefill-scenarios:${report.id}`,
        JSON.stringify(slots),
      );
      window.location.assign(paths.reportDashboard(report.id));
    },
    [],
  );

  // Filtros globales (estado + rango de fechas), excluyendo infactibles.
  const infeasibleCount = useMemo(
    () => runs.filter((r) => r.is_infeasible_result).length,
    [runs],
  );
  const infeasibleRuns = useMemo(() => {
    return runs
      .filter((run) => {
        if (!run.is_infeasible_result) return false;
        if (statusFilter !== "ALL" && run.status !== statusFilter) return false;
        const created = new Date(run.queued_at).getTime();
        if (fromDate && created < new Date(`${fromDate}T00:00:00`).getTime()) return false;
        if (toDate && created > new Date(`${toDate}T23:59:59`).getTime()) return false;
        return true;
      })
      .sort((a, b) => new Date(b.queued_at).getTime() - new Date(a.queued_at).getTime());
  }, [fromDate, runs, statusFilter, toDate]);

  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      if (run.is_infeasible_result) return false;
      if (statusFilter !== "ALL" && run.status !== statusFilter) return false;
      const created = new Date(run.queued_at).getTime();
      if (fromDate) {
        const from = new Date(`${fromDate}T00:00:00`).getTime();
        if (created < from) return false;
      }
      if (toDate) {
        const to = new Date(`${toDate}T23:59:59`).getTime();
        if (created > to) return false;
      }
      return true;
    });
  }, [fromDate, runs, statusFilter, toDate]);

  // Favoritos primero, luego por fecha descendente.
  const orderedRuns = useMemo(() => {
    const copy = [...filteredRuns];
    copy.sort((a, b) => {
      const af = a.is_favorite ? 0 : 1;
      const bf = b.is_favorite ? 0 : 1;
      if (af !== bf) return af - bf;
      return new Date(b.queued_at).getTime() - new Date(a.queued_at).getTime();
    });
    return copy;
  }, [filteredRuns]);

  const handleRunDisplayNameSaved = useCallback(
    (jobId: number, next: string | null) => {
      setRuns((prev) =>
        prev.map((r) => (r.id === jobId ? { ...r, display_name: next } : r)),
      );
    },
    [],
  );

  const handleFavoriteToggled = useCallback(
    (jobId: number, next: boolean) => {
      setRuns((prev) =>
        prev.map((r) => (r.id === jobId ? { ...r, is_favorite: next } : r)),
      );
    },
    [],
  );

  const handleVisibilityChanged = useCallback(
    (jobId: number, next: boolean) => {
      setRuns((prev) =>
        prev.map((r) => (r.id === jobId ? { ...r, is_public: next } : r)),
      );
    },
    [],
  );

  const currentUserId = user?.id ?? null;

  const ownedSet = useMemo(() => {
    return new Set(
      runs.filter((r) => r.user_id === currentUserId).map((r) => r.id),
    );
  }, [runs, currentUserId]);

  return (
    <section className="pageSection" style={{ display: "grid", gap: 12 }}>
      <div className="toolbarRow">
        <div>
          <h1 style={{ margin: 0 }}>Resultados</h1>
          <p style={{ margin: "6px 0 0", opacity: 0.75 }}>
            Filtra jobs, marca favoritos y abre el detalle. Los favoritos siempre
            aparecen primero. Cada columna admite filtro independiente.
          </p>
        </div>
        <Button variant="ghost" onClick={() => void fetchRuns()} disabled={loading}>
          {loading ? "Cargando..." : "Refrescar"}
        </Button>
      </div>

      <div role="tablist" aria-label="Tipo de resultados" style={{ display: "flex", gap: 8 }}>
        <Button variant={activeTab === "results" ? "primary" : "ghost"} onClick={() => setActiveTab("results")}>
          Resultados factibles
        </Button>
        <Button variant={activeTab === "infeasibility" ? "primary" : "ghost"} onClick={() => setActiveTab("infeasibility")}>
          Reportes de infactibilidad {infeasibleCount ? `(${infeasibleCount})` : ""}
        </Button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))",
          gap: 10,
        }}
      >
        <label className="field">
          <span className="field__label">Estado</span>
          <select
            className="field__input"
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(e.target.value as SimulationRun["status"] | "ALL")
            }
          >
            <option value="ALL">Todos</option>
            <option value="QUEUED">En cola</option>
            <option value="RUNNING">En ejecución</option>
            <option value="SUCCEEDED">Exitosa</option>
            <option value="FAILED">Fallida</option>
            <option value="CANCELLED">Cancelada</option>
          </select>
        </label>
        <label className="field">
          <span className="field__label">Desde</span>
          <input
            className="field__input"
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
        </label>
        <label className="field">
          <span className="field__label">Hasta</span>
          <input
            className="field__input"
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
        </label>
      </div>

      {loading ? (
        <div style={{ display: "grid", gap: 8 }}>
          <div className="skeletonLine" />
          <div className="skeletonLine" />
          <div className="skeletonLine" />
        </div>
      ) : null}
      {!loading && error ? (
        <div style={{ border: "1px solid rgba(239,68,68,0.4)", borderRadius: 12, padding: 12 }}>
          <strong>Error al cargar resultados</strong>
          <p style={{ marginBottom: 0 }}>{error}</p>
        </div>
      ) : null}
      {!loading && !error && orderedRuns.length === 0 ? (
        <div
          style={{
            border: "1px dashed rgba(255,255,255,0.2)",
            borderRadius: 12,
            padding: 12,
          }}
        >
          No hay jobs que coincidan con los filtros.
        </div>
      ) : null}

      {activeTab === "results" ? (
        <>
      <DataTable
        rows={orderedRuns}
        rowKey={(r) => String(r.id)}
        columns={[
          {
            key: "fav",
            header: "★",
            render: (r) => (
              <FavoriteStarButton
                jobId={r.id}
                isFavorite={Boolean(r.is_favorite)}
                onToggled={(next) => handleFavoriteToggled(r.id, next)}
              />
            ),
            filter: {
              type: "multiselect",
              getValue: (r) => (r.is_favorite ? "fav" : "no"),
              options: [
                { value: "fav", label: "★ Solo favoritos" },
                { value: "no", label: "Sin favoritos" },
              ],
            },
          },
          {
            key: "display_name",
            header: "Nombre del resultado",
            render: (r) => (
              <RunDisplayNameEditor
                jobId={r.id}
                value={r.display_name ?? null}
                onSaved={handleRunDisplayNameSaved}
                compact
                linkTo={paths.resultsDetail(r.id)}
              />
            ),
            filter: {
              type: "text",
              getValue: (r) => r.display_name ?? "",
              placeholder: "Buscar nombre…",
            },
          },
          {
            key: "scenario",
            header: "Escenario",
            render: (r) =>
              r.scenario_name ??
              (r.scenario_id === null
                ? (r.input_name ?? "CSV upload")
                : (scenarioMap[r.scenario_id]?.name ?? `#${r.scenario_id}`)),
            filter: {
              type: "multiselect",
              getValue: (r) => {
                const fallback =
                  r.scenario_id === null
                    ? r.input_name ?? ""
                    : scenarioMap[r.scenario_id]?.name ?? "";
                return r.scenario_name ?? fallback ?? "—";
              },
              placeholder: "Escenario…",
            },
          },
          {
            key: "run",
            header: "ID ejecución",
            render: (r) => (
              <span style={{ fontFamily: "monospace", opacity: 0.75 }}>{r.id}</span>
            ),
            filter: {
              type: "text",
              getValue: (r) => String(r.id),
              placeholder: "#id",
            },
          },
          {
            key: "owner",
            header: "Dueño",
            render: (r) => (
              <span style={{ opacity: 0.85 }}>{r.username ?? "—"}</span>
            ),
            filter: {
              type: "multiselect",
              getValue: (r) => r.username ?? "—",
              placeholder: "Usuario…",
            },
          },
          {
            key: "scenario_tag",
            header: "Etiquetas",
            render: (r) => {
              const tags =
                (r.scenario_tags && r.scenario_tags.length > 0
                  ? r.scenario_tags
                  : r.scenario_tag
                  ? [r.scenario_tag]
                  : null) ??
                (r.scenario_id != null
                  ? scenarioMap[r.scenario_id]?.tags ??
                    (scenarioMap[r.scenario_id]?.tag
                      ? [scenarioMap[r.scenario_id]!.tag!]
                      : [])
                  : []);
              if (!tags || tags.length === 0) {
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
                  (r.scenario_tags && r.scenario_tags.length > 0
                    ? r.scenario_tags
                    : r.scenario_tag
                    ? [r.scenario_tag]
                    : null) ??
                  (r.scenario_id != null
                    ? scenarioMap[r.scenario_id]?.tags ??
                      (scenarioMap[r.scenario_id]?.tag
                        ? [scenarioMap[r.scenario_id]!.tag!]
                        : [])
                    : []);
                if (!tags || tags.length === 0) return "—";
                return tags.map((t) => t.name).join(", ");
              },
              placeholder: "Etiquetas…",
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
          {
            key: "timing",
            header: "Tiempo",
            render: (r) => (
              <RunTimingCell
                startedAt={r.started_at ?? null}
                finishedAt={r.finished_at ?? null}
                queuedAt={r.queued_at}
                onClick={() => setLogsOpenForJob(r.id)}
                title="Ver registros (logs) de la ejecución"
              />
            ),
          },
          {
            key: "open",
            header: "Detalle",
            render: (r) => {
              const iconBtn =
                "inline-flex h-8 w-8 items-center justify-center rounded-md border transition-colors";
              return (
                <div className="flex items-center gap-1.5">
                  <Link
                    to={paths.resultsDetail(r.id)}
                    title="Ver resultados (gráficas individuales)"
                    aria-label="Ver resultados"
                    className={`${iconBtn} border-slate-700 text-slate-300 hover:border-cyan-500/50 hover:bg-cyan-500/10 hover:text-cyan-300`}
                  >
                    <svg
                      width={16}
                      height={16}
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M3 3v18h18" />
                      <path d="M7 17V9" />
                      <path d="M12 17V5" />
                      <path d="M17 17v-7" />
                    </svg>
                  </Link>
                  <button
                    type="button"
                    onClick={() => setViewReportRun(r)}
                    title="Ver en un reporte (con esta simulación pre-cargada como Escenario 1)"
                    aria-label="Ver en un reporte"
                    className={`${iconBtn} border-slate-700 text-slate-300 hover:border-emerald-500/50 hover:bg-emerald-500/10 hover:text-emerald-300`}
                  >
                    <svg
                      width={16}
                      height={16}
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <path d="M14 2v6h6" />
                      <path d="M9 13h6" />
                      <path d="M9 17h6" />
                    </svg>
                  </button>
                  {r.status === "SUCCEEDED" ? (
                    <Link
                      to={paths.resultsDataExplorer(r.id)}
                      title="Explorar todos los datos de la simulación (tabla wide)"
                      aria-label="Data explorer"
                      className={`${iconBtn} border-slate-700 text-slate-300 hover:border-violet-500/50 hover:bg-violet-500/10 hover:text-violet-300`}
                    >
                      <svg
                        width={16}
                        height={16}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <rect x="3" y="3" width="18" height="18" rx="2" />
                        <path d="M3 9h18M3 15h18M9 3v18M15 3v18" />
                      </svg>
                    </Link>
                  ) : null}
                </div>
              );
            },
          },
        ]}
        searchableText={(r) =>
          `${r.id} ${r.scenario_id ?? ""} ${r.display_name ?? ""} ${r.scenario_name ?? ""} ${r.username ?? ""}`
        }
      />

      <p
        style={{
          margin: "4px 0 0",
          fontSize: 12,
          opacity: 0.75,
          lineHeight: 1.5,
        }}
      >
        Las simulaciones infactibles
        {infeasibleCount > 0 ? ` (${infeasibleCount} en esta vista)` : ""} no
        aparecen en esta lista porque no tienen resultados numéricos que graficar.
        Para revisarlas, ve a la sección <Link to={paths.simulation}>Simulación</Link>,
        donde cada corrida infactible tiene un botón para correr el diagnóstico
        (IIS + mapeo a parámetros).
      </p>
        </>
      ) : (
        <InfeasibilityReportsTab runs={infeasibleRuns} scenarioMap={scenarioMap} />
      )}

      {viewReportRun ? (
        <ChooseReportForRunModal
          run={viewReportRun}
          reports={reports}
          loading={loadingReports}
          onClose={() => setViewReportRun(null)}
          onPick={(report, slotIdx) =>
            openReportWithRun(report, viewReportRun.id, slotIdx)
          }
        />
      ) : null}

      <JobLogsModal jobId={logsOpenForJob} onClose={() => setLogsOpenForJob(null)} />
    </section>
  );
}

function InfeasibilityReportsTab({
  runs,
  scenarioMap,
}: {
  runs: SimulationRun[];
  scenarioMap: Record<number, Scenario>;
}) {
  if (runs.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: "center", opacity: 0.72 }}>
        No hay simulaciones infactibles con los filtros actuales.
      </div>
    );
  }
  const diagnosticLabel: Record<NonNullable<SimulationRun["diagnostic_status"]>, string> = {
    NONE: "Pendiente",
    QUEUED: "En cola",
    RUNNING: "Analizando",
    SUCCEEDED: "Disponible",
    FAILED: "Falló",
    CANCELLED: "Cancelado",
  };
  const diagnosticVariant: Record<NonNullable<SimulationRun["diagnostic_status"]>, "neutral" | "warning" | "success" | "danger" | "info"> = {
    NONE: "neutral", QUEUED: "info", RUNNING: "warning", SUCCEEDED: "success", FAILED: "danger", CANCELLED: "warning",
  };
  return (
    <div style={{ display: "grid", gap: 10 }}>
      <p style={{ margin: 0, fontSize: 13, opacity: 0.78 }}>
        Los reportes se mantienen separados de los resultados factibles. Abre uno para ejecutar el análisis progresivo CSV/pandas → certificado → IIS → relajación.
      </p>
      {runs.map((run) => {
        const diagnosticStatus = run.diagnostic_status ?? "NONE";
        const scenarioName = run.scenario_name ?? (run.scenario_id ? scenarioMap[run.scenario_id]?.name : null) ?? "Escenario no disponible";
        return (
          <article key={run.id} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, padding: 14, border: "1px solid rgba(239,68,68,0.32)", borderRadius: 8, background: "rgba(127,29,29,0.1)" }}>
            <div>
              <strong>{run.display_name || scenarioName}</strong>
              <div style={{ marginTop: 5, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                <Badge variant="danger">INFACTIBLE</Badge>
                <Badge variant={diagnosticVariant[diagnosticStatus]}>{diagnosticLabel[diagnosticStatus]}</Badge>
                <small>Job #{run.id} · {run.solver_name.toUpperCase()} · {new Date(run.queued_at).toLocaleString()}</small>
              </div>
              {run.description ? <p style={{ margin: "7px 0 0", fontSize: 12, opacity: 0.78 }}>{run.description}</p> : null}
            </div>
            <Link className="btn btn--primary" to={paths.infeasibilityReport(run.id)}>
              {diagnosticStatus === "NONE" ? "Abrir y analizar" : "Ver reporte"}
            </Link>
          </article>
        );
      })}
    </div>
  );
}

// ─── Modal: elegir reporte para abrir con esta corrida pre-cargada ─────────

function ChooseReportForRunModal({
  run,
  reports,
  loading,
  onClose,
  onPick,
}: {
  run: SimulationRun;
  reports: SavedReport[];
  loading: boolean;
  onClose: () => void;
  onPick: (report: SavedReport, slotIdx: number) => void;
}) {
  const [filter, setFilter] = useState("");
  /** Reporte seleccionado para elegir slot (paso 2 del modal). */
  const [picked, setPicked] = useState<SavedReport | null>(null);
  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return reports;
    return reports.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        (r.description ?? "").toLowerCase().includes(q),
    );
  }, [reports, filter]);

  /** Número de slots del reporte: max(defaults.length, aliases.length, 1). */
  const slotsOf = (r: SavedReport): number => {
    const d = Array.isArray(r.default_job_ids) ? r.default_job_ids.length : 0;
    const a = Array.isArray(r.scenario_aliases) ? r.scenario_aliases.length : 0;
    return Math.max(d, a, 1);
  };
  const slotLabel = (r: SavedReport, idx: number): string => {
    const alias = (r.scenario_aliases ?? [])[idx]?.trim();
    return alias && alias.length > 0 ? alias : `Escenario ${idx + 1}`;
  };

  const handleReportPick = (r: SavedReport) => {
    const n = slotsOf(r);
    if (n <= 1) {
      // Un solo escenario → no preguntes, asigna al slot 0.
      onPick(r, 0);
      return;
    }
    setPicked(r);
  };

  const runLabel =
    run.display_name?.trim() ||
    run.scenario_name?.trim() ||
    run.input_name?.trim() ||
    `Job ${run.id}`;

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 250,
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(560px, 100%)",
          maxHeight: "calc(100vh - 32px)",
          overflowY: "auto",
          background: "rgba(11,18,32,0.98)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 14,
          padding: 20,
          display: "grid",
          gap: 12,
        }}
      >
        <div>
          <h3 className="m-0 text-lg font-semibold text-white">
            Ver en un reporte
          </h3>
          <p className="m-0 mt-1 text-xs text-slate-400">
            La simulación <strong className="text-cyan-300">{runLabel}</strong>{" "}
            (#{run.id}) se cargará como <strong>Escenario 1</strong> en el
            dashboard del reporte que elijas.
          </p>
        </div>

        <input
          type="text"
          placeholder="Buscar reporte por nombre o descripción…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2 text-sm text-slate-100"
        />

        {picked ? (
          <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-3 space-y-2">
            <p className="m-0 text-xs text-slate-300">
              ¿En qué escenario de <strong>{picked.name}</strong> quieres cargar{" "}
              <strong className="text-cyan-300">{runLabel}</strong>?
            </p>
            <div className="grid gap-1">
              {Array.from({ length: slotsOf(picked) }).map((_, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onPick(picked, idx)}
                  className="w-full rounded-lg border border-slate-800 bg-slate-950/40 p-2 text-left hover:border-cyan-500/50 hover:bg-cyan-500/10 text-sm text-slate-100"
                >
                  <span className="text-slate-500 text-[11px] uppercase tracking-wider">
                    Slot {idx + 1} ·
                  </span>{" "}
                  <strong>{slotLabel(picked, idx)}</strong>
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setPicked(null)}
              className="text-[11px] text-slate-400 hover:text-slate-200 underline underline-offset-2"
            >
              ← Elegir otro reporte
            </button>
          </div>
        ) : loading ? (
          <p className="m-0 text-xs text-slate-500">Cargando reportes…</p>
        ) : filtered.length === 0 ? (
          <p className="m-0 text-xs text-slate-500">
            {reports.length === 0
              ? "No tienes reportes accesibles. Crea uno desde la sección Reportes."
              : "Sin coincidencias."}
          </p>
        ) : (
          <ul className="grid gap-1 max-h-[50vh] overflow-y-auto list-none p-0 m-0">
            {filtered.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => handleReportPick(r)}
                  className="w-full rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-left hover:border-cyan-500/50 hover:bg-cyan-500/10"
                >
                  <div className="flex items-center justify-between gap-2">
                    <strong className="text-sm text-slate-100">{r.name}</strong>
                    <div className="flex shrink-0 gap-1">
                      {r.is_official ? (
                        <span className="rounded-full border border-yellow-500/40 bg-yellow-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-yellow-300">
                          ★ Oficial
                        </span>
                      ) : null}
                      {r.is_public ? (
                        <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
                          Público
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <p className="m-0 mt-1 text-[11px] text-slate-500">
                    {r.items.length} gráfica{r.items.length === 1 ? "" : "s"}
                    {r.owner_username && !r.is_owner
                      ? ` · de ${r.owner_username}`
                      : ""}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex justify-end pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
