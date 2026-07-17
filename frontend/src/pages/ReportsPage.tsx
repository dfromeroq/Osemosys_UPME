/**
 * Página de reportes:
 *   - Tab "Mis gráficas guardadas" → CRUD sobre las plantillas guardadas por el usuario.
 *   - Tab "Generador de reportes" → permite seleccionar plantillas, asignar los
 *     escenarios requeridos por cada una (según num_scenarios) y descargar un ZIP
 *     con una imagen por plantilla (PNG o SVG).
 *
 * La generación de reportes se apoya en `/saved-chart-templates/report`, que
 * renderiza cada gráfica con los mismos helpers que usa la página de resultados.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/shared/components/Button";
import { JobSelect } from "@/shared/components/JobSelect";
import { downloadBlob } from "@/shared/utils/downloadBlob";
import { savedChartsApi } from "@/features/reports/api/savedChartsApi";
import { simulationApi } from "@/features/simulation/api/simulationApi";
import {
  getChartModule,
  getChartModules,
  type ChartModuleInfo,
} from "@/shared/charts/ChartSelector";
import { paths } from "@/routes/paths";
import { useCurrentUser } from "@/app/providers/useCurrentUser";
import { PreviewChartModal } from "@/features/reports/components/PreviewChartModal";
import { CategoriesPanel } from "@/features/reports/components/CategoriesPanel";
import { FavoriteStar } from "@/features/reports/components/FavoriteStar";
import { ChartPickerModal } from "@/features/reports/components/ChartPickerModal";
import { IconEye, IconPencil, IconSwap } from "@/features/reports/components/CardActionIcons";
import { RowScenarioPicker } from "@/features/reports/components/RowScenarioPicker";
import { ChartSeriesConfigTab } from "@/features/reports/components/ChartSeriesConfigTab";
import { VisualizationCatalogAdminTab } from "@/features/reports/components/VisualizationCatalogAdminTab";
import { pickRepresentativeJob } from "@/features/reports/pickRepresentativeJob";
import {
  loadReportScenarios,
  saveReportScenarios,
} from "@/features/reports/scenarioMemory";
import type {
  ReportLayout,
  ReportTemplateItem,
  SavedChartTemplate,
  SavedReport,
  SimulationRun,
} from "@/types/domain";
import {
  computeAutoLayout,
  expandLayoutForExport,
  reconcileLayout,
} from "@/features/reports/layout";

type TabId = "saved" | "generator" | "reports" | "chart_series" | "viz_catalog";

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("es-CO", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

/** Chip interactivo Público / Privado (clic para alternar si eres dueño). */
function VisibilityChip({
  isPublic,
  canEdit,
  onToggle,
}: {
  isPublic: boolean;
  canEdit: boolean;
  onToggle?: () => void;
}) {
  const label = isPublic ? "Público" : "Privado";
  const base = "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider";
  const cls = isPublic
    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
    : "border-amber-500/30 bg-amber-500/10 text-amber-300";
  if (!canEdit) {
    return <span className={`${base} ${cls}`} title={`Visibilidad: ${label}`}>{label}</span>;
  }
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`${base} ${cls} cursor-pointer hover:brightness-125`}
      title={isPublic ? "Cambiar a privado" : "Cambiar a público"}
    >
      {label}
    </button>
  );
}

/** Badge "Oficial" (admin-editable). */
function OfficialChip({
  isOfficial,
  canEdit,
  onToggle,
}: {
  isOfficial: boolean;
  canEdit: boolean;
  onToggle?: () => void;
}) {
  const cls =
    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border-yellow-500/40 bg-yellow-500/10 text-yellow-300";
  if (!isOfficial && !canEdit) return null;
  if (!isOfficial && canEdit) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="inline-flex items-center gap-1 rounded-full border border-slate-700 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400 hover:text-yellow-300 hover:border-yellow-500/40"
        title="Marcar como oficial (visible a todos)"
      >
        Marcar oficial
      </button>
    );
  }
  if (canEdit) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className={`${cls} cursor-pointer`}
        title="Quitar estado oficial"
      >
        ★ Oficial
      </button>
    );
  }
  return <span className={cls} title="Reporte oficial">★ Oficial</span>;
}

/**
 * Input numérico para reubicar una gráfica del reporte a una posición específica.
 * Muestra el número de orden actual; al editarlo y hacer Enter/blur llama a
 * `onSubmit(newIndex0Based)`.
 */
function PositionInput({
  index,
  total,
  onSubmit,
}: {
  index: number;
  total: number;
  onSubmit: (newIndex: number) => void;
}) {
  const [draft, setDraft] = useState<string>(String(index + 1).padStart(2, "0"));
  useEffect(() => {
    setDraft(String(index + 1).padStart(2, "0"));
  }, [index]);
  const commit = () => {
    const n = Number.parseInt(draft.trim(), 10);
    if (Number.isFinite(n) && n >= 1 && n <= total) {
      const newIdx = n - 1;
      if (newIdx !== index) onSubmit(newIdx);
    }
    setDraft(String(index + 1).padStart(2, "0"));
  };
  return (
    <input
      type="number"
      min={1}
      max={total}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          (e.target as HTMLInputElement).blur();
        }
      }}
      onFocus={(e) => e.currentTarget.select()}
      title={`Posición 1–${total}. Escribe un número y Enter para mover.`}
      className="h-8 w-12 shrink-0 rounded-md border border-cyan-500/30 bg-cyan-500/10 text-center text-sm font-bold tabular-nums text-cyan-300 focus:outline-none focus:border-cyan-400 focus:bg-cyan-500/20"
    />
  );
}

/**
 * Zona delgada entre filas del generador que al hover se expande y permite
 * insertar una gráfica en esa posición. Minimiza el ruido visual cuando no
 * se usa.
 */
function InsertChartHere({
  onClick,
  label,
}: {
  onClick: () => void;
  label: string;
}) {
  return (
    <div className="group relative h-2.5 transition-all duration-150 hover:h-8">
      <button
        type="button"
        onClick={onClick}
        title={label}
        aria-label={label}
        className="absolute inset-x-0 top-1/2 -translate-y-1/2 mx-auto flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-150"
      >
        <span className="flex items-center gap-1 rounded-full border border-cyan-500/40 bg-slate-950/80 px-2 py-0.5 text-[10px] font-semibold text-cyan-300 hover:bg-cyan-500/20">
          <span className="text-sm leading-none">＋</span> {label}
        </span>
      </button>
      <div
        aria-hidden="true"
        className="absolute inset-x-4 top-1/2 h-px bg-transparent group-hover:bg-cyan-500/30 transition-colors"
      />
    </div>
  );
}

/**
 * Panel explícito para configurar los escenarios predeterminados del reporte.
 * Muestra cuáles están persistidos hoy, permite sobrescribirlos con los
 * escenarios actuales, o quitarlos. Persiste en `report.default_job_ids`
 * mediante `savedChartsApi.updateReport`.
 */
