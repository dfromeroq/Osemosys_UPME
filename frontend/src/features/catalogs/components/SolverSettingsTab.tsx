import { useCallback, useEffect, useMemo, useState } from "react";

import { useToast } from "@/app/providers/useToast";
import { systemSettingsApi, type SolverSettings } from "@/features/systemSettings/api/systemSettingsApi";
import { Badge } from "@/shared/components/Badge";
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

type SolverSettingsTabProps = {
  canEdit: boolean;
};

export function SolverSettingsTab({ canEdit }: SolverSettingsTabProps) {
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
    if (!canEdit) return;
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

  const previewEffective = useMemo(() => {
    if (settings == null) return null;
    const parsed = Number.parseInt(draft, 10);
    if (!Number.isFinite(parsed) || parsed < 0) {
      return settings.effective_threads_preview;
    }
    if (parsed === 0) {
      return settings.hardware_thread_limit;
    }
    return Math.min(parsed, settings.hardware_thread_limit);
  }, [draft, settings]);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <p style={{ margin: 0, opacity: 0.75, maxWidth: 720 }}>
        Ajuste global de hilos para HiGHS y Gurobi. El worker lee este valor al resolver cada
        simulación: jobs en cola y futuras corridas usarán la configuración vigente en ese momento.
        GLPK no se ve afectado (siempre un hilo).
      </p>

      {!canEdit ? (
        <Badge variant="neutral">Solo lectura (sin permiso de administración)</Badge>
      ) : null}

      <Card>
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          <h2 style={{ margin: 0 }}>Solver</h2>
          <p className="muted" style={{ margin: 0 }}>
            <strong>0</strong> = usar todos los CPUs disponibles del worker (
            {settings?.hardware_thread_limit ?? "…"} detectados en este servidor). Si el valor
            pedido supera el hardware, se aplica el máximo disponible.
          </p>

          {loading ? (
            <div className="muted">Cargando…</div>
          ) : (
            <>
              <div style={{ maxWidth: 240 }}>
                <TextField
                  label="Hilos del solver (global)"
                  type="number"
                  min={0}
                  max={512}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  disabled={saving || !canEdit}
                />
              </div>

              {previewEffective != null ? (
                <div className="muted" style={{ fontSize: 13 }}>
                  Hilos efectivos con este valor: <strong>{previewEffective}</strong>
                  {settings && previewEffective !== Number.parseInt(draft, 10) && Number.parseInt(draft, 10) > 0 ? (
                    <span> (cap por hardware)</span>
                  ) : null}
                </div>
              ) : null}

              <div className="muted" style={{ fontSize: 13 }}>
                Última actualización:{" "}
                <strong>{formatUpdatedAt(settings?.updated_at ?? null)}</strong>
                {settings?.updated_by_username
                  ? ` · por ${settings.updated_by_username}`
                  : ""}
              </div>

              {canEdit ? (
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
              ) : null}
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
