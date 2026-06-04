/**
 * Administración de configuración runtime del sistema.
 */
import { useCallback, useEffect, useState } from "react";

import { useToast } from "@/app/providers/useToast";
import {
  systemSettingsApi,
  type HipoParallelType,
  type HighsMethod,
  type OnOffChoose,
  type SolverSettings,
  type SolverSettingsUpdate,
} from "@/features/systemSettings/api/systemSettingsApi";
import { Button } from "@/shared/components/Button";
import { Card } from "@/shared/components/Card";
import { TextField } from "@/shared/components/TextField";

function formatUpdatedAt(iso: string | null): string {
  if (!iso) return "Nunca";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

const METHOD_OPTIONS: { value: HighsMethod; label: string }[] = [
  { value: "ipm", label: "IPM (recomendado LP grande)" },
  { value: "hipo", label: "HiPO (IPM multi-hilo)" },
  { value: "simplex", label: "Simplex" },
  { value: "ipx", label: "IPX" },
  { value: "choose", label: "Automático (choose)" },
];

const ON_OFF_OPTIONS: { value: OnOffChoose; label: string }[] = [
  { value: "on", label: "On" },
  { value: "off", label: "Off" },
  { value: "choose", label: "Choose" },
];

const HIPO_PARALLEL_OPTIONS: { value: HipoParallelType; label: string }[] = [
  { value: "", label: "Default (both)" },
  { value: "both", label: "Tree + node" },
  { value: "tree", label: "Tree" },
  { value: "node", label: "Node" },
];

function settingsToDraft(s: SolverSettings): SolverSettingsUpdate {
  return {
    solver_threads: s.solver_threads,
    highs_method: s.highs_method,
    highs_presolve: s.highs_presolve,
    highs_parallel: s.highs_parallel,
    highs_hipo_parallel_type: s.highs_hipo_parallel_type,
    highs_run_crossover: s.highs_run_crossover,
    highs_use_direct: s.highs_use_direct,
    highs_time_limit: s.highs_time_limit,
    highs_ipm_optimality_tolerance: s.highs_ipm_optimality_tolerance,
    highs_primal_feasibility_tolerance: s.highs_primal_feasibility_tolerance,
  };
}

export function SystemSettingsAdminPage() {
  const { push } = useToast();
  const [settings, setSettings] = useState<SolverSettings | null>(null);
  const [draft, setDraft] = useState<SolverSettingsUpdate | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await systemSettingsApi.getSolverSettings();
      setSettings(data);
      setDraft(settingsToDraft(data));
    } catch (err) {
      push(
        err instanceof Error ? err.message : "No se pudo cargar la configuración.",
        "error",
      );
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function save() {
    if (!draft) return;
    if (
      !Number.isFinite(draft.solver_threads) ||
      draft.solver_threads < 0 ||
      draft.solver_threads > 512
    ) {
      push("El número de hilos debe ser un entero entre 0 y 512.", "error");
      return;
    }
    setSaving(true);
    try {
      const updated = await systemSettingsApi.updateSolverSettings(draft);
      setSettings(updated);
      setDraft(settingsToDraft(updated));
      push("Configuración actualizada.", "success");
    } catch (err) {
      push(
        err instanceof Error
          ? err.message
          : "No se pudo guardar la configuración.",
        "error",
      );
    } finally {
      setSaving(false);
    }
  }

  const dirty =
    settings !== null &&
    draft !== null &&
    JSON.stringify(draft) !== JSON.stringify(settingsToDraft(settings));

  function patchDraft(partial: Partial<SolverSettingsUpdate>) {
    setDraft((prev) => (prev ? { ...prev, ...partial } : prev));
  }

  return (
    <section className="pageSection">
      <header className="page__header">
        <h1>Configuración del sistema</h1>
        <p className="muted">
          Ajustes runtime que aplican a todas las simulaciones nuevas. Cambios
          aquí no requieren reinicio del worker.
        </p>
      </header>

      <Card>
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>
          <h2 style={{ margin: 0 }}>Solver HiGHS</h2>
          <p className="muted" style={{ margin: 0 }}>
            HiGHS es el solver open-source por defecto. <strong>0 hilos</strong> =
            default del servidor. GLPK no usa estas opciones.
          </p>

          {loading || !draft ? (
            <div className="muted">Cargando…</div>
          ) : (
            <>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                  gap: 12,
                }}
              >
                <TextField
                  label="Hilos"
                  type="number"
                  min={0}
                  max={512}
                  value={String(draft.solver_threads)}
                  onChange={(e) =>
                    patchDraft({ solver_threads: Number.parseInt(e.target.value, 10) || 0 })
                  }
                  disabled={saving}
                />

                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span>Método LP</span>
                  <select
                    value={draft.highs_method}
                    onChange={(e) =>
                      patchDraft({ highs_method: e.target.value as HighsMethod })
                    }
                    disabled={saving}
                  >
                    {METHOD_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span>Presolve</span>
                  <select
                    value={draft.highs_presolve}
                    onChange={(e) =>
                      patchDraft({ highs_presolve: e.target.value as OnOffChoose })
                    }
                    disabled={saving}
                  >
                    {ON_OFF_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span>Paralelo</span>
                  <select
                    value={draft.highs_parallel}
                    onChange={(e) =>
                      patchDraft({ highs_parallel: e.target.value as OnOffChoose })
                    }
                    disabled={saving}
                  >
                    {ON_OFF_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span>HiPO parallel type</span>
                  <select
                    value={draft.highs_hipo_parallel_type}
                    onChange={(e) =>
                      patchDraft({
                        highs_hipo_parallel_type: e.target.value as HipoParallelType,
                      })
                    }
                    disabled={saving || draft.highs_method !== "hipo"}
                  >
                    {HIPO_PARALLEL_OPTIONS.map((opt) => (
                      <option key={opt.value || "default"} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span>Crossover (IPM→básica)</span>
                  <select
                    value={draft.highs_run_crossover}
                    onChange={(e) =>
                      patchDraft({ highs_run_crossover: e.target.value as OnOffChoose })
                    }
                    disabled={saving}
                  >
                    {ON_OFF_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>

                <TextField
                  label="Time limit (s, 0=sin límite)"
                  type="number"
                  min={0}
                  step={60}
                  value={String(draft.highs_time_limit)}
                  onChange={(e) =>
                    patchDraft({ highs_time_limit: Number.parseFloat(e.target.value) || 0 })
                  }
                  disabled={saving}
                />

                <TextField
                  label="Tolerancia IPM"
                  type="number"
                  step="any"
                  value={String(draft.highs_ipm_optimality_tolerance)}
                  onChange={(e) =>
                    patchDraft({
                      highs_ipm_optimality_tolerance:
                        Number.parseFloat(e.target.value) || 1e-7,
                    })
                  }
                  disabled={saving}
                />

                <TextField
                  label="Tolerancia primal"
                  type="number"
                  step="any"
                  value={String(draft.highs_primal_feasibility_tolerance)}
                  onChange={(e) =>
                    patchDraft({
                      highs_primal_feasibility_tolerance:
                        Number.parseFloat(e.target.value) || 1e-7,
                    })
                  }
                  disabled={saving}
                />
              </div>

              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={draft.highs_use_direct}
                  onChange={(e) => patchDraft({ highs_use_direct: e.target.checked })}
                  disabled={saving}
                />
                <span>
                  Usar <strong>highspy directo</strong> (escribe LP → readModel → run;
                  evita overhead de appsi_highs)
                </span>
              </label>

              <div className="muted" style={{ fontSize: 13 }}>
                Última actualización:{" "}
                <strong>{formatUpdatedAt(settings?.updated_at ?? null)}</strong>
                {settings?.updated_by_username
                  ? ` · por ${settings.updated_by_username}`
                  : ""}
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <Button
                  className="btn btn--primary"
                  onClick={() => void save()}
                  disabled={!dirty || saving}
                >
                  {saving ? "Guardando…" : "Guardar cambios"}
                </Button>
                <Button
                  className="btn btn--ghost"
                  onClick={() => settings && setDraft(settingsToDraft(settings))}
                  disabled={!dirty || saving}
                >
                  Descartar
                </Button>
              </div>
            </>
          )}
        </div>
      </Card>
    </section>
  );
}