function DefaultScenariosPanel({
  reportId,
  current,
  savedDefaults,
  scenarioAliases,
  availableJobs,
  onSaved,
}: {
  reportId: number | null;
  current: (number | null)[];
  savedDefaults: (number | null)[] | null;
  scenarioAliases: string[];
  availableJobs: SimulationRun[];
  onSaved: (nextDefaults: (number | null)[] | null) => void;
}) {
  const [saving, setSaving] = useState(false);
  const jobLabel = (jid: number | null | undefined): string => {
    if (jid == null) return "—";
    const j = availableJobs.find((r) => r.id === jid);
    return (
      j?.display_name?.trim() ||
      j?.scenario_name ||
      j?.input_name ||
      `Job ${jid}`
    );
  };
  const aliasLabel = (idx: number): string => {
    const a = scenarioAliases[idx]?.trim();
    return a && a.length > 0 ? a : `Escenario ${idx + 1}`;
  };
  const hasDefaults =
    Array.isArray(savedDefaults) && savedDefaults.some((v) => v != null);
  const sameAsSaved =
    hasDefaults &&
    savedDefaults!.length === current.length &&
    savedDefaults!.every((v, i) => (v ?? null) === (current[i] ?? null));

  const persist = async (next: (number | null)[] | null) => {
    if (!reportId) return;
    setSaving(true);
    try {
      await savedChartsApi.updateReport(reportId, { default_job_ids: next });
      onSaved(next);
    } catch (err) {
      alert(
        err instanceof Error
          ? err.message
          : "No se pudieron guardar los predeterminados.",
      );
    } finally {
      setSaving(false);
    }
  };

  if (!reportId) {
    return (
      <div className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2 text-[11px] text-slate-400">
        Guarda primero este reporte para poder fijar escenarios predeterminados.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="m-0 text-[11px] font-semibold uppercase tracking-wider text-emerald-200">
          Escenarios predeterminados del reporte
          {hasDefaults ? (
            sameAsSaved ? (
              <span className="ml-2 rounded-full bg-emerald-500/15 border border-emerald-500/40 px-1.5 py-0.5 text-[10px] text-emerald-200 normal-case">
                ✓ usando los predeterminados
              </span>
            ) : (
              <span className="ml-2 rounded-full bg-amber-500/10 border border-amber-500/40 px-1.5 py-0.5 text-[10px] text-amber-200 normal-case">
                cambios no guardados
              </span>
            )
          ) : (
            <span className="ml-2 rounded-full bg-slate-800/70 border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400 normal-case">
              sin predeterminados
            </span>
          )}
        </p>
        <div className="flex gap-1">
          <button
            type="button"
            disabled={saving}
            onClick={() => {
              if (
                !confirm(
                  "¿Guardar los escenarios seleccionados como predeterminados del reporte?\n\nLa próxima vez que se abra, cargará con estos.",
                )
              )
                return;
              void persist(current);
            }}
            className="rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
          >
            Guardar como predeterminados
          </button>
          {hasDefaults ? (
            <button
              type="button"
              disabled={saving}
              onClick={() => {
                if (!confirm("¿Quitar los escenarios predeterminados del reporte?"))
                  return;
                void persist(null);
              }}
              className="rounded border border-slate-700 px-2 py-0.5 text-[10px] font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-50"
            >
              Quitar predeterminados
            </button>
          ) : null}
        </div>
      </div>
      {hasDefaults ? (
        <div className="flex flex-wrap gap-1.5 text-[11px]">
          {savedDefaults!.map((jid, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded border border-emerald-500/20 bg-emerald-500/5 px-1.5 py-0.5 text-emerald-200"
            >
              <span className="text-emerald-300/70 text-[10px] uppercase tracking-wider">
                {aliasLabel(i)}:
              </span>
              <span>{jobLabel(jid)}</span>
            </span>
          ))}
        </div>
      ) : (
        <p className="m-0 text-[11px] text-slate-400">
          Este reporte no tiene escenarios predeterminados. Guarda los
          seleccionados para que la próxima vez se abran así.
        </p>
      )}
    </div>
  );
}

function templateSummary(t: SavedChartTemplate): string {
  const bits: string[] = [];
  bits.push(`Tipo: ${t.tipo}`);
  bits.push(`Unidad: ${t.un}`);
  if (t.variable) bits.push(`Variable: ${t.variable}`);
  if (t.sub_filtro) bits.push(`Sub-filtro: ${t.sub_filtro}`);
  if (t.loc) bits.push(`Loc: ${t.loc}`);
  if (t.agrupar_por) bits.push(`Agrupar: ${t.agrupar_por}`);
  if (t.view_mode) bits.push(`Trazo: ${t.view_mode}`);
  bits.push(
    t.compare_mode === "facet"
      ? `Modo: facet · ${t.num_scenarios} escenarios`
      : t.compare_mode === "by-year"
      ? `Modo: por año · ${t.num_scenarios} escenarios`
      : t.compare_mode === "line-total"
      ? `Modo: líneas totales · ${t.num_scenarios} escenarios`
      : `Modo: único · 1 escenario`,
  );
  return bits.join(" · ");
}

// ─── Página ────────────────────────────────────────────────────────────────

export function ReportsPage() {
  const { user } = useCurrentUser();
  const isAdminReports = Boolean(
    user?.is_admin_reports ?? user?.can_manage_scenarios,
  );
  const canManageOfficial = isAdminReports;
  const [tab, setTab] = useState<TabId>("reports");
  const [templates, setTemplates] = useState<SavedChartTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [availableJobs, setAvailableJobs] = useState<SimulationRun[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);

  const [reports, setReports] = useState<SavedReport[]>([]);
  const [loadingReports, setLoadingReports] = useState(true);
  const [includeOthersPrivate, setIncludeOthersPrivate] = useState(false);
  /** Cuando se activa, el generador pre-carga un reporte guardado. */
  const [loadReportRequest, setLoadReportRequest] = useState<SavedReport | null>(
    null,
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await savedChartsApi.list();
      setTemplates(rows);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Error cargando gráficas guardadas.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshReports = useCallback(async () => {
    setLoadingReports(true);
    try {
      const rows = await savedChartsApi.listReports(
        isAdminReports && includeOthersPrivate
          ? { includeOthersPrivate: true }
          : undefined,
      );
      setReports(rows);
    } catch (err) {
      console.error("Error cargando reportes guardados", err);
    } finally {
      setLoadingReports(false);
    }
  }, [isAdminReports, includeOthersPrivate]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    refreshReports();
  }, [refreshReports]);

  const handleLoadReport = useCallback((r: SavedReport) => {
    setLoadReportRequest(r);
    setTab("generator");
  }, []);

  // Auto-cargar un reporte si la URL trae ?load=<id> (vínculo desde el dashboard).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const idStr = params.get("load");
    if (!idStr) return;
    const id = Number(idStr);
    if (!id) return;
    savedChartsApi
      .getReport(id)
      .then((r) => handleLoadReport(r))
      .catch((err) => console.error("Auto-load report failed", err))
      .finally(() => {
        // Limpia el query string para que no re-dispare al refrescar.
        const url = new URL(window.location.href);
        url.searchParams.delete("load");
        window.history.replaceState({}, "", url.toString());
      });
  }, [handleLoadReport]);

  useEffect(() => {
    setLoadingJobs(true);
    simulationApi
      .listRuns({ scope: "global", status_filter: "SUCCEEDED", cantidad: 100 })
      .then((res) => {
        // Solo escenarios con resultados utilizables: SUCCEEDED y NO infactibles.
        setAvailableJobs(
          (res.data ?? []).filter((r) => !r.is_infeasible_result),
        );
      })
      .catch(console.error)
      .finally(() => setLoadingJobs(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-6 space-y-6 font-sans">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-white">Reportes</h1>
        <p className="m-0 text-sm text-slate-500 max-w-3xl">
          Guarda gráficas desde la página de resultados y combínalas aquí en un reporte.
          Cada plantilla recuerda sus filtros, unidades, tipo de trazo y cuántos
          escenarios necesita cuando se genera el reporte.
        </p>
      </header>

      <div
        role="tablist"
        aria-label="Secciones de reportes"
        className="inline-flex gap-1 rounded-xl border border-slate-800 bg-slate-900/60 p-1"
      >
        {[
          { id: "reports" as TabId, label: `Mis reportes guardados (${reports.length})` },
          { id: "generator" as TabId, label: "Generador de reporte" },
          { id: "saved" as TabId, label: `Mis gráficas guardadas (${templates.length})` },
          ...(isAdminReports
            ? [
                { id: "chart_series" as TabId, label: "Series por gráfica" },
                { id: "viz_catalog" as TabId, label: "Catálogo de gráficas" },
              ]
            : []),
        ].map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t.id)}
              className={`rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
                active
                  ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/25"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {error ? (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {tab === "saved" ? (
        <SavedChartsTab
          templates={templates}
          loading={loading}
          onRefresh={refresh}
          availableJobs={availableJobs}
          loadingJobs={loadingJobs}
        />
      ) : tab === "reports" ? (
        <SavedReportsTab
          reports={reports}
          loading={loadingReports}
          onRefresh={refreshReports}
          onLoadReport={handleLoadReport}
          templates={templates}
          onTemplatesRefresh={refresh}
          canManageOfficial={canManageOfficial}
          isAdminReports={isAdminReports}
          includeOthersPrivate={includeOthersPrivate}
          onToggleIncludeOthersPrivate={(v) => setIncludeOthersPrivate(v)}
          onGoToGenerator={() => setTab("generator")}
        />
      ) : tab === "chart_series" ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <ChartSeriesConfigTab />
        </div>
      ) : tab === "viz_catalog" ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <VisualizationCatalogAdminTab />
        </div>
      ) : (
        <ReportGeneratorTab
          templates={templates}
          loading={loading}
          availableJobs={availableJobs}
          loadingJobs={loadingJobs}
          loadReportRequest={loadReportRequest}
          onLoadReportConsumed={() => setLoadReportRequest(null)}
          onReportSaved={refreshReports}
          savedReports={reports}
          onTemplatesRefresh={refresh}
          isAdminReports={isAdminReports}
        />
      )}
    </div>
  );
}

// ─── Tab 1: Lista CRUD ──────────────────────────────────────────────────────

function SavedChartsTab({
  templates,
  loading,
  onRefresh,
  availableJobs,
  loadingJobs,
}: {
  templates: SavedChartTemplate[];
  loading: boolean;
  onRefresh: () => void;
  availableJobs: SimulationRun[];
  loadingJobs: boolean;
}) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [previewTemplate, setPreviewTemplate] =
    useState<SavedChartTemplate | null>(null);
  const [showOnlyFavorites, setShowOnlyFavorites] = useState(false);

  const toggleChartFavorite = async (tpl: SavedChartTemplate, next: boolean) => {
    try {
      await savedChartsApi.setChartFavorite(tpl.id, next);
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "No se pudo cambiar favorito.");
    }
  };

  const startEdit = (tpl: SavedChartTemplate) => {
    setEditingId(tpl.id);
    setEditName(tpl.name);
    setEditDescription(tpl.description ?? "");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditName("");
    setEditDescription("");
  };

  const saveEdit = async () => {
    if (editingId == null) return;
    const trimmed = editName.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      await savedChartsApi.update(editingId, {
        name: trimmed,
        description: editDescription.trim() || null,
      });
      cancelEdit();
      onRefresh();
    } catch (err) {
      alert(
        err instanceof Error ? err.message : "No se pudo actualizar la plantilla.",
      );
    } finally {
      setSaving(false);
    }
  };

  const remove = async (tpl: SavedChartTemplate) => {
    if (!confirm(`¿Eliminar la gráfica "${tpl.name}"?`)) return;
    try {
      await savedChartsApi.remove(tpl.id);
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "No se pudo eliminar.");
    }
  };

  const toggleVisibility = async (tpl: SavedChartTemplate) => {
    try {
      await savedChartsApi.update(tpl.id, { is_public: !(tpl.is_public ?? false) });
      onRefresh();
    } catch (err) {
      alert(
        err instanceof Error
          ? err.message
          : "No se pudo cambiar la visibilidad.",
      );
    }
  };

  // ID del último resultado con datos (más reciente queued_at) para enlace rápido
  // al generador de gráficas individual de Resultados. Debe declararse antes de
  // cualquier early return para no violar las reglas de hooks.
  const latestRunId = useMemo(() => {
    if (availableJobs.length === 0) return null;
    let best = availableJobs[0]!;
    for (const r of availableJobs) {
      if (new Date(r.queued_at).getTime() > new Date(best.queued_at).getTime()) {
        best = r;
      }
    }
    return best.id;
  }, [availableJobs]);

  if (loading) {
    return (
      <div className="animate-pulse rounded-xl border border-slate-800 bg-slate-900/40 h-40" />
    );
  }

  const generateChartsButton = (
    <Link
      to={
        latestRunId != null ? paths.resultsDetail(latestRunId) : paths.results
      }
      className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold no-underline ${
        latestRunId != null
          ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20"
          : "border-slate-700 text-slate-500 cursor-not-allowed pointer-events-none"
      }`}
      title={
        latestRunId != null
          ? `Crea o guarda nuevas gráficas desde Resultados (último resultado #${latestRunId}).`
          : "No hay resultados disponibles todavía."
      }
      onClick={(e) => {
        if (latestRunId == null) e.preventDefault();
      }}
    >
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
      </svg>
      Generar gráficas →
    </Link>
  );

  if (templates.length === 0) {
    return (
      <>
      <div className="flex justify-end mb-3">{generateChartsButton}</div>
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-10 text-center">
        <h3 className="mb-2 text-lg font-semibold text-slate-200">
          Aún no tienes gráficas guardadas
        </h3>
        <p className="m-0 mx-auto max-w-md text-sm text-slate-500">
          Ve a{" "}
          <Link to={paths.results} className="text-cyan-400 hover:underline">
            Resultados
          </Link>
          , abre una simulación y usa el botón "Guardar gráfica" para crear tu
          primera plantilla.
        </p>
      </div>
      </>
    );
  }

  const visibleTemplates = showOnlyFavorites
    ? templates.filter((t) => t.is_favorite === true)
    : templates;

  return (
    <>
    <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="m-0 text-xs text-slate-500">
          {templates.length} gráfica{templates.length === 1 ? "" : "s"} accesible
          {templates.length === 1 ? "" : "s"} (propias + públicas + oficiales).
        </p>
        <button
          type="button"
          onClick={() => setShowOnlyFavorites((v) => !v)}
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold transition-colors ${
            showOnlyFavorites
              ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
              : "border-slate-700 bg-slate-900/40 text-slate-400 hover:text-slate-200"
          }`}
          title="Mostrar solo gráficas marcadas como favoritas"
        >
          <span style={{ color: showOnlyFavorites ? "#fbbf24" : undefined }}>★</span>
          Solo favoritas
        </button>
      </div>
      {generateChartsButton}
    </div>
    {showOnlyFavorites && visibleTemplates.length === 0 ? (
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-6 text-center text-sm text-slate-500">
        No tienes gráficas marcadas como favoritas todavía.
      </div>
    ) : null}
    <div className="grid gap-3">
      {visibleTemplates.map((tpl) => {
        const editing = editingId === tpl.id;
        return (
          <div
            key={tpl.id}
            className="rounded-xl border border-slate-800 bg-slate-900/40 p-5"
          >
            {editing ? (
              <div className="grid gap-3">
                <label className="grid gap-1">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    Nombre
                  </span>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2 text-sm text-slate-100"
                  />
                </label>
                <label className="grid gap-1">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    Descripción
                  </span>
                  <textarea
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    rows={4}
                    className="rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2 text-sm text-slate-100 resize-y font-mono"
                  />
                </label>
                <div className="flex gap-2 justify-end">
                  <Button variant="ghost" onClick={cancelEdit} disabled={saving}>
                    Cancelar
                  </Button>
                  <Button variant="primary" onClick={saveEdit} disabled={saving}>
                    {saving ? "Guardando…" : "Guardar cambios"}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <FavoriteStar
                      isFavorite={tpl.is_favorite ?? false}
                      onToggle={(next) => toggleChartFavorite(tpl, next)}
                    />
                    <h3 className="m-0 text-base font-semibold text-white break-words">
                      {tpl.name}
                    </h3>
                    <VisibilityChip
                      isPublic={tpl.is_public ?? false}
                      canEdit={tpl.is_owner ?? true}
                      onToggle={() => toggleVisibility(tpl)}
                    />
                    {!tpl.is_owner ? (
                      <span className="rounded-full border border-slate-700 bg-slate-800/60 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                        de {tpl.owner_username ?? "otro"}
                      </span>
                    ) : null}
                  </div>
                  <p className="m-0 text-xs text-slate-500">
                    {templateSummary(tpl)}
                  </p>
                  {tpl.description ? (
                    <pre className="m-0 whitespace-pre-wrap break-words rounded-md border border-slate-800/70 bg-slate-950/40 p-3 text-[12px] text-slate-400 font-mono">
                      {tpl.description}
                    </pre>
                  ) : null}
                  <p className="m-0 text-[10px] text-slate-600">
                    Creada el {formatDate(tpl.created_at)} · ID {tpl.id}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0 flex-wrap">
                  <button
                    type="button"
                    onClick={() => setPreviewTemplate(tpl)}
                    className="rounded-lg border border-cyan-500/40 px-3 py-1.5 text-xs font-medium text-cyan-300 hover:bg-cyan-500/10"
                    title="Previsualizar con un escenario"
                  >
                    Visualizar
                  </button>
                  {tpl.is_owner ? (
                    <>
                      <button
                        type="button"
                        onClick={() => startEdit(tpl)}
                        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800"
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        onClick={() => remove(tpl)}
                        className="rounded-lg border border-rose-500/40 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-500/10"
                      >
                        Eliminar
                      </button>
                    </>
                  ) : null}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
    <PreviewChartModal
      open={previewTemplate !== null}
      onClose={() => setPreviewTemplate(null)}
      template={previewTemplate}
      availableJobs={availableJobs}
      loadingJobs={loadingJobs}
    />
    </>
  );
}

// ─── Tab 2: Generador de reporte ────────────────────────────────────────────

/** Configuración de un ítem seleccionado (job_ids se resuelven en la generación). */
type SelectionData = {
  job_ids: (number | null)[];
};

const UNGROUPED_MODULE: ChartModuleInfo = {
  id: "_otros",
  label: "Otros",
  emoji: "📁",
};

function ReportGeneratorTab({
  templates,
  loading,
  availableJobs,
  loadingJobs,
  loadReportRequest,
  onLoadReportConsumed,
  onReportSaved,
  savedReports,
  onTemplatesRefresh,
  isAdminReports,
}: {
  templates: SavedChartTemplate[];
  loading: boolean;
  availableJobs: SimulationRun[];
  loadingJobs: boolean;
  loadReportRequest: SavedReport | null;
  onLoadReportConsumed: () => void;
  onReportSaved: () => void;
  savedReports: SavedReport[];
  onTemplatesRefresh: () => void;
  isAdminReports: boolean;
}) {
  /**
   * Orden del reporte: lista de filas con id estable. Permite duplicados de la
   * misma plantilla (por ejemplo para representar el mismo chart con escenarios
   * distintos). Cada fila puede tener un `slotOverride` opcional que elige qué
   * escenarios globales consume (por índice 0-based en globalScenarios).
   */
  type RowState = {
    rowId: string;
    tpl_id: number;
    slotOverride?: number[] | null;
  };
  const [rows, setRows] = useState<RowState[]>([]);
  /** Derivado para compatibilidad (layout, checkboxes, payload fallback). */
  const order = useMemo(() => rows.map((r) => r.tpl_id), [rows]);
  /** Genera un id único estable por fila (solo client-side). */
  const nextRowIdRef = useRef(0);
  const makeRowId = () => {
    nextRowIdRef.current += 1;
    return `r${Date.now().toString(36)}-${nextRowIdRef.current}`;
  };
  /** Datos asociados (job_ids por rowId). Se deriva de globalScenarios + slotOverride. */
  const [selectionData, setSelectionData] = useState<Record<number, SelectionData>>({});
  /** Qué acordeones están expandidos (por module id). */
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  /** Escenarios globales: slot i se propaga al slot i de cada plantilla. */
  const [globalScenarios, setGlobalScenarios] = useState<(number | null)[]>([]);
  /** Alias por escenario global (persistido en el reporte). */
  const [scenarioAliases, setScenarioAliases] = useState<string[]>([]);

  const [fmt, setFmt] = useState<"png" | "svg">("png");
  const [organizeFolders, setOrganizeFolders] = useState(false);
  // Rango de años aplicado al export (no persistido aquí — el reporte guardado
  // tiene su propio rango persistido editable desde el dashboard).
  const [yearFrom, setYearFrom] = useState<number | null>(null);
  const [yearTo, setYearTo] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  /** Alias por job_id solo para el export (no muta display_name real). */
  const [renameOverrides, setRenameOverrides] = useState<Record<number, string>>({});
  const [renameOpen, setRenameOpen] = useState(false);
  /**
   * Compensación de scroll al mover una gráfica con ↑/↓: el click deja un
   * anchor; después de re-renderizar (requestAnimationFrame), ajustamos el
   * scroll para que el botón clicado quede más o menos bajo el cursor.
   *
   * Implementación robusta: capturamos `pageY` del click (espacio documento)
   * y después del paint calculamos el desplazamiento sobre la misma fila
   * identificada por `data-row-id`, sin depender del `btn` DOM ref. Así, si
   * React desmonta/reemplaza el botón por algún motivo, no queda un anchor
   * roto que rompa interacciones futuras.
   */
  const anchorAndRun = (
    e: React.MouseEvent<HTMLButtonElement>,
    rowId: string,
    run: () => void,
  ) => {
    const clickClientY = e.clientY;
    run();
    requestAnimationFrame(() => {
      try {
        const selector = `[data-row-id="${rowId}"]`;
        const target = document.querySelector<HTMLElement>(selector);
        if (!target) return;
        const newRect = target.getBoundingClientRect();
        if (newRect.width === 0 && newRect.height === 0) return;
        // Mantener la fila aproximadamente a la misma altura visual que tenía
        // el click (en viewport). Si se salió fuera del viewport, no hacemos
        // nada — el usuario ve el scroll natural.
        const rowCenter = newRect.top + newRect.height / 2;
        const delta = rowCenter - clickClientY;
        if (Math.abs(delta) > 4) {
          window.scrollBy({ left: 0, top: delta, behavior: "auto" });
        }
      } catch {
        /* ignore */
      }
    });
  };

  /** Preview modal (visualiza una plantilla con escenarios seleccionados). */
  const [previewTemplateInline, setPreviewTemplateInline] =
    useState<SavedChartTemplate | null>(null);
  /** Modal para reemplazar un item del reporte por otra plantilla (row-based). */
  const [replaceTargetId, setReplaceTargetId] = useState<string | null>(null);
  /** Índice 0-based después del cual insertar una nueva gráfica (picker). */
  const [insertAfterIdx, setInsertAfterIdx] = useState<number | null>(null);
  /** Edición inline del report_title por plantilla. */
  const [titleEditingId, setTitleEditingId] = useState<number | null>(null);
  const [titleDraft, setTitleDraft] = useState<string>("");
  /** Fila cuya asignación de escenarios está expandida. null = todas colapsadas. */
  const [editingSlotsRowId, setEditingSlotsRowId] = useState<string | null>(null);

  /** Vista del paso 2: lista plana ordenada o agrupada por categorías. */
  const [viewMode, setViewMode] = useState<"list" | "categories">("list");
  /** Layout pendiente de guardar (override manual). null = aún no construido en este modo. */
  const [pendingLayout, setPendingLayout] = useState<ReportLayout | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);

  /** Reporte que se está editando (loaded vs. nuevo). */
  const [currentReportId, setCurrentReportId] = useState<number | null>(null);
  /** Snapshot del reporte tal como vino del backend (para detectar cambios sin guardar). */
  const [loadedReport, setLoadedReport] = useState<SavedReport | null>(null);
  const [showSaveReportModal, setShowSaveReportModal] = useState(false);
  const [reportToast, setReportToast] = useState<string | null>(null);
  /** Modal "tienes cambios sin guardar" antes de ir al dashboard. */
  const [unsavedDashboardPrompt, setUnsavedDashboardPrompt] = useState(false);

  // ── Cargar un reporte guardado (desde la tab "Mis reportes") ──
  useEffect(() => {
    if (!loadReportRequest) return;
    // Si aún no cargaron las plantillas accesibles, esperar; de lo contrario
    // filtraríamos todo a [] y el reporte quedaría vacío en el Generador.
    if (loading) return;
    if (templates.length === 0 && (loadReportRequest.items?.length ?? 0) > 0) {
      return;
    }
    const validIds = loadReportRequest.items.filter((id) =>
      templates.some((t) => t.id === id),
    );
    // Permite duplicados: cada elemento crea una fila independiente con rowId nuevo.
    setRows(
      validIds.map((tid) => ({ rowId: makeRowId(), tpl_id: tid })),
    );
    setSelectionData(() => {
      const next: Record<number, SelectionData> = {};
      const seen = new Set<number>();
      for (const tid of validIds) {
        if (seen.has(tid)) continue;
        seen.add(tid);
        const tpl = templates.find((t) => t.id === tid);
        if (tpl) {
          next[tid] = {
            job_ids: Array.from({ length: tpl.num_scenarios }, () => null),
          };
        }
      }
      return next;
    });
    setFmt(loadReportRequest.fmt);
    setCurrentReportId(loadReportRequest.id);
    setLoadedReport(loadReportRequest);
    // Heredar el rango de años persistido en el reporte.
    setYearFrom(
      typeof loadReportRequest.year_from === "number"
        ? loadReportRequest.year_from
        : null,
    );
    setYearTo(
      typeof loadReportRequest.year_to === "number"
        ? loadReportRequest.year_to
        : null,
    );
    // Restaurar aliases persistidos del reporte.
    setScenarioAliases(
      Array.isArray(loadReportRequest.scenario_aliases)
        ? [...loadReportRequest.scenario_aliases]
        : [],
    );
    // Prioridad para los escenarios globales:
    //   1) default_job_ids persistidos en el reporte (si existen, siempre ganan);
    //   2) memoria client-side (última sesión en este navegador) como fallback;
    //   3) vacío.
    const savedDefaults = Array.isArray(loadReportRequest.default_job_ids)
      ? loadReportRequest.default_job_ids
      : null;
    const hasDefaults = savedDefaults && savedDefaults.some((v) => v != null);
    if (hasDefaults) {
      setGlobalScenarios([...(savedDefaults as (number | null)[])]);
    } else {
      const remembered = loadReportScenarios(loadReportRequest.id);
      if (remembered && remembered.length > 0) {
        setGlobalScenarios(remembered);
      }
    }
    // Si el reporte tiene layout persistido, abrir directamente en vista Categorías.
    if (loadReportRequest.layout) {
      setPendingLayout(loadReportRequest.layout);
      setViewMode("categories");
    } else {
      setPendingLayout(null);
      setViewMode("list");
    }
    onLoadReportConsumed();
  }, [loadReportRequest, templates, onLoadReportConsumed]);

  // Si estamos en vista Categorías, mantener pendingLayout sincronizado con el
  // orden: agregar nuevos ids a "Sin asignar", quitar los eliminados.
  const templatesByIdLocal = useMemo(
    () => new Map(templates.map((t) => [t.id, t])),
    [templates],
  );
  useEffect(() => {
    if (viewMode !== "categories" || !pendingLayout) return;
    setPendingLayout((prev) =>
      prev ? reconcileLayout(prev, order, templatesByIdLocal) : prev,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order, viewMode]);

  // Sincroniza selectionData con la lista de items: cualquier id que aparezca
  // en `order` debe tener un slot inicial para sus job_ids; los que ya no
  // están se quedan tal cual (no estorban).
  useEffect(() => {
    setSelectionData((prev) => {
      let changed = false;
      const next: Record<number, SelectionData> = { ...prev };
      for (const id of order) {
        if (next[id]) continue;
        const tpl = templatesByIdLocal.get(id);
        if (!tpl) continue;
        next[id] = {
          job_ids: Array.from({ length: tpl.num_scenarios }, () => null),
        };
        changed = true;
      }
      return changed ? next : prev;
    });
  }, [order, templatesByIdLocal]);

  // ── Agrupar plantillas por módulo (primer nivel de jerarquía) ──
  const groupedTemplates = useMemo(() => {
    const allModules = getChartModules();
    const byModule = new Map<string, SavedChartTemplate[]>();
    const moduleMeta = new Map<string, ChartModuleInfo>();
    for (const m of allModules) moduleMeta.set(m.id, m);
    for (const tpl of templates) {
      const mod = getChartModule(tpl.tipo) ?? UNGROUPED_MODULE;
      if (!moduleMeta.has(mod.id)) moduleMeta.set(mod.id, mod);
      const list = byModule.get(mod.id) ?? [];
      list.push(tpl);
      byModule.set(mod.id, list);
    }
    // Respetar el orden de allModules; al final, módulos no conocidos.
    // Dentro de cada grupo: favoritos primero (sort estable).
    const sortFavFirst = (list: SavedChartTemplate[]): SavedChartTemplate[] => {
      const withIdx = list.map((tpl, idx) => ({ tpl, idx }));
      withIdx.sort((a, b) => {
        const af = a.tpl.is_favorite ? 1 : 0;
        const bf = b.tpl.is_favorite ? 1 : 0;
        if (af !== bf) return bf - af;
        return a.idx - b.idx;
      });
      return withIdx.map((x) => x.tpl);
    };
    const result: { module: ChartModuleInfo; templates: SavedChartTemplate[] }[] = [];
    const knownIds = new Set(allModules.map((m) => m.id));
    for (const m of allModules) {
      const items = byModule.get(m.id);
      if (items && items.length > 0) result.push({ module: m, templates: sortFavFirst(items) });
    }
    for (const [id, items] of byModule.entries()) {
      if (knownIds.has(id)) continue;
      const meta = moduleMeta.get(id) ?? UNGROUPED_MODULE;
      result.push({ module: meta, templates: sortFavFirst(items) });
    }
    return result;
  }, [templates]);

  // Mantenemos los grupos colapsados por defecto para reducir ruido visual.
  // Los usuarios expanden manualmente la categoría que necesitan.
  useEffect(() => {
    setExpandedGroups((prev) => {
      if (Object.keys(prev).length > 0) return prev;
      const next: Record<string, boolean> = {};
      for (const { module } of groupedTemplates) next[module.id] = false;
      return next;
    });
  }, [groupedTemplates]);

  const selectedIds = useMemo(() => new Set(order), [order]);
  const orderIndexOf = (tplId: number) => order.indexOf(tplId);

  /** `setOrder`-compatible shim: acepta una función que recibe `order` (number[])
   *  y devuelve un nuevo `order`. Reconstruye `rows` preservando los rowIds
   *  existentes cuando sea posible (match por template_id desde la izquierda). */
  const setOrder = (updater: (prev: number[]) => number[]) => {
    setRows((prevRows) => {
      const prevOrder = prevRows.map((r) => r.tpl_id);
      const nextOrder = updater(prevOrder);
      if (nextOrder === prevOrder) return prevRows;
      const usedRowIds = new Set<string>();
      const byTpl = new Map<number, RowState[]>();
      for (const r of prevRows) {
        if (!byTpl.has(r.tpl_id)) byTpl.set(r.tpl_id, []);
        byTpl.get(r.tpl_id)!.push(r);
      }
      const next: RowState[] = [];
      for (const tplId of nextOrder) {
        const pool = byTpl.get(tplId) ?? [];
        const reused = pool.find((r) => !usedRowIds.has(r.rowId));
        if (reused) {
          usedRowIds.add(reused.rowId);
          next.push(reused);
        } else {
          next.push({ rowId: makeRowId(), tpl_id: tplId });
        }
      }
      return next;
    });
  };

  const addTemplate = (tpl: SavedChartTemplate) => {
    if (selectedIds.has(tpl.id)) return;
    setRows((prev) => [...prev, { rowId: makeRowId(), tpl_id: tpl.id }]);
    setSelectionData((prev) => ({
      ...prev,
      [tpl.id]: {
        job_ids: Array.from({ length: tpl.num_scenarios }, () => null),
      },
    }));
  };

  /** Elimina una fila por rowId (una sola instancia). */
  const removeRow = (rowId: string) => {
    setRows((prev) => {
      const next = prev.filter((r) => r.rowId !== rowId);
      const remainingTplIds = new Set(next.map((r) => r.tpl_id));
      setSelectionData((prevSel) => {
        const nextSel = { ...prevSel };
        for (const key of Object.keys(nextSel)) {
          const tid = Number(key);
          if (!remainingTplIds.has(tid)) delete nextSel[tid];
        }
        return nextSel;
      });
      return next;
    });
  };

  /** Elimina todas las instancias de un template (usado por el checkbox). */
  const removeTemplate = (tplId: number) => {
    setRows((prev) => prev.filter((r) => r.tpl_id !== tplId));
    setSelectionData((prev) => {
      const next = { ...prev };
      delete next[tplId];
      return next;
    });
  };

  /** Reemplaza la plantilla de una fila específica por otra. */
  const replaceRow = (rowId: string, newTpl: SavedChartTemplate) => {
    setRows((prev) => {
      const idx = prev.findIndex((r) => r.rowId === rowId);
      if (idx < 0) return prev;
      if (prev[idx]!.tpl_id === newTpl.id) return prev;
      const next = [...prev];
      next[idx] = {
        rowId,
        tpl_id: newTpl.id,
        // Al reemplazar, recorta/expande slotOverride a la nueva num_scenarios.
        slotOverride: next[idx]!.slotOverride
          ? next[idx]!.slotOverride!.slice(0, newTpl.num_scenarios)
          : null,
      };
      return next;
    });
    setSelectionData((prev) => ({
      ...prev,
      [newTpl.id]: prev[newTpl.id] ?? {
        job_ids: Array.from({ length: newTpl.num_scenarios }, () => null),
      },
    }));
  };

  /** Duplica una fila existente inmediatamente después. */
  const duplicateRow = (rowId: string) => {
    setRows((prev) => {
      const idx = prev.findIndex((r) => r.rowId === rowId);
      if (idx < 0) return prev;
      const src = prev[idx]!;
      const templatesLocal = templates;
      const tpl = templatesLocal.find((t) => t.id === src.tpl_id);
      const numScenarios = tpl?.num_scenarios ?? 1;
      const srcSlots =
        src.slotOverride ??
        Array.from({ length: numScenarios }, (_, i) => i);

      // Máximo escenario ya demandado por cualquier fila (incluyendo overrides);
      // es el límite superior actual de `globalScenarios` implícito.
      let maxSlotAnyRow = 0;
      for (const r of prev) {
        const t = templatesLocal.find((tt) => tt.id === r.tpl_id);
        const slots =
          r.slotOverride ??
          Array.from(
            { length: t?.num_scenarios ?? 1 },
            (_, i) => i,
          );
        for (const s of slots) if (s > maxSlotAnyRow) maxSlotAnyRow = s;
      }
      const capacity = maxSlotAnyRow + 1;

      if (numScenarios === 1) {
        // Usar el primer escenario NO utilizado por otras copias de la MISMA
        // plantilla. Sólo crecer (agregar nuevo slot) si ya están todas tomadas.
        const usedBySameTpl = new Set<number>();
        for (const r of prev) {
          if (r.tpl_id !== src.tpl_id) continue;
          const slots =
            r.slotOverride ??
            Array.from({ length: numScenarios }, (_, i) => i);
          for (const s of slots) usedBySameTpl.add(s);
        }
        let chosen: number | null = null;
        for (let s = 0; s < capacity; s += 1) {
          if (!usedBySameTpl.has(s)) {
            chosen = s;
            break;
          }
        }
        if (chosen == null) chosen = capacity; // crecer solo si todas tomadas
        const clone: RowState = {
          rowId: makeRowId(),
          tpl_id: src.tpl_id,
          slotOverride: [chosen],
        };
        const next = [...prev];
        next.splice(idx + 1, 0, clone);
        return next;
      }

      // Multi-escenario: buscar el primer offset ≥ 0 cuya ventana [off..off+N-1]
      // no coincida con la ventana de otra copia de la misma plantilla. Si todas
      // caben dentro del capacity actual sin crecer, usamos ese offset; si no,
      // extendemos al siguiente bloque libre más allá de capacity.
      const windowsBySameTpl: string[] = [];
      for (const r of prev) {
        if (r.tpl_id !== src.tpl_id) continue;
        const slots =
          r.slotOverride ??
          Array.from({ length: numScenarios }, (_, i) => i);
        windowsBySameTpl.push(slots.slice(0, numScenarios).join(","));
      }
      const maxOffset = Math.max(0, capacity - numScenarios);
      let chosenOffset: number | null = null;
      for (let off = 0; off <= maxOffset; off += 1) {
        const candidate = Array.from(
          { length: numScenarios },
          (_, i) => off + i,
        ).join(",");
        if (!windowsBySameTpl.includes(candidate)) {
          chosenOffset = off;
          break;
        }
      }
      if (chosenOffset == null) chosenOffset = maxOffset + 1;
      const nextSlots = Array.from(
        { length: numScenarios },
        (_, i) => chosenOffset! + i,
      );
      const clone: RowState = {
        rowId: makeRowId(),
        tpl_id: src.tpl_id,
        slotOverride: nextSlots,
      };
      const next = [...prev];
      next.splice(idx + 1, 0, clone);
      return next;
    });
  };

  /** Cambia el slot override de una fila. `slots === null` → volver al default. */
  const setRowSlotOverride = (rowId: string, slots: number[] | null) => {
    setRows((prev) =>
      prev.map((r) =>
        r.rowId === rowId
          ? (slots == null
              ? (() => {
                  const copy = { ...r };
                  delete copy.slotOverride;
                  return copy;
                })()
              : { ...r, slotOverride: slots })
          : r,
      ),
    );
  };

  /** Actualiza report_title de un template en el backend y refresca local. */
  const updateChartReportTitle = async (templateId: number, newTitle: string) => {
    try {
      await savedChartsApi.update(templateId, { report_title: newTitle });
      onTemplatesRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "No se pudo actualizar el título.");
    }
  };

  /** Alterna el tipo de trazo entre columnas apiladas y áreas apiladas. */
  const toggleColumnAreaViewMode = async (tpl: SavedChartTemplate) => {
    const next: "column" | "area" =
      (tpl.view_mode ?? "column") === "area" ? "column" : "area";
    try {
      await savedChartsApi.update(tpl.id, { view_mode: next });
      onTemplatesRefresh();
    } catch (err) {
      alert(
        err instanceof Error
          ? err.message
          : "No se pudo cambiar el tipo de gráfico.",
      );
    }
  };

  const canEditChartReportTitle = (tpl: SavedChartTemplate): boolean =>
    Boolean(tpl.is_owner) || isAdminReports;

  const toggleTemplate = (tpl: SavedChartTemplate) => {
    if (selectedIds.has(tpl.id)) removeTemplate(tpl.id);
    else addTemplate(tpl);
  };


  /** Sube la fila con rowId una posición. */
  const moveRowUp = (rowId: string) => {
    setRows((prev) => {
      const i = prev.findIndex((r) => r.rowId === rowId);
      if (i <= 0) return prev;
      const next = [...prev];
      const tmp = next[i - 1]!;
      next[i - 1] = next[i]!;
      next[i] = tmp;
      return next;
    });
  };
  /** Baja la fila con rowId una posición. */
  const moveRowDown = (rowId: string) => {
    setRows((prev) => {
      const i = prev.findIndex((r) => r.rowId === rowId);
      if (i < 0 || i >= prev.length - 1) return prev;
      const next = [...prev];
      const tmp = next[i + 1]!;
      next[i + 1] = next[i]!;
      next[i] = tmp;
      return next;
    });
  };

  /** Inserta una nueva fila con `newTpl` en la posición `index` (0-based). No
   *  elimina otras instancias del mismo template — permite duplicados. */
  const insertAtIndex = (newTpl: SavedChartTemplate, index: number) => {
    setRows((prev) => {
      const clamped = Math.max(0, Math.min(prev.length, index));
      const next = [...prev];
      next.splice(clamped, 0, { rowId: makeRowId(), tpl_id: newTpl.id });
      return next;
    });
    setSelectionData((prev) => {
      if (prev[newTpl.id]) return prev;
      return {
        ...prev,
        [newTpl.id]: {
          job_ids: Array.from({ length: newTpl.num_scenarios }, () => null),
        },
      };
    });
  };

  /**
   * Navega a la página de resultados para crear una gráfica nueva, con el
   * contexto necesario para que al guardar vuelva al Generador con la gráfica
   * agregada automáticamente en la posición indicada.
   */
  const generatorNavigate = useNavigate();
  const startCreateNewChart = async (insertAfter: number | null) => {
    if (currentReportId == null) {
      alert(
        "Guarda primero este reporte para poder agregar nuevas gráficas a él desde la página de resultados.",
      );
      return;
    }
    const preferred = globalScenarios.filter((j): j is number => j != null);
    const job = pickRepresentativeJob(availableJobs, preferred);
    if (!job) {
      alert(
        "No hay resultados disponibles para crear una gráfica. Lanza una simulación primero.",
      );
      return;
    }
    // Si hay cambios sin guardar en el generador, persistirlos antes de navegar;
    // si no, al volver desde ResultDetailPage los cambios locales se perderían
    // porque el auto-insert se basa en `report.items` del backend.
    if (isDirty) {
      try {
        const updated = await savedChartsApi.updateReport(currentReportId, {
          items: order,
          fmt,
          layout: viewMode === "categories" ? pendingLayout : null,
          scenario_aliases: scenarioAliases.map((s) => s ?? ""),
        });
        setLoadedReport(updated);
        onReportSaved();
      } catch (err) {
        alert(
          err instanceof Error
            ? `No se pudieron guardar los cambios pendientes: ${err.message}`
            : "No se pudieron guardar los cambios pendientes.",
        );
        return;
      }
    }
    const params = new URLSearchParams();
    params.set("addToReport", String(currentReportId));
    params.set("addMode", "generator");
    if (insertAfter != null) params.set("addAfterIdx", String(insertAfter));
    generatorNavigate(`${paths.resultsDetail(job.id)}?${params.toString()}`);
  };

  /** Mueve la fila con rowId a la posición `newIndex` (0-based). */
  const moveRowTo = (rowId: string, newIndex: number) => {
    setRows((prev) => {
      const i = prev.findIndex((r) => r.rowId === rowId);
      if (i < 0) return prev;
      const target = Math.max(0, Math.min(prev.length - 1, newIndex));
      if (target === i) return prev;
      const row = prev[i]!;
      const next = [...prev];
      next.splice(i, 1);
      next.splice(target, 0, row);
      return next;
    });
  };

  // ── Select all / clear all ──
  const selectAll = () => {
    setOrder((prev) => {
      const existing = new Set(prev);
      const next = [...prev];
      for (const tpl of templates) {
        if (!existing.has(tpl.id)) next.push(tpl.id);
      }
      return next;
    });
    setSelectionData((prev) => {
      const next = { ...prev };
      for (const tpl of templates) {
        if (!next[tpl.id]) {
          next[tpl.id] = {
            job_ids: Array.from({ length: tpl.num_scenarios }, () => null),
          };
        }
      }
      return next;
    });
  };
  const clearAll = () => {
    setRows([]);
    setSelectionData({});
  };
  const toggleGroupAll = (
    groupTemplates: SavedChartTemplate[],
    shouldSelect: boolean,
  ) => {
    if (shouldSelect) {
      setOrder((prev) => {
        const existing = new Set(prev);
        const next = [...prev];
        for (const tpl of groupTemplates) {
          if (!existing.has(tpl.id)) next.push(tpl.id);
        }
        return next;
      });
      setSelectionData((prev) => {
        const next = { ...prev };
        for (const tpl of groupTemplates) {
          if (!next[tpl.id]) {
            next[tpl.id] = {
              job_ids: Array.from({ length: tpl.num_scenarios }, () => null),
            };
          }
        }
        return next;
      });
    } else {
      const ids = new Set(groupTemplates.map((t) => t.id));
      setOrder((prev) => prev.filter((id) => !ids.has(id)));
      setSelectionData((prev) => {
        const next = { ...prev };
        for (const id of ids) delete next[id];
        return next;
      });
    }
  };

  // ── Lista ordenada materializada (para render del panel derecho y envío) ──
  /**
   * Cada fila tiene `tpl`, su rowId estable y sus `job_ids` resueltos desde
   * `slotOverride` (índices 0-based en globalScenarios) o, por default, los
   * primeros `num_scenarios` slots globales.
   */
  const orderedItems = useMemo(() => {
    return rows
      .map((row) => {
        const tpl = templates.find((t) => t.id === row.tpl_id);
        if (!tpl) return null;
        const defaultSlots = Array.from(
          { length: tpl.num_scenarios },
          (_, i) => i,
        );
        const slots = row.slotOverride ?? defaultSlots;
        const job_ids: (number | null)[] = slots
          .slice(0, tpl.num_scenarios)
          .map((slotIdx) => globalScenarios[slotIdx] ?? null);
        while (job_ids.length < tpl.num_scenarios) job_ids.push(null);
        return { row, tpl, data: { job_ids } as SelectionData };
      })
      .filter(
        (x): x is { row: RowState; tpl: SavedChartTemplate; data: SelectionData } =>
          x !== null,
      );
  }, [rows, templates, globalScenarios]);

  const allSelected =
    templates.length > 0 && selectedIds.size === templates.length;
  const someSelected = selectedIds.size > 0 && !allSelected;

  // ── Escenarios globales ──
  // N = (mayor num_scenarios entre plantillas) o el mayor índice referenciado
  // por cualquier slotOverride de una fila (+1). Así, si una fila usa slot #4,
  // aparecen 5 campos de escenario global aunque ninguna plantilla pida 5.
  const maxScenariosNeeded = useMemo(() => {
    let max = 0;
    for (const { tpl, row } of orderedItems) {
      if (tpl.num_scenarios > max) max = tpl.num_scenarios;
      if (row.slotOverride && row.slotOverride.length > 0) {
        const rowMax = Math.max(...row.slotOverride) + 1;
        if (rowMax > max) max = rowMax;
      }
    }
    return max;
  }, [orderedItems]);

  // Redimensiona el vector de escenarios globales cuando cambia N.
  useEffect(() => {
    setGlobalScenarios((prev) => {
      if (prev.length === maxScenariosNeeded) return prev;
      const next: (number | null)[] = Array.from(
        { length: maxScenariosNeeded },
        (_, i) => prev[i] ?? null,
      );
      return next;
    });
  }, [maxScenariosNeeded]);

  // Persiste los escenarios elegidos para este reporte (memoria client-side).
  useEffect(() => {
    if (currentReportId == null) return;
    saveReportScenarios(currentReportId, globalScenarios);
  }, [currentReportId, globalScenarios]);

  /** Cambia el alias de un escenario global. */
  const setScenarioAliasAt = (idx: number, value: string) => {
    setScenarioAliases((prev) => {
      const next = [...prev];
      while (next.length <= idx) next.push("");
      next[idx] = value;
      return next;
    });
  };
  /** Etiqueta human-readable del escenario en posición `idx`. */
  const scenarioLabel = (idx: number): string => {
    const a = scenarioAliases[idx]?.trim();
    return a && a.length > 0 ? a : `Escenario ${idx + 1}`;
  };

  const setGlobalScenarioAt = (idx: number, value: number | null) => {
    setGlobalScenarios((prev) => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });
  };

  /** Propaga los escenarios globales a cada plantilla (hasta su num_scenarios). */
  const applyGlobalScenarios = () => {
    setSelectionData((prev) => {
      const next = { ...prev };
      for (const { tpl } of orderedItems) {
        const current = next[tpl.id];
        if (!current) continue;
        const nextJobs = [...current.job_ids];
        for (let i = 0; i < tpl.num_scenarios; i += 1) {
          const g = globalScenarios[i];
          if (g != null) nextJobs[i] = g;
        }
        next[tpl.id] = { ...current, job_ids: nextJobs };
      }
      return next;
    });
  };
  const clearAllAssignedJobs = () => {
    setSelectionData((prev) => {
      const next: Record<number, SelectionData> = {};
      for (const [id, data] of Object.entries(prev)) {
        next[Number(id)] = {
          job_ids: data.job_ids.map(() => null),
        };
      }
      return next;
    });
  };

  const canApplyGlobal =
    maxScenariosNeeded > 0 &&
    globalScenarios.slice(0, maxScenariosNeeded).some((j) => j != null);

  const canGenerate =
    orderedItems.length > 0 &&
    orderedItems.every(({ data }) => data.job_ids.every((j) => j != null));

  /** Compara el estado actual contra el reporte guardado en backend. */
  const isDirty = useMemo(() => {
    if (!loadedReport || !currentReportId) return false;
    const sameItems =
      JSON.stringify(loadedReport.items ?? []) === JSON.stringify(order);
    const sameLayout =
      JSON.stringify(loadedReport.layout ?? null) ===
      JSON.stringify(pendingLayout);
    const sameFmt = loadedReport.fmt === fmt;
    return !(sameItems && sameLayout && sameFmt);
  }, [loadedReport, currentReportId, order, pendingLayout, fmt]);

  /** Navega al dashboard del reporte actual, persistiendo escenarios. */
  const navigateToDashboard = () => {
    if (!currentReportId) return;
    const valid = globalScenarios.filter((j): j is number => j != null);
    if (valid.length > 0) {
      window.sessionStorage.setItem(
        `dashboard-prefill-scenarios:${currentReportId}`,
        JSON.stringify(valid),
      );
    }
    window.location.assign(paths.reportDashboard(currentReportId));
  };

  /** Guarda los cambios actuales del reporte cargado y luego ejecuta cb. */
  const saveCurrentReportAndThen = async (cb: () => void) => {
    if (!currentReportId) return;
    try {
      const updated = await savedChartsApi.updateReport(currentReportId, {
        items: order,
        fmt,
        layout: viewMode === "categories" ? pendingLayout : null,
        scenario_aliases: scenarioAliases.map((s) => s ?? ""),
      });
      setLoadedReport(updated);
      onReportSaved();
      cb();
    } catch (err) {
      alert(
        err instanceof Error ? err.message : "No se pudo guardar el reporte.",
      );
    }
  };

  const handleGenerate = async () => {
    if (!canGenerate) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const reportHasMultiScenarios = maxScenariosNeeded > 1;
      const items: ReportTemplateItem[] = orderedItems.map(({ tpl, row, data }) => {
        const base: ReportTemplateItem = {
          template_id: tpl.id,
          job_ids: data.job_ids.filter((j): j is number => j != null),
        };
        if (tpl.num_scenarios === 1 && reportHasMultiScenarios) {
          const slotIdx =
            row.slotOverride && row.slotOverride.length > 0
              ? row.slotOverride[0]!
              : 0;
          const alias = scenarioAliases[slotIdx]?.trim();
          base.scenario_alias_for_title =
            alias && alias.length > 0 ? alias : `Escenario ${slotIdx + 1}`;
        }
        return base;
      });
      // Si el usuario eligió "Organizar en carpetas", usamos el layout actual
      // (vista Categorías) o derivamos uno automático desde el orden plano.
      let categoriesPayload:
        | Awaited<ReturnType<typeof expandLayoutForExport>>
        | undefined;
      if (organizeFolders) {
        const layoutForExport =
          viewMode === "categories" && pendingLayout
            ? pendingLayout
            : computeAutoLayout(order, templatesByIdLocal);
        categoriesPayload = expandLayoutForExport(
          layoutForExport,
          templatesByIdLocal,
          orderedItems[0]?.data.job_ids.filter(
            (j): j is number => j != null,
          ) ?? [],
        );
        // expandLayoutForExport solo necesita los escenarios globales para
        // resolver job_ids; en el Generador, cada plantilla puede tener sus
        // propios escenarios, así que lo reemplazamos por el mapa real.
        const jobsByTemplate = new Map<number, number[]>(
          orderedItems.map(({ tpl, data }) => [
            tpl.id,
            data.job_ids.filter((j): j is number => j != null),
          ]),
        );
        const reassign = (
          arr: { template_id: number; job_ids: number[] }[],
        ) =>
          arr.map((x) => ({
            template_id: x.template_id,
            job_ids: jobsByTemplate.get(x.template_id) ?? x.job_ids,
          }));
        categoriesPayload = categoriesPayload.map((c) => ({
          ...c,
          items: reassign(c.items),
          subcategories: c.subcategories.map((s) => ({
            ...s,
            items: reassign(s.items),
          })),
        }));
      }
      const overridesForPayload: Record<string, string> = {};
      // Pre-poblar con los aliases: el alias del slot i se aplica al job_id
      // que esté asignado en globalScenarios[i] (si lo hay).
      for (let i = 0; i < globalScenarios.length; i += 1) {
        const jid = globalScenarios[i];
        const alias = scenarioAliases[i]?.trim();
        if (jid != null && alias && alias.length > 0) {
          overridesForPayload[String(jid)] = alias;
        }
      }
      // Los overrides explícitos (rename results) sobreescriben aliases.
      const uniqueJobs = new Set<number>();
      for (const it of items) {
        for (const j of it.job_ids) uniqueJobs.add(j);
      }
      for (const jid of uniqueJobs) {
        const v = (renameOverrides[jid] ?? "").trim();
        if (v) overridesForPayload[String(jid)] = v;
      }
      const hasOverrides = Object.keys(overridesForPayload).length > 0;
      if (yearFrom != null && yearTo != null && yearFrom > yearTo) {
        setGenerateError("El año inicial no puede ser mayor que el año final.");
        return;
      }
      const { blob, filename } = await savedChartsApi.generateReport({
        items,
        fmt,
        ...(organizeFolders && categoriesPayload
          ? { organize_by_category: true, categories: categoriesPayload }
          : {}),
        ...(hasOverrides ? { job_display_overrides: overridesForPayload } : {}),
        ...(yearFrom != null ? { year_from: yearFrom } : {}),
        ...(yearTo != null ? { year_to: yearTo } : {}),
      });
      downloadBlob(blob, filename);
    } catch (err: unknown) {
      let msg = "No se pudo generar el reporte.";
      if (err && typeof err === "object" && "message" in err) {
        msg = (err as { message?: string }).message ?? msg;
      }
      if (err && typeof err === "object" && "details" in err) {
        const resp = (err as { details?: { response?: unknown } }).details?.response;
        if (resp instanceof Blob && resp.type.includes("json")) {
          try {
            const text = await resp.text();
            const parsed = JSON.parse(text);
            if (typeof parsed.detail === "string") msg = parsed.detail;
          } catch {
            /* ignore */
          }
        }
      }
      setGenerateError(msg);
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="animate-pulse rounded-xl border border-slate-800 bg-slate-900/40 h-40" />
    );
  }

  if (templates.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-10 text-center text-sm text-slate-400">
        No hay gráficas guardadas. Guarda al menos una desde la página de resultados
        para poder generar un reporte.
      </div>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
      {/* ── Columna izquierda: catálogo agrupado + selección ordenada ── */}
      <section className="space-y-6 min-w-0">
        <div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="m-0 text-sm font-semibold uppercase tracking-wider text-slate-500">
              1. Selecciona las gráficas a incluir
            </h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={selectAll}
                disabled={allSelected}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-40"
              >
                Seleccionar todas
              </button>
              <button
                type="button"
                onClick={clearAll}
                disabled={orderedItems.length === 0}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-400 hover:bg-slate-800 disabled:opacity-40"
              >
                Limpiar
              </button>
            </div>
          </div>
          <p className="mt-2 mb-0 text-xs text-slate-500">
            {allSelected
              ? `Todas las gráficas (${templates.length}) están seleccionadas.`
              : someSelected
                ? `${orderedItems.length} de ${templates.length} seleccionadas.`
                : `${templates.length} gráficas disponibles en ${groupedTemplates.length} grupos.`}
          </p>
        </div>

        <div className="space-y-3">
          {groupedTemplates.map(({ module, templates: groupTpls }) => {
            const groupSelectedCount = groupTpls.filter((t) =>
              selectedIds.has(t.id),
            ).length;
            const allInGroup = groupSelectedCount === groupTpls.length;
            const someInGroup = groupSelectedCount > 0 && !allInGroup;
            const expanded = expandedGroups[module.id] ?? false;
            return (
              <div
                key={module.id}
                className="rounded-xl border border-slate-800 bg-slate-900/30"
              >
                <header className="flex items-center gap-3 border-b border-slate-800/60 px-4 py-3">
                  <input
                    type="checkbox"
                    aria-label={`Seleccionar todas de ${module.label}`}
                    checked={allInGroup}
                    ref={(el) => {
                      if (el) el.indeterminate = someInGroup;
                    }}
                    onChange={(e) => {
                      const shouldSelect = e.target.checked;
                      const n = groupTpls.length;
                      const msg = shouldSelect
                        ? `¿Agregar las ${n} gráfica${n === 1 ? "" : "s"} de "${module.label}" al reporte?`
                        : `¿Quitar del reporte las ${n} gráfica${n === 1 ? "" : "s"} de "${module.label}"?`;
                      if (!window.confirm(msg)) return;
                      toggleGroupAll(groupTpls, shouldSelect);
                    }}
                    className="h-4 w-4 shrink-0 cursor-pointer rounded border-slate-600 bg-slate-950 text-cyan-500 focus:ring-cyan-500/40"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedGroups((prev) => ({
                        ...prev,
                        [module.id]: !expanded,
                      }))
                    }
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <span className="text-base">{module.emoji}</span>
                    <span className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-100">
                      {module.label}
                    </span>
                    <span className="shrink-0 rounded-full bg-slate-800/80 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      {groupSelectedCount}/{groupTpls.length}
                    </span>
                    <span
                      className={`shrink-0 text-slate-500 transition-transform ${
                        expanded ? "rotate-180" : ""
                      }`}
                      aria-hidden
                    >
                      ▾
                    </span>
                  </button>
                </header>
                {expanded ? (
                  <div className="grid gap-2 p-3">
                    {groupTpls.map((tpl) => {
                      const checked = selectedIds.has(tpl.id);
                      const orderIdx = orderIndexOf(tpl.id);
                      return (
                        <label
                          key={tpl.id}
                          className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
                            checked
                              ? "border-cyan-500/40 bg-cyan-500/5"
                              : "border-slate-800 bg-slate-900/30 hover:bg-slate-900/50"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleTemplate(tpl)}
                            className="mt-1 h-4 w-4 shrink-0 cursor-pointer rounded border-slate-600 bg-slate-950 text-cyan-500 focus:ring-cyan-500/40"
                          />
                          <div className="min-w-0 flex-1 space-y-1">
                            <div className="flex items-center gap-2">
                              {checked ? (
                                <span className="shrink-0 rounded-full bg-cyan-500/20 px-2 py-0.5 text-[10px] font-bold tabular-nums text-cyan-300">
                                  #{orderIdx + 1}
                                </span>
                              ) : null}
                              {tpl.is_favorite ? (
                                <span
                                  className="shrink-0 text-[13px] leading-none"
                                  style={{ color: "#fbbf24" }}
                                  title="Favorita"
                                  aria-label="Favorita"
                                >
                                  ★
                                </span>
                              ) : null}
                              <p className="m-0 text-sm font-semibold text-white break-words">
                                {tpl.name}
                              </p>
                            </div>
                            <p className="m-0 text-xs text-slate-500">
                              {templateSummary(tpl)}
                            </p>
                          </div>
                          <span className="shrink-0 rounded-full border border-slate-700 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                            {tpl.num_scenarios} esc.
                          </span>
                        </label>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        {/* ── 2. Orden + asignación de escenarios ── */}
        {orderedItems.length > 0 ? (
          <section className="space-y-3">
            <div>
              <h2 className="m-0 text-sm font-semibold uppercase tracking-wider text-slate-500">
                2. Ordena y asigna escenarios
              </h2>
              <p className="m-0 mt-1 text-xs text-slate-500">
                Reorganiza las gráficas con las flechas: el número de orden se
                incluye como prefijo en el nombre del archivo (ej.{" "}
                <code className="text-slate-400">01_Capacidad_…</code>,{" "}
                <code className="text-slate-400">02_Emisiones_…</code>).
              </p>
            </div>

            {/* ── Asignación global ── */}
            <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-4 space-y-3">
              <div className="flex flex-col gap-1">
                <p className="m-0 text-sm font-semibold text-emerald-200">
                  Escenarios globales del reporte
                </p>
                <p className="m-0 text-xs text-emerald-200/70">
                  Selecciona una vez los {maxScenariosNeeded}{" "}
                  escenario{maxScenariosNeeded === 1 ? "" : "s"} que usarán todas
                  las gráficas. Al aplicar, cada plantilla consume los primeros{" "}
                  <em>N</em> según sus necesidades (las comparativas usan todos;
                  las de un solo escenario usan solo el Escenario 1).
                </p>
              </div>

              <div
                className="grid gap-2"
                style={{
                  gridTemplateColumns:
                    "repeat(auto-fit, minmax(220px, 1fr))",
                }}
              >
                {Array.from({ length: maxScenariosNeeded }).map((_, idx) => {
                  const value = globalScenarios[idx] ?? null;
                  return (
                    <div key={idx} className="grid gap-1">
                      <label className="grid gap-1">
                        <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300/80">
                          {scenarioLabel(idx)}
                        </span>
                        <JobSelect
                          value={value}
                          onChange={(next) => setGlobalScenarioAt(idx, next)}
                          jobs={availableJobs}
                          loading={loadingJobs}
                        />
                      </label>
                      <input
                        type="text"
                        value={scenarioAliases[idx] ?? ""}
                        onChange={(e) => setScenarioAliasAt(idx, e.target.value)}
                        placeholder={`Alias (opcional) · Escenario ${idx + 1}`}
                        className="rounded border border-emerald-500/30 bg-emerald-500/5 px-2 py-1 text-[11px] text-emerald-100 placeholder:text-emerald-300/40"
                      />
                    </div>
                  );
                })}
              </div>

              <div className="flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  onClick={clearAllAssignedJobs}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800"
                >
                  Limpiar asignaciones
                </button>
                <button
                  type="button"
                  onClick={applyGlobalScenarios}
                  disabled={!canApplyGlobal}
                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Aplicar a todas las gráficas
                </button>
              </div>

              {/* Panel de escenarios predeterminados del reporte */}
              <DefaultScenariosPanel
                reportId={currentReportId}
                current={globalScenarios}
                savedDefaults={
                  Array.isArray(loadedReport?.default_job_ids)
                    ? (loadedReport?.default_job_ids as (number | null)[])
                    : null
                }
                scenarioAliases={scenarioAliases}
                availableJobs={availableJobs}
                onSaved={(nextDefaults) => {
                  setLoadedReport((prev) =>
                    prev ? { ...prev, default_job_ids: nextDefaults } : prev,
                  );
                  onReportSaved();
                  setReportToast(
                    nextDefaults
                      ? "Escenarios predeterminados del reporte actualizados."
                      : "Predeterminados eliminados.",
                  );
                  window.setTimeout(() => setReportToast(null), 3500);
                }}
              />
            </div>

            {/* Toggle Lista / Categorías */}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div
                role="group"
                aria-label="Vista del paso 2"
                className="inline-flex rounded-lg border border-slate-700 bg-slate-900/60 p-0.5"
              >
                <button
                  type="button"
                  onClick={() => setViewMode("list")}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                    viewMode === "list"
                      ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/25"
                      : "text-slate-400"
                  }`}
                >
                  Lista
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("categories")}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                    viewMode === "categories"
                      ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/25"
                      : "text-slate-400"
                  }`}
                >
                  Categorías
                </button>
              </div>
              {viewMode === "categories" && pendingLayout ? (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const fresh = computeAutoLayout(order, templatesByIdLocal);
                      if (
                        confirm(
                          "Reemplazar el layout actual con las categorías por defecto (por módulo)?",
                        )
                      )
                        setPendingLayout(fresh);
                    }}
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800"
                  >
                    Restablecer auto
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (
                        confirm(
                          "Quitar todas las categorías y reagrupar todo en 'Sin asignar'?",
                        )
                      ) {
                        setPendingLayout({
                          categories: [
                            {
                              id: "_unassigned",
                              label: "Sin asignar",
                              items: [...order],
                              subcategories: [],
                            },
                          ],
                        });
                      }
                    }}
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-400 hover:bg-slate-800"
                  >
                    Vaciar categorías
                  </button>
                </div>
              ) : null}
            </div>

            {viewMode === "list" ? (
              <ol className="list-none p-0 m-0">
                {orderedItems.map(({ row, tpl }, idx) => {
                  const isFirst = idx === 0;
                  const isLast = idx === orderedItems.length - 1;
                  const defaultSlots = Array.from(
                    { length: tpl.num_scenarios },
                    (_, i) => i,
                  );
                  const effectiveSlots = row.slotOverride ?? defaultSlots;
                  return (
                    <div key={row.rowId}>
                      {idx === 0 ? (
                        <InsertChartHere
                          onClick={() => setInsertAfterIdx(-1)}
                          label="Insertar gráfica al inicio"
                        />
                      ) : null}
                    <li
                      data-row-id={row.rowId}
                      className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3"
                    >
                      <div className="flex flex-wrap items-start gap-3">
                        <PositionInput
                          index={idx}
                          total={orderedItems.length}
                          onSubmit={(newIndex) => moveRowTo(row.rowId, newIndex)}
                        />
                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            {tpl.is_favorite ? (
                              <span style={{ color: "#fbbf24" }} className="text-sm leading-none">★</span>
                            ) : null}
                            <p className="m-0 text-sm font-semibold text-white break-words">
                              {tpl.report_title || tpl.name}
                            </p>
                          </div>
                          {tpl.report_title ? (
                            <p className="m-0 text-[11px] text-slate-500 break-words">
                              <span className="text-slate-600">Gráfica oficial:</span>{" "}
                              {tpl.name}
                            </p>
                          ) : null}
                          <p className="m-0 text-xs text-slate-500">
                            {templateSummary(tpl)}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-1 flex-wrap">
                          <button
                            type="button"
                            onClick={() => setPreviewTemplateInline(tpl)}
                            title="Visualizar con los escenarios seleccionados"
                            className="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-emerald-500/40 px-2 text-[11px] font-semibold text-emerald-300 hover:bg-emerald-500/10"
                          >
                            <IconEye /> Visualizar
                          </button>
                          <button
                            type="button"
                            onClick={() => setReplaceTargetId(row.rowId)}
                            title="Reemplazar por otra gráfica guardada"
                            className="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-indigo-500/40 px-2 text-[11px] font-semibold text-indigo-300 hover:bg-indigo-500/10"
                          >
                            <IconSwap /> Reemplazar
                          </button>
                          <button
                            type="button"
                            onClick={() => duplicateRow(row.rowId)}
                            title="Duplicar esta fila (misma gráfica, otros escenarios)"
                            className="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-slate-600 px-2 text-[11px] font-semibold text-slate-300 hover:bg-slate-800"
                          >
                            ⧉ Duplicar
                          </button>
                          {(tpl.view_mode === "column" ||
                            tpl.view_mode === "area" ||
                            tpl.view_mode == null) &&
                          tpl.compare_mode === "off" &&
                          canEditChartReportTitle(tpl) ? (
                            <button
                              type="button"
                              onClick={() => toggleColumnAreaViewMode(tpl)}
                              title={
                                tpl.view_mode === "area"
                                  ? "Cambiar a columnas apiladas"
                                  : "Cambiar a áreas apiladas"
                              }
                              className="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-amber-500/40 px-2 text-[11px] font-semibold text-amber-300 hover:bg-amber-500/10"
                            >
                              {tpl.view_mode === "area" ? "▦ A columnas" : "▲ A áreas"}
                            </button>
                          ) : null}
                          {canEditChartReportTitle(tpl) ? (
                            <button
                              type="button"
                              onClick={() => {
                                setTitleEditingId(tpl.id);
                                setTitleDraft(tpl.report_title ?? "");
                              }}
                              title="Editar título usado al renderizar en reportes"
                              className="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-cyan-500/40 px-2 text-[11px] font-semibold text-cyan-300 hover:bg-cyan-500/10"
                            >
                              <IconPencil /> Título
                            </button>
                          ) : null}
                          <button
                            type="button"
                            onClick={(e) => anchorAndRun(e, row.rowId, () => moveRowUp(row.rowId))}
                            disabled={isFirst}
                            title="Subir"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            onClick={(e) => anchorAndRun(e, row.rowId, () => moveRowDown(row.rowId))}
                            disabled={isLast}
                            title="Bajar"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            ↓
                          </button>
                          <button
                            type="button"
                            onClick={() => removeRow(row.rowId)}
                            title="Quitar esta fila del reporte"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-rose-500/40 text-rose-300 hover:bg-rose-500/10"
                          >
                            ×
                          </button>
                        </div>
                      </div>
                      {/* Chip siempre visible: qué escenarios usa; botón "Asignar" abre el picker */}
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-900/60 px-2 py-0.5 text-[10px] font-semibold text-slate-300">
                          <span className="text-slate-500 uppercase tracking-wider">
                            Escenario{effectiveSlots.length === 1 ? "" : "s"}:
                          </span>
                          {effectiveSlots
                            .map((s, i) => (
                              <span key={i} className="text-cyan-300">
                                {scenarioLabel(s)}
                              </span>
                            ))
                            .reduce<React.ReactNode[]>((acc, el, i) => {
                              if (i > 0)
                                acc.push(
                                  <span key={`sep-${i}`} className="text-slate-600">
                                    ·
                                  </span>,
                                );
                              acc.push(el);
                              return acc;
                            }, [])}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            setEditingSlotsRowId((cur) =>
                              cur === row.rowId ? null : row.rowId,
                            )
                          }
                          className="inline-flex h-7 items-center justify-center gap-1 rounded-md border border-slate-700 px-2 text-[10px] font-semibold text-slate-300 hover:bg-slate-800"
                        >
                          {editingSlotsRowId === row.rowId ? "Ocultar asignación" : "Asignar escenarios"}
                        </button>
                      </div>
                      {editingSlotsRowId === row.rowId ? (
                        <RowScenarioPicker
                          tpl={tpl}
                          effectiveSlots={effectiveSlots}
                          globalScenariosLen={Math.max(
                            maxScenariosNeeded,
                            globalScenarios.length,
                            tpl.num_scenarios,
                          )}
                          isOverride={Boolean(row.slotOverride)}
                          onChange={(slots) => setRowSlotOverride(row.rowId, slots)}
                        />
                      ) : null}
                      {titleEditingId === tpl.id ? (
                        <div className="rounded-md border border-cyan-500/30 bg-cyan-500/5 px-3 py-2 space-y-1">
                          <p className="m-0 text-[10px] text-slate-400">
                            Título usado al renderizar en reportes (vacío → título automático):
                          </p>
                          <div className="flex gap-1">
                            <input
                              type="text"
                              value={titleDraft}
                              onChange={(e) => setTitleDraft(e.target.value)}
                              placeholder={tpl.name}
                              className="flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                            />
                            <button
                              type="button"
                              onClick={async () => {
                                await updateChartReportTitle(tpl.id, titleDraft);
                                setTitleEditingId(null);
                              }}
                              className="rounded bg-cyan-600 px-2 py-1 text-[10px] font-semibold text-white hover:bg-cyan-500"
                            >
                              Guardar
                            </button>
                            <button
                              type="button"
                              onClick={() => setTitleEditingId(null)}
                              className="rounded border border-slate-700 px-2 py-1 text-[10px] font-semibold text-slate-300 hover:bg-slate-800"
                            >
                              Cancelar
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </li>
                      <InsertChartHere
                        onClick={() => setInsertAfterIdx(idx)}
                        label={
                          isLast
                            ? "Agregar gráfica al final"
                            : "Insertar gráfica aquí"
                        }
                      />
                    </div>
                  );
                })}
              </ol>
            ) : pendingLayout ? (
              <CategoriesPanel
                layout={pendingLayout}
                onLayoutChange={setPendingLayout}
                items={order}
                onItemsChange={(nextIds: number[]) => setOrder(() => nextIds)}
                accessibleTemplates={templates}
              />
            ) : (
              <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-6 space-y-3">
                <p className="m-0 text-sm font-semibold text-slate-200">
                  ¿Cómo quieres organizar las categorías?
                </p>
                <p className="m-0 text-xs text-slate-500">
                  Elige una opción para empezar. Después podrás renombrar,
                  agregar subcategorías y mover gráficas entre categorías.
                </p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setPendingLayout(
                        computeAutoLayout(order, templatesByIdLocal),
                      )
                    }
                    className="rounded-lg bg-cyan-600 px-4 py-2 text-xs font-semibold text-white hover:bg-cyan-500"
                  >
                    Crear con categorías por defecto
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setPendingLayout({
                        categories: [
                          {
                            id: "_unassigned",
                            label: "Sin asignar",
                            items: [...order],
                            subcategories: [],
                          },
                        ],
                      })
                    }
                    className="rounded-lg border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800"
                  >
                    Empezar en blanco
                  </button>
                </div>
              </div>
            )}
          </section>
        ) : null}
      </section>

      {/* ── Columna derecha: resumen + generar ── */}
      <aside className="h-fit rounded-xl border border-slate-800 bg-slate-900/40 p-5 space-y-5 lg:sticky lg:top-6">
        <div>
          <h2 className="m-0 text-sm font-semibold uppercase tracking-wider text-slate-500">
            Resumen del reporte
          </h2>
          <p className="m-0 mt-1 text-xs text-slate-500">
            Gráficas en el reporte:{" "}
            <strong className="text-slate-200">{orderedItems.length}</strong>
          </p>
          <p className="m-0 mt-1 text-xs text-slate-500">
            Se exportarán numeradas{" "}
            <code className="text-slate-400">01_</code>,{" "}
            <code className="text-slate-400">02_</code>, … en el orden mostrado.
          </p>
        </div>

        <div>
          <p className="m-0 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Formato de imagen
          </p>
          <div className="mt-2 inline-flex rounded-lg border border-slate-800 bg-slate-950/40 p-0.5">
            {(["png", "svg"] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFmt(f)}
                className={`rounded-md px-3 py-2 text-xs font-semibold transition-colors ${
                  fmt === f
                    ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/25"
                    : "text-slate-500 hover:text-slate-300 border border-transparent"
                }`}
              >
                {f.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <label className="flex items-start gap-2 text-xs text-slate-300">
          <input
            type="checkbox"
            checked={organizeFolders}
            onChange={(e) => setOrganizeFolders(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            <strong>Organizar en carpetas por categoría</strong>
            <br />
            <span className="text-slate-500 text-[11px]">
              {viewMode === "categories" && pendingLayout
                ? "Usa el layout que estás editando."
                : "Si no estás en vista Categorías, se agrupa automáticamente por módulo."}
            </span>
          </span>
        </label>

        {globalScenarios.some((j) => j != null) ? (
          <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-3 space-y-2">
            <button
              type="button"
              onClick={() => setRenameOpen((v) => !v)}
              className="flex w-full items-center justify-between gap-2 text-left"
            >
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Renombrar resultados (solo este export)
              </span>
              <span className={`text-slate-500 transition-transform ${renameOpen ? "rotate-180" : ""}`}>▾</span>
            </button>
            {renameOpen ? (
              <div className="space-y-1.5">
                <p className="m-0 text-[10px] text-slate-500 leading-snug">
                  Cambia cómo aparece cada resultado en los títulos de las imágenes. No modifica el escenario ni el alias guardado del resultado.
                </p>
                {globalScenarios.map((jid, idx) => {
                  if (jid == null) return null;
                  const job = availableJobs.find((j) => j.id === jid);
                  const base =
                    (job?.display_name?.trim() || job?.scenario_name || `Job ${jid}`);
                  return (
                    <label key={`${idx}-${jid}`} className="grid gap-0.5">
                      <span className="text-[10px] text-slate-500">
                        Escenario {idx + 1} · <span className="text-slate-400">{base}</span>
                      </span>
                      <input
                        type="text"
                        value={renameOverrides[jid] ?? ""}
                        onChange={(e) =>
                          setRenameOverrides((prev) => ({ ...prev, [jid]: e.target.value }))
                        }
                        placeholder={base}
                        className="rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-100 placeholder:text-slate-600"
                      />
                    </label>
                  );
                })}
              </div>
            ) : null}
          </div>
        ) : null}

        {/* Rango de años (solo este export) */}
        <div className="rounded-lg border border-cyan-500/25 bg-cyan-500/5 p-3 space-y-2">
          <div>
            <p className="m-0 text-[11px] font-semibold uppercase tracking-wider text-cyan-300/80">
              Rango de años (opcional)
            </p>
            <p className="m-0 text-[10px] text-cyan-200/70">
              Filtra los años incluidos en el ZIP. Vacío = todos los años.
            </p>
          </div>
          <div className="flex items-end gap-2">
            <label className="grid gap-0.5 flex-1">
              <span className="text-[10px] text-cyan-300/80">Desde</span>
              <input
                type="number"
                inputMode="numeric"
                min={1900}
                max={2200}
                value={yearFrom ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setYearFrom(v === "" ? null : Number(v));
                }}
                placeholder="todos"
                className="rounded border border-cyan-500/40 bg-slate-950/60 px-2 py-1 text-xs text-cyan-100 placeholder:text-cyan-700"
              />
            </label>
            <label className="grid gap-0.5 flex-1">
              <span className="text-[10px] text-cyan-300/80">Hasta</span>
              <input
                type="number"
                inputMode="numeric"
                min={1900}
                max={2200}
                value={yearTo ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setYearTo(v === "" ? null : Number(v));
                }}
                placeholder="todos"
                className="rounded border border-cyan-500/40 bg-slate-950/60 px-2 py-1 text-xs text-cyan-100 placeholder:text-cyan-700"
              />
            </label>
          </div>
        </div>

        {generateError ? (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            {generateError}
          </div>
        ) : null}

        <button
          type="button"
          onClick={handleGenerate}
          disabled={!canGenerate || generating}
          className="w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {generating ? "Generando reporte…" : "Descargar reporte (.zip)"}
        </button>
        {!canGenerate && orderedItems.length > 0 ? (
          <p className="m-0 text-[11px] text-slate-500">
            Asigna un escenario en cada slot antes de generar.
          </p>
        ) : null}

        {/* ── Guardar el reporte como plantilla reutilizable ── */}
        <div className="border-t border-slate-800 pt-4 space-y-2">
          <p className="m-0 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Guardar este reporte
          </p>
          <p className="m-0 text-[11px] text-slate-500 leading-relaxed">
            Guarda la selección y el orden actuales con un nombre. Podrás
            recargarla más tarde desde "Mis reportes guardados".
          </p>
          {currentReportId ? (
            <p className="m-0 text-[10px] text-emerald-300/80">
              Editando reporte guardado #{currentReportId}.
            </p>
          ) : null}
          <button
            type="button"
            disabled={orderedItems.length === 0}
            onClick={() => setShowSaveReportModal(true)}
            className="w-full rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {currentReportId ? "Guardar cambios / Guardar como…" : "Guardar reporte…"}
          </button>
        </div>

        {/* ── Abrir el dashboard del reporte (requiere reporte guardado) ── */}
        <div className="border-t border-slate-800 pt-4 space-y-2">
          <p className="m-0 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Visualizar dashboard
          </p>
          <p className="m-0 text-[11px] text-slate-500 leading-relaxed">
            Abre el reporte como dashboard interactivo agrupado por categorías.
            Los escenarios globales actuales se aplicarán automáticamente.
          </p>
          <button
            type="button"
            disabled={!currentReportId}
            onClick={() => {
              if (!currentReportId) return;
              if (isDirty) {
                setUnsavedDashboardPrompt(true);
                return;
              }
              navigateToDashboard();
            }}
            title={
              currentReportId
                ? "Abrir dashboard"
                : "Guarda el reporte primero para abrir su dashboard"
            }
            className="w-full rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Ver dashboard del reporte
          </button>
          {!currentReportId ? (
            <p className="m-0 text-[10px] text-slate-500">
              Guarda el reporte para habilitar el dashboard.
            </p>
          ) : isDirty ? (
            <p className="m-0 text-[10px] text-amber-400/80">
              Hay cambios sin guardar.
            </p>
          ) : null}
        </div>
      </aside>

      <SaveReportModal
        open={showSaveReportModal}
        onClose={() => setShowSaveReportModal(false)}
        items={order}
        fmt={fmt}
        existingReportId={currentReportId}
        existingReports={savedReports}
        layout={viewMode === "categories" ? pendingLayout : null}
        scenarioAliases={scenarioAliases}
        defaultJobIds={globalScenarios}
        yearFrom={yearFrom}
        yearTo={yearTo}
        onSaved={(saved) => {
          setCurrentReportId(saved.id);
          setLoadedReport(saved);
          onReportSaved();
          setShowSaveReportModal(false);
          setReportToast(`Reporte "${saved.name}" guardado.`);
          window.setTimeout(() => setReportToast(null), 3500);
        }}
      />

      {reportToast ? (
        <div
          className="fixed bottom-6 right-6 z-[300] rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-200 shadow-2xl backdrop-blur-md"
          role="status"
        >
          {reportToast}
        </div>
      ) : null}

      {unsavedDashboardPrompt ? (
        <UnsavedChangesPrompt
          onCancel={() => setUnsavedDashboardPrompt(false)}
          onSaveAndGo={async () => {
            setUnsavedDashboardPrompt(false);
            await saveCurrentReportAndThen(navigateToDashboard);
          }}
          onDiscardAndGo={() => {
            setUnsavedDashboardPrompt(false);
            navigateToDashboard();
          }}
        />
      ) : null}

      <PreviewChartModal
        open={previewTemplateInline !== null}
        onClose={() => setPreviewTemplateInline(null)}
        template={previewTemplateInline}
        availableJobs={availableJobs}
        loadingJobs={loadingJobs}
        initialJobIds={
          previewTemplateInline
            ? (selectionData[previewTemplateInline.id]?.job_ids ?? []).filter(
                (j): j is number => j != null,
              )
            : []
        }
        scenarioAliasSuffix={(() => {
          const tpl = previewTemplateInline;
          if (!tpl || tpl.num_scenarios !== 1) return undefined;
          const totalSlots = Math.max(
            scenarioAliases.length,
            globalScenarios.length,
          );
          if (totalSlots <= 1) return undefined;
          const row = rows.find((r) => r.tpl_id === tpl.id);
          const slotIdx =
            row?.slotOverride && row.slotOverride.length > 0
              ? row.slotOverride[0]!
              : 0;
          const alias = scenarioAliases[slotIdx]?.trim();
          return alias && alias.length > 0 ? alias : `Escenario ${slotIdx + 1}`;
        })()}
        scenarioNames={(() => {
          const tpl = previewTemplateInline;
          if (!tpl) return undefined;
          const row = rows.find((r) => r.tpl_id === tpl.id);
          const slots =
            row?.slotOverride && row.slotOverride.length > 0
              ? row.slotOverride.slice(0, tpl.num_scenarios)
              : Array.from({ length: tpl.num_scenarios }, (_, i) => i);
          return slots.map((s) => {
            const a = scenarioAliases[s]?.trim();
            return a && a.length > 0 ? a : `Escenario ${s + 1}`;
          });
        })()}
      />

      <ChartPickerModal
        open={replaceTargetId != null}
        onClose={() => setReplaceTargetId(null)}
        title="Reemplazar gráfica"
        templates={templates}
        onPick={(tpl) => {
          if (replaceTargetId != null) replaceRow(replaceTargetId, tpl);
          setReplaceTargetId(null);
        }}
      />

      <ChartPickerModal
        open={insertAfterIdx != null}
        onClose={() => setInsertAfterIdx(null)}
        title="Agregar gráfica"
        templates={templates}
        excludeIds={new Set(order)}
        onPick={(tpl) => {
          if (insertAfterIdx != null) {
            insertAtIndex(tpl, insertAfterIdx + 1);
          }
          setInsertAfterIdx(null);
        }}
        onCreateNew={
          currentReportId != null
            ? () => startCreateNewChart(insertAfterIdx ?? null)
            : undefined
        }
      />
    </div>
  );
}

// ─── Modal: cambios sin guardar antes de ir al dashboard ────────────────────

function UnsavedChangesPrompt({
  onCancel,
  onSaveAndGo,
  onDiscardAndGo,
}: {
  onCancel: () => void;
  onSaveAndGo: () => void;
  onDiscardAndGo: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onCancel}
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
          width: "min(480px, 100%)",
          background: "rgba(11,18,32,0.98)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 14,
          padding: 20,
          display: "grid",
          gap: 12,
        }}
      >
        <h3 className="m-0 text-lg font-semibold text-white">
          Tienes cambios sin guardar
        </h3>
        <p className="m-0 text-sm text-slate-300">
          El reporte tiene modificaciones que aún no se han guardado en el
          servidor. ¿Cómo quieres continuar al dashboard?
        </p>
        <div className="flex flex-wrap justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onDiscardAndGo}
            className="rounded-lg border border-amber-500/40 px-3 py-2 text-xs font-semibold text-amber-300 hover:bg-amber-500/10"
          >
            Ir sin guardar
          </button>
          <button
            type="button"
            onClick={onSaveAndGo}
            className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-500"
          >
            Guardar y abrir dashboard
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Modal: guardar reporte ─────────────────────────────────────────────────

function SaveReportModal({
  open,
  onClose,
  items,
  fmt,
  existingReportId,
  existingReports,
  onSaved,
  layout,
  scenarioAliases,
  defaultJobIds,
  yearFrom,
  yearTo,
}: {
  open: boolean;
  onClose: () => void;
  items: number[];
  fmt: "png" | "svg";
  existingReportId: number | null;
  existingReports: SavedReport[];
  onSaved: (saved: SavedReport) => void;
  /** Layout en construcción (vista Categorías). null = modo auto en el dashboard. */
  layout?: ReportLayout | null;
  /** Aliases por escenario global. */
  scenarioAliases?: string[];
  /** Job IDs actualmente seleccionados; se persisten como default al guardar. */
  defaultJobIds?: (number | null)[];
  /** Rango de años seleccionado; se persiste con el reporte. */
  yearFrom?: number | null;
  yearTo?: number | null;
}) {
  const existing = existingReportId
    ? existingReports.find((r) => r.id === existingReportId) ?? null
    : null;
  const [mode, setMode] = useState<"update" | "new">(existing ? "update" : "new");
  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setMode(existing ? "update" : "new");
    setName(existing?.name ?? "");
    setDescription(existing?.description ?? "");
    setError(null);
  }, [open, existing]);

  const handleSave = async () => {
    const trimmed = name.trim();
    if (mode === "new" && !trimmed) {
      setError("Asigna un nombre al reporte.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (mode === "update" && existing) {
        const updated = await savedChartsApi.updateReport(existing.id, {
          name: trimmed || existing.name,
          description: description.trim() || null,
          fmt,
          items,
          layout: layout ?? null,
          scenario_aliases: (scenarioAliases ?? []).map((s) => s ?? ""),
          default_job_ids: defaultJobIds ?? null,
          year_from: yearFrom ?? null,
          year_to: yearTo ?? null,
        });
        onSaved(updated);
      } else {
        const created = await savedChartsApi.createReport({
          name: trimmed,
          description: description.trim() || null,
          fmt,
          items,
          layout: layout ?? null,
          scenario_aliases: (scenarioAliases ?? []).map((s) => s ?? ""),
          default_job_ids: defaultJobIds ?? null,
          year_from: yearFrom ?? null,
          year_to: yearTo ?? null,
        });
        onSaved(created);
      }
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? (err as { message?: string }).message ?? "Error guardando el reporte."
          : "Error guardando el reporte.";
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

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
        zIndex: 200,
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
          gap: 14,
        }}
      >
        <h3 className="m-0 text-lg font-semibold text-white">
          {mode === "update" ? "Actualizar reporte guardado" : "Guardar reporte"}
        </h3>

        {existing ? (
          <div
            role="group"
            aria-label="Modo de guardado"
            className="inline-flex rounded-lg border border-slate-700 bg-slate-900/60 p-0.5"
          >
            <button
              type="button"
              onClick={() => setMode("update")}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                mode === "update"
                  ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/25"
                  : "text-slate-400"
              }`}
            >
              Actualizar "{existing.name}"
            </button>
            <button
              type="button"
              onClick={() => setMode("new")}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                mode === "new"
                  ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/25"
                  : "text-slate-400"
              }`}
            >
              Guardar como nuevo
            </button>
          </div>
        ) : null}

        <label className="grid gap-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Nombre
          </span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={255}
            className="rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100"
          />
        </label>

        <label className="grid gap-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Descripción
          </span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            className="rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 resize-y"
          />
        </label>

        <p className="m-0 text-[11px] text-slate-500">
          Se guardan {items.length} gráfica{items.length === 1 ? "" : "s"} en el
          orden actual, formato {fmt.toUpperCase()}. Los escenarios se eligen al
          generar el reporte (no se persisten).
        </p>

        {error ? (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            {error}
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={saving}>
            {saving ? "Guardando…" : "Guardar"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Tab: Mis reportes guardados ────────────────────────────────────────────

function SavedReportsTab({
  reports,
  loading,
  onRefresh,
  onLoadReport,
  templates,
  onTemplatesRefresh,
  canManageOfficial,
  isAdminReports,
  includeOthersPrivate,
  onToggleIncludeOthersPrivate,
  onGoToGenerator,
}: {
  reports: SavedReport[];
  loading: boolean;
  onRefresh: () => void;
  onLoadReport: (r: SavedReport) => void;
  templates: SavedChartTemplate[];
  onTemplatesRefresh: () => void;
  canManageOfficial: boolean;
  isAdminReports: boolean;
  includeOthersPrivate: boolean;
  onToggleIncludeOthersPrivate: (v: boolean) => void;
  onGoToGenerator: () => void;
}) {
  const templatesById = useMemo(
    () => new Map(templates.map((t) => [t.id, t])),
    [templates],
  );
  const [showOnlyFavorites, setShowOnlyFavorites] = useState(false);
  const [copyingId, setCopyingId] = useState<number | null>(null);

  /**
   * Reglas de edición en el frontend (el backend es la autoridad):
   * - full edit (nombre, descripción, visibilidad, items, layout): owner, o admin_reports si es oficial.
   * - admin_reports sobre reporte público NO oficial: solo puede renombrar y marcar/desmarcar oficial.
   * - admin_reports sobre reporte privado de otros: solo lectura + copia.
   */
  const canFullEdit = (r: SavedReport): boolean => {
    if (r.is_owner ?? true) return true;
    if (isAdminReports && (r.is_official ?? false)) return true;
    return false;
  };
  const canRenameOnly = (r: SavedReport): boolean => {
    if (canFullEdit(r)) return false;
    return isAdminReports && (r.is_public ?? false) && !(r.is_official ?? false);
  };
  const canDelete = (r: SavedReport): boolean => {
    if (r.is_owner ?? true) return true;
    if (isAdminReports && (r.is_official ?? false)) return true;
    return false;
  };

  const handleDelete = async (r: SavedReport) => {
    if (!confirm(`¿Eliminar el reporte "${r.name}"?`)) return;
    try {
      await savedChartsApi.deleteReport(r.id);
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "No se pudo eliminar.");
    }
  };

  const toggleVisibility = async (r: SavedReport) => {
    try {
      await savedChartsApi.updateReport(r.id, { is_public: !(r.is_public ?? false) });
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "No se pudo cambiar la visibilidad.");
    }
  };

  const toggleOfficial = async (r: SavedReport) => {
    try {
      await savedChartsApi.updateReport(r.id, { is_official: !(r.is_official ?? false) });
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "No se pudo cambiar el estado oficial.");
    }
  };

  const toggleFavorite = async (r: SavedReport, next: boolean) => {
    try {
      await savedChartsApi.setReportFavorite(r.id, next);
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "No se pudo cambiar favorito.");
    }
  };

  const handleCopy = async (r: SavedReport) => {
    if (copyingId != null) return;
    setCopyingId(r.id);
    try {
      const copy = await savedChartsApi.copyReport(r.id);
      onRefresh();
      onTemplatesRefresh();
      alert(
        `Se creó la copia "${copy.name}" (privada) en tus reportes guardados. Las gráficas que no tenías fueron copiadas también.`,
      );
    } catch (err) {
      alert(err instanceof Error ? err.message : "No se pudo copiar el reporte.");
    } finally {
      setCopyingId(null);
    }
  };

  if (loading) {
    return (
      <div className="animate-pulse rounded-xl border border-slate-800 bg-slate-900/40 h-40" />
    );
  }

  if (reports.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-10 text-center">
        <h3 className="mb-2 text-lg font-semibold text-slate-200">
          Aún no tienes reportes guardados
        </h3>
        <p className="m-0 mx-auto max-w-md text-sm text-slate-500">
          Desde el <em>Generador de reporte</em>, selecciona y organiza las
          gráficas y luego usa "Guardar reporte" para almacenar la colección
          con un nombre.
        </p>
        <button
          type="button"
          onClick={onGoToGenerator}
          className="mt-5 inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500"
        >
          Ir al Generador de reporte →
        </button>
      </div>
    );
  }

  const visibleReports = showOnlyFavorites
    ? reports.filter((r) => r.is_favorite === true)
    : reports;

  return (
    <>
    <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="m-0 text-xs text-slate-500">
          {reports.length} reporte{reports.length === 1 ? "" : "s"} accesible
          {reports.length === 1 ? "" : "s"}.
        </p>
        <button
          type="button"
          onClick={() => setShowOnlyFavorites((v) => !v)}
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold transition-colors ${
            showOnlyFavorites
              ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
              : "border-slate-700 bg-slate-900/40 text-slate-400 hover:text-slate-200"
          }`}
          title="Mostrar solo reportes marcados como favoritos"
        >
          <span style={{ color: showOnlyFavorites ? "#fbbf24" : undefined }}>★</span>
          Solo favoritos
        </button>
        {isAdminReports ? (
          <label className="inline-flex items-center gap-2 text-xs text-slate-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={includeOthersPrivate}
              onChange={(e) => onToggleIncludeOthersPrivate(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900"
            />
            Ver reportes privados de otros usuarios
          </label>
        ) : null}
      </div>
    </div>
    {showOnlyFavorites && visibleReports.length === 0 ? (
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-6 text-center text-sm text-slate-500">
        No tienes reportes marcados como favoritos todavía.
      </div>
    ) : null}
    <div className="grid gap-3">
      {visibleReports.map((r) => {
        const missing = r.items.filter((id) => !templatesById.has(id));
        const fullEdit = canFullEdit(r);
        const renameOnly = canRenameOnly(r);
        const officialToggleEnabled = fullEdit || renameOnly;
        const visibilityToggleEnabled = fullEdit;
        const deleteEnabled = canDelete(r);
        const isOwner = r.is_owner ?? true;
        return (
          <div
            key={r.id}
            className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 space-y-3"
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <FavoriteStar
                    isFavorite={r.is_favorite ?? false}
                    onToggle={(next) => toggleFavorite(r, next)}
                  />
                  <h3 className="m-0 text-base font-semibold text-white break-words">
                    {r.name}
                  </h3>
                  <VisibilityChip
                    isPublic={r.is_public ?? false}
                    canEdit={visibilityToggleEnabled}
                    onToggle={() => toggleVisibility(r)}
                  />
                  <OfficialChip
                    isOfficial={r.is_official ?? false}
                    canEdit={officialToggleEnabled && canManageOfficial}
                    onToggle={() => toggleOfficial(r)}
                  />
                  {!isOwner ? (
                    <span className="rounded-full border border-slate-700 bg-slate-800/60 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      de {r.owner_username ?? "otro"}
                    </span>
                  ) : null}
                  {!isOwner && !fullEdit ? (
                    <span className="rounded-full border border-slate-700 bg-slate-800/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      solo lectura
                    </span>
                  ) : null}
                </div>
                <p className="m-0 text-xs text-slate-500">
                  {r.items.length} gráfica{r.items.length === 1 ? "" : "s"} · formato{" "}
                  {r.fmt.toUpperCase()} · actualizado {formatDate(r.updated_at)}
                </p>
                {r.description ? (
                  <p className="m-0 whitespace-pre-wrap break-words text-sm text-slate-300">
                    {r.description}
                  </p>
                ) : null}
                {missing.length > 0 ? (
                  <p className="m-0 text-[11px] text-amber-300">
                    ⚠ {missing.length} gráfica
                    {missing.length === 1 ? "" : "s"} referenciada
                    {missing.length === 1 ? "" : "s"} ya no existe
                    {missing.length === 1 ? "" : "n"}; se omitirán al cargar.
                  </p>
                ) : null}
              </div>
              <div className="flex shrink-0 gap-2 flex-wrap">
                <Link
                  to={paths.reportDashboard(r.id)}
                  className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20 no-underline"
                  title="Abrir dashboard interactivo"
                >
                  Ver dashboard
                </Link>
                {fullEdit ? (
                  <button
                    type="button"
                    onClick={() => onLoadReport(r)}
                    className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/20"
                    title="Cargar en el generador"
                  >
                    Cargar → Generador
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => handleCopy(r)}
                  disabled={copyingId === r.id}
                  className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-3 py-1.5 text-xs font-semibold text-indigo-300 hover:bg-indigo-500/20 disabled:opacity-60"
                  title="Crear una copia privada en tu cuenta"
                >
                  {copyingId === r.id ? "Copiando…" : "Copiar"}
                </button>
                {deleteEnabled ? (
                  <button
                    type="button"
                    onClick={() => handleDelete(r)}
                    className="rounded-lg border border-rose-500/40 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-500/10"
                  >
                    Eliminar
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}
    </div>
    {visibleReports.length > 0 ? (
      <div className="mt-5 flex justify-center">
        <button
          type="button"
          onClick={onGoToGenerator}
          className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-5 py-2.5 text-sm font-semibold text-cyan-200 hover:bg-cyan-500/20 transition-colors"
          title="Abrir el Generador de reporte para crear un reporte nuevo"
        >
          <span className="text-base leading-none">＋</span>
          Crear un nuevo reporte
        </button>
      </div>
    ) : null}
    </>
  );
}
