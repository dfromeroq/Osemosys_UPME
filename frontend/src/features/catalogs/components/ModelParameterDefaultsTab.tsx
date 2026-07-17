import { useCallback, useEffect, useMemo, useState } from "react";

import { useToast } from "@/app/providers/useToast";
import {
  modelParameterDefaultsApi,
  type ModelDefaultCatalogRow,
  type ModelDefaultVersionSummary,
} from "@/features/modelDefaults/api/modelParameterDefaultsApi";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Card } from "@/shared/components/Card";
import { TextField } from "@/shared/components/TextField";

const CATEGORY_LABELS: Record<string, string> = {
  global: "Global",
  demand: "Demanda",
  performance: "Rendimiento",
  costs: "Costos",
  capacity: "Capacidad",
  activity: "Actividad",
  reserve: "Margen de reserva",
  re: "Renovables",
  emissions: "Emisiones",
  muio: "MUIO",
  udc: "UDC",
  storage: "Almacenamiento",
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

type ModelParameterDefaultsTabProps = {
  canEdit: boolean;
};

export function ModelParameterDefaultsTab({ canEdit }: ModelParameterDefaultsTabProps) {
  const { push } = useToast();
  const [rows, setRows] = useState<ModelDefaultCatalogRow[]>([]);
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});
  const [versions, setVersions] = useState<ModelDefaultVersionSummary[]>([]);
  const [viewVersionId, setViewVersionId] = useState<number | null>(null);
  const [activeVersionId, setActiveVersionId] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const isHistoricalVersion =
    viewVersionId != null && activeVersionId != null && viewVersionId !== activeVersionId;
  const isReadOnly = !canEdit || isHistoricalVersion;

  const loadCatalog = useCallback(async (versionId?: number) => {
    const data = await modelParameterDefaultsApi.getCatalog(versionId);
    setRows(data.rows);
    setDraftValues(
      Object.fromEntries(data.rows.map((r) => [r.param_key, String(r.value)])),
    );
    setViewVersionId(data.version_id);
    if (versionId == null) {
      setActiveVersionId(data.version_id);
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const ver = await modelParameterDefaultsApi.listVersions();
      setVersions(ver.versions);
      setActiveVersionId(ver.active_version_id);
      await loadCatalog(viewVersionId ?? ver.active_version_id);
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo cargar la configuración.", "error");
    } finally {
      setLoading(false);
    }
  }, [loadCatalog, push, viewVersionId]);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const ver = await modelParameterDefaultsApi.listVersions();
        setVersions(ver.versions);
        setActiveVersionId(ver.active_version_id);
        await loadCatalog(ver.active_version_id);
      } catch (err) {
        push(err instanceof Error ? err.message : "No se pudo cargar la configuración.", "error");
      } finally {
        setLoading(false);
      }
    })();
  }, [loadCatalog, push]);

  const categories = useMemo(() => {
    const set = new Set(rows.map((r) => r.category));
    return Array.from(set).sort();
  }, [rows]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (categoryFilter && r.category !== categoryFilter) return false;
      if (!q) return true;
      return (
        r.pyomo_name.toLowerCase().includes(q) ||
        r.param_key.includes(q) ||
        (r.description ?? "").toLowerCase().includes(q)
      );
    });
  }, [rows, categoryFilter, search]);

  async function save() {
    if (!canEdit) return;
    const items: { param_key: string; value: number }[] = [];
    for (const row of rows) {
      const raw = draftValues[row.param_key] ?? String(row.value);
      const parsed = Number.parseFloat(raw);
      if (!Number.isFinite(parsed)) {
        push(`Valor inválido para ${row.pyomo_name}`, "error");
        return;
      }
      if (row.min_value != null && parsed < row.min_value) {
        push(`${row.pyomo_name}: mínimo ${row.min_value}`, "error");
        return;
      }
      if (row.max_value != null && parsed > row.max_value) {
        push(`${row.pyomo_name}: máximo ${row.max_value}`, "error");
        return;
      }
      items.push({ param_key: row.param_key, value: parsed });
    }
    setSaving(true);
    try {
      const res = await modelParameterDefaultsApi.createVersion({
        items,
        comment: comment.trim() || null,
      });
      push(`Versión #${res.version_id} activa para simulaciones nuevas.`, "success");
      setComment("");
      setViewVersionId(res.active_version_id);
      setActiveVersionId(res.active_version_id);
      const ver = await modelParameterDefaultsApi.listVersions();
      setVersions(ver.versions);
      await loadCatalog(res.active_version_id);
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo guardar.", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <p style={{ margin: 0, opacity: 0.75, maxWidth: 720 }}>
        Valores <code>default=</code> del modelo Pyomo. Solo aplican donde el escenario o CSV no
        define el índice. Cada guardado crea una versión nueva; las simulaciones en curso conservan
        la versión con la que arrancaron.
      </p>

      {!canEdit ? (
        <Badge variant="neutral">Solo lectura (sin permiso de administración)</Badge>
      ) : null}

      <Card>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
          <label style={{ display: "grid", gap: 4, minWidth: 220 }}>
            <span style={{ fontSize: 12, opacity: 0.8 }}>Versión</span>
            <select
              value={viewVersionId ?? ""}
              onChange={(e) => {
                const id = Number(e.target.value);
                if (Number.isFinite(id)) {
                  void loadCatalog(id).catch((err: unknown) =>
                    push(err instanceof Error ? err.message : "Error al cargar versión", "error"),
                  );
                }
              }}
              style={{ padding: "8px 10px", borderRadius: 8 }}
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  #{v.id}
                  {v.is_active ? " (activa)" : ""} — {formatDate(v.created_at)}
                  {v.created_by_username ? ` — ${v.created_by_username}` : ""}
                </option>
              ))}
            </select>
          </label>
          {activeVersionId != null ? (
            <span style={{ fontSize: 13, opacity: 0.85 }}>
              Versión activa: <strong>#{activeVersionId}</strong>
            </span>
          ) : null}
          <Button type="button" variant="ghost" onClick={() => void refresh()} disabled={loading}>
            Recargar
          </Button>
          {isHistoricalVersion ? (
            <Button
              type="button"
              variant="ghost"
              onClick={() => activeVersionId != null && void loadCatalog(activeVersionId)}
            >
              Ver versión activa
            </Button>
          ) : null}
        </div>
      </Card>

      <Card>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 12 }}>
          <label style={{ display: "grid", gap: 4 }}>
            <span style={{ fontSize: 12, opacity: 0.8 }}>Categoría</span>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              style={{ padding: "8px 10px", borderRadius: 8, minWidth: 160 }}
            >
              <option value="">Todas</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABELS[c] ?? c}
                </option>
              ))}
            </select>
          </label>
          <TextField
            label="Buscar"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Nombre Pyomo o clave…"
          />
        </div>

        {loading ? (
          <p>Cargando parámetros…</p>
        ) : (
          <div style={{ overflowX: "auto", maxHeight: "60vh" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border, #334155)" }}>
                  <th style={{ padding: 8 }}>Parámetro</th>
                  <th style={{ padding: 8 }}>Índices</th>
                  <th style={{ padding: 8 }}>Categoría</th>
                  <th style={{ padding: 8 }}>Valor default</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => (
                  <tr key={row.param_key} style={{ borderBottom: "1px solid #1e293b" }}>
                    <td style={{ padding: 8, verticalAlign: "top" }}>
                      <div style={{ fontWeight: 600 }}>{row.pyomo_name}</div>
                      <div style={{ fontSize: 11, opacity: 0.65, fontFamily: "monospace" }}>
                        {row.param_key}
                      </div>
                      {row.description ? (
                        <div style={{ fontSize: 11, opacity: 0.75, marginTop: 4 }}>{row.description}</div>
                      ) : null}
                    </td>
                    <td style={{ padding: 8, fontSize: 11, fontFamily: "monospace" }}>{row.index_dims}</td>
                    <td style={{ padding: 8 }}>{CATEGORY_LABELS[row.category] ?? row.category}</td>
                    <td style={{ padding: 8, minWidth: 140 }}>
                      <input
                        type="number"
                        step="any"
                        disabled={isReadOnly}
                        value={draftValues[row.param_key] ?? ""}
                        onChange={(e) =>
                          setDraftValues((prev) => ({
                            ...prev,
                            [row.param_key]: e.target.value,
                          }))
                        }
                        style={{ width: "100%", padding: "6px 8px", borderRadius: 6 }}
                        title={
                          row.min_value != null || row.max_value != null
                            ? `Rango: ${row.min_value ?? "−∞"} … ${row.max_value ?? "∞"}`
                            : undefined
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {!isReadOnly ? (
        <Card>
          <div style={{ display: "grid", gap: 12, maxWidth: 480 }}>
            <TextField
              label="Comentario (opcional)"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Motivo del cambio…"
            />
            <Button type="button" onClick={() => void save()} disabled={saving || loading}>
              {saving ? "Guardando…" : "Guardar configuración (nueva versión)"}
            </Button>
          </div>
        </Card>
      ) : isHistoricalVersion ? (
        <p style={{ fontSize: 13, opacity: 0.8 }}>
          Vista de solo lectura: seleccione la versión activa para editar.
        </p>
      ) : null}
    </div>
  );
}
