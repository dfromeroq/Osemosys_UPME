/**
 * Administración de configuración runtime del sistema.
 *
 * Solo visible para usuarios con `can_manage_system_settings`. Permite
 * cambiar parámetros globales (ej. número de hilos del solver) sin reiniciar
 * el contenedor — la BD es la fuente de verdad y el worker la lee en cada
 * simulación.
 */
import { useCallback, useEffect, useState } from "react";

import { useToast } from "@/app/providers/useToast";
import { systemSettingsApi, type SolverSettings } from "@/features/systemSettings/api/systemSettingsApi";
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

export function SystemSettingsAdminPage() {
  const { push } = useToast();
  const [settings, setSettings] = useState<SolverSettings | null>(null);
  const [draft, setDraft] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await systemSettingsApi.getSolverSettings();
      setSettings(data);
      setDraft(String(data.solver_threads));
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
    const parsed = Number.parseInt(draft, 10);
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > 512) {
      push("El número de hilos debe ser un entero entre 0 y 512.", "error");
      return;
    }
    setSaving(true);
    try {
      const updated = await systemSettingsApi.updateSolverSettings(parsed);
      setSettings(updated);
      setDraft(String(updated.solver_threads));
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

  const dirty = settings !== null && draft !== String(settings.solver_threads);

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
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          <h2 style={{ margin: 0 }}>Solver</h2>
          <p className="muted" style={{ margin: 0 }}>
            Número de hilos que se entregan a HiGHS y Gurobi. <strong>0</strong>{" "}
            = no aplicar (cada solver usa su default según el servidor). GLPK es
            siempre single-thread y no se ve afectado.
          </p>

          {loading ? (
            <div className="muted">Cargando…</div>
          ) : (
            <>
              <div style={{ maxWidth: 240 }}>
                <TextField
                  label="Hilos del solver"
                  type="number"
                  min={0}
                  max={512}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  disabled={saving}
                />
              </div>

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
                  onClick={() => settings && setDraft(String(settings.solver_threads))}
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
