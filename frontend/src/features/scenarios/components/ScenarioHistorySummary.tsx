/**
 * ScenarioHistorySummary — pestaña de resumen de historial dentro de
 * `ScenarioDetailPage`. Muestra los últimos N batches y un botón para ir
 * a la página completa con filtros (`/scenarios/:id/history`).
 */
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";

import { useToast } from "@/app/providers/useToast";
import {
  scenariosApi,
  type ScenarioAuditBatch,
  type ScenarioAuditPage,
} from "@/features/scenarios/api/scenariosApi";
import { paths } from "@/routes/paths";
import { Badge } from "@/shared/components/Badge";
import { Card } from "@/shared/components/Card";

const SUMMARY_BATCH_LIMIT = 8;

function formatRelative(iso: string): string {
  try {
    const ts = new Date(iso).getTime();
    const diff = Date.now() - ts;
    const min = Math.round(diff / 60_000);
    if (min < 1) return "hace unos segundos";
    if (min < 60) return `hace ${min} min`;
    const hr = Math.round(min / 60);
    if (hr < 24) return `hace ${hr} h`;
    const days = Math.round(hr / 24);
    if (days < 30) return `hace ${days} d`;
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

function sourceLabel(src: string): string {
  if (src === "API") return "Edición directa";
  if (src === "EXCEL_APPLY") return "Aplicación Excel";
  if (src === "IMPORT_UPSERT") return "Import inicial";
  return src;
}

export function ScenarioHistorySummary({ scenarioId }: { scenarioId: number }) {
  const { push } = useToast();
  const [page, setPage] = useState<ScenarioAuditPage | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const res = await scenariosApi.listScenarioAudit(scenarioId, {
          group_by_batch: true,
          limit: SUMMARY_BATCH_LIMIT,
          offset: 0,
        });
        if (!cancelled) setPage(res);
      } catch (e) {
        if (!cancelled) {
          push(
            e instanceof Error ? e.message : "No se pudo cargar el historial.",
            "error",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scenarioId, push]);

  const batches = (page?.items ?? []) as ScenarioAuditBatch[];
  const totalEntries = page?.total_entries ?? 0;
  const totalBatches = page?.total_batches ?? 0;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <div>
          <h3 style={{ margin: 0 }}>Historial de cambios</h3>
          <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
            {totalEntries} cambios en {totalBatches} operaciones. Mostrando los{" "}
            {Math.min(SUMMARY_BATCH_LIMIT, totalBatches)} más recientes.
          </p>
        </div>
        <Link className="btn btn--primary" to={paths.scenarioHistory(scenarioId)}>
          Ver historial completo
        </Link>
      </div>

      {loading && !page ? (
        <div className="muted">Cargando historial…</div>
      ) : batches.length === 0 ? (
        <Card>
          <div style={{ padding: 24, textAlign: "center" }}>
            <p style={{ margin: 0 }}>
              <strong>Sin cambios registrados</strong>
            </p>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
              Las ediciones de valores aparecerán aquí.
            </p>
          </div>
        </Card>
      ) : (
        batches.map((b, idx) => {
          const stats = b.stats || {};
          const ins = stats.INSERT || 0;
          const upd = stats.UPDATE || 0;
          const del = stats.DELETE || 0;
          return (
            <Card key={b.batch_id ?? `legacy-${idx}-${b.started_at}`}>
              <div
                style={{
                  padding: 12,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: 10,
                }}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      flexWrap: "wrap",
                    }}
                  >
                    <strong>{b.changed_by}</strong>
                    <Badge variant={b.source === "API" ? "info" : "neutral"}>
                      {sourceLabel(b.source)}
                    </Badge>
                    <span className="muted" style={{ fontSize: 12 }}>
                      {formatRelative(b.ended_at)}
                    </span>
                  </div>
                  {b.batch_label ? (
                    <div style={{ fontSize: 13 }}>{b.batch_label}</div>
                  ) : null}
                  {b.params_touched.length > 0 ? (
                    <div className="muted" style={{ fontSize: 12 }}>
                      {b.params_touched.slice(0, 4).join(", ")}
                      {b.params_touched.length > 4 ? `… (+${b.params_touched.length - 4})` : ""}
                    </div>
                  ) : null}
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  {ins > 0 ? <Badge variant="success">+{ins}</Badge> : null}
                  {upd > 0 ? <Badge variant="info">~{upd}</Badge> : null}
                  {del > 0 ? <Badge variant="danger">-{del}</Badge> : null}
                  <Badge variant="neutral">{b.entries_count}</Badge>
                </div>
              </div>
            </Card>
          );
        })
      )}
    </div>
  );
}
