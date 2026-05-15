/**
 * ScenarioHistoryPage — Visor de historial de cambios de un escenario.
 *
 * Muestra todas las modificaciones a `osemosys_param_value` agrupadas por
 * batch (operación). Permite filtrar por parámetro, tecnología, fuel,
 * emisión, región, UDC, usuario, fuente, acción, año, fecha y texto libre.
 * Solo se ofrecen como opciones de filtro los valores que efectivamente
 * tuvieron cambios (vienen de `/audit/facets`).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { useToast } from "@/app/providers/useToast";
import {
  scenariosApi,
  type OsemosysParamAuditEntry,
  type ScenarioAuditBatch,
  type ScenarioAuditFacets,
  type ScenarioAuditFilters,
  type ScenarioAuditPage,
} from "@/features/scenarios/api/scenariosApi";
import { paths } from "@/routes/paths";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Card } from "@/shared/components/Card";
import { TextField } from "@/shared/components/TextField";
import type { Scenario } from "@/types/domain";

const PAGE_SIZE = 25;
const ACTIONS = ["INSERT", "UPDATE", "DELETE"];
const SOURCES = ["API", "EXCEL_APPLY", "IMPORT_UPSERT"];

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatNumber(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs !== 0 && (abs < 0.001 || abs >= 1_000_000)) {
    return v.toExponential(3);
  }
  return v.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

function deltaPct(oldV: number | null, newV: number | null): string | null {
  if (oldV == null || newV == null || !Number.isFinite(oldV) || !Number.isFinite(newV)) {
    return null;
  }
  if (oldV === 0) return newV === 0 ? "0%" : "∞%";
  return `${(((newV - oldV) / Math.abs(oldV)) * 100).toFixed(1)}%`;
}

function actionVariant(action: string): "success" | "info" | "danger" | "neutral" {
  if (action === "INSERT") return "success";
  if (action === "UPDATE") return "info";
  if (action === "DELETE") return "danger";
  return "neutral";
}

function sourceLabel(src: string): string {
  if (src === "API") return "Edición directa";
  if (src === "EXCEL_APPLY") return "Aplicación Excel";
  if (src === "IMPORT_UPSERT") return "Import inicial";
  return src;
}

type DimensionsShape = {
  region_name?: string | null;
  technology_name?: string | null;
  fuel_name?: string | null;
  emission_name?: string | null;
  udc_name?: string | null;
  year?: number | string | null;
};

function asDims(d: Record<string, unknown> | null | undefined): DimensionsShape {
  return (d ?? {}) as DimensionsShape;
}

function DimensionChips({ dims }: { dims: DimensionsShape }) {
  const items: Array<{ label: string; value: string }> = [];
  if (dims.region_name) items.push({ label: "Región", value: String(dims.region_name) });
  if (dims.technology_name) items.push({ label: "Tec", value: String(dims.technology_name) });
  if (dims.fuel_name) items.push({ label: "Fuel", value: String(dims.fuel_name) });
  if (dims.emission_name) items.push({ label: "Emisión", value: String(dims.emission_name) });
  if (dims.udc_name) items.push({ label: "UDC", value: String(dims.udc_name) });
  if (dims.year != null) items.push({ label: "Año", value: String(dims.year) });
  if (items.length === 0) return <span className="muted">—</span>;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
      {items.map((it) => (
        <span
          key={`${it.label}:${it.value}`}
          style={{
            background: "rgba(148,163,184,0.12)",
            border: "1px solid rgba(148,163,184,0.25)",
            borderRadius: 6,
            padding: "2px 6px",
            fontSize: 11,
            fontFamily: "monospace",
          }}
          title={`${it.label}: ${it.value}`}
        >
          <span className="muted">{it.label}:</span> {it.value}
        </span>
      ))}
    </div>
  );
}

function DiffCell({ entry }: { entry: OsemosysParamAuditEntry }) {
  const action = entry.action;
  const oldV = entry.old_value;
  const newV = entry.new_value;
  if (action === "INSERT") {
    return (
      <span>
        <Badge variant="success">Nuevo</Badge>{" "}
        <span style={{ fontFamily: "monospace" }}>{formatNumber(newV)}</span>
      </span>
    );
  }
  if (action === "DELETE") {
    return (
      <span>
        <Badge variant="danger">Eliminado</Badge>{" "}
        <span style={{ fontFamily: "monospace", textDecoration: "line-through" }}>
          {formatNumber(oldV)}
        </span>
      </span>
    );
  }
  const pct = deltaPct(oldV, newV);
  const goingUp = oldV != null && newV != null && newV > oldV;
  const goingDown = oldV != null && newV != null && newV < oldV;
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center", fontFamily: "monospace" }}>
      <span style={{ color: "var(--text-muted, #94a3b8)" }}>{formatNumber(oldV)}</span>
      <span aria-hidden>→</span>
      <strong>{formatNumber(newV)}</strong>
      {pct ? (
        <span
          style={{
            fontSize: 11,
            color: goingUp ? "rgb(34,197,94)" : goingDown ? "rgb(239,68,68)" : undefined,
          }}
        >
          ({pct})
        </span>
      ) : null}
    </span>
  );
}

type MultiSelectChipsProps = {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
};

function MultiSelectChips({ label, options, selected, onChange }: MultiSelectChipsProps) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.toLowerCase().includes(q));
  }, [options, search]);

  function toggle(value: string) {
    if (selected.includes(value)) {
      onChange(selected.filter((s) => s !== value));
    } else {
      onChange([...selected, value]);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <button
        type="button"
        className="btn btn--ghost"
        onClick={() => setOpen((v) => !v)}
        style={{ justifyContent: "space-between", textAlign: "left" }}
      >
        <span>
          {label}
          {selected.length ? (
            <span className="muted" style={{ marginLeft: 6, fontSize: 12 }}>
              ({selected.length})
            </span>
          ) : null}
        </span>
        <span aria-hidden style={{ marginLeft: 8 }}>
          {open ? "▴" : "▾"}
        </span>
      </button>
      {selected.length > 0 ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {selected.map((s) => (
            <span
              key={s}
              style={{
                background: "rgba(56,189,248,0.14)",
                border: "1px solid rgba(56,189,248,0.34)",
                borderRadius: 999,
                padding: "2px 8px",
                fontSize: 11,
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              {s}
              <button
                type="button"
                onClick={() => toggle(s)}
                aria-label={`Quitar filtro ${s}`}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "inherit",
                  cursor: "pointer",
                  padding: 0,
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : null}
      {open ? (
        <div
          style={{
            border: "1px solid rgba(148,163,184,0.25)",
            borderRadius: 6,
            padding: 6,
            maxHeight: 200,
            overflow: "auto",
            background: "var(--surface, rgba(15,23,42,0.6))",
          }}
        >
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar…"
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: "4px 6px",
              fontSize: 12,
              marginBottom: 4,
              background: "transparent",
              color: "inherit",
              border: "1px solid rgba(148,163,184,0.2)",
              borderRadius: 4,
            }}
          />
          {filtered.length === 0 ? (
            <div className="muted" style={{ fontSize: 12, padding: 4 }}>
              Sin opciones
            </div>
          ) : (
            filtered.map((o) => {
              const checked = selected.includes(o);
              return (
                <label
                  key={o}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    fontSize: 12,
                    padding: "2px 4px",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(o)}
                  />
                  <span>{o}</span>
                </label>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}

function BatchCard({
  scenarioId,
  batch,
}: {
  scenarioId: number;
  batch: ScenarioAuditBatch;
}) {
  const [expanded, setExpanded] = useState(false);
  const [entries, setEntries] = useState<OsemosysParamAuditEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stats = batch.stats || {};
  const ins = stats.INSERT || 0;
  const upd = stats.UPDATE || 0;
  const del = stats.DELETE || 0;
  const isLegacy = !batch.batch_id;

  const loadEntries = useCallback(async () => {
    if (!batch.batch_id) {
      // Legacy pseudo-batch (sin batch_id real): mostrar el preview tal cual.
      setEntries(batch.preview);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await scenariosApi.listScenarioAuditBatchEntries(
        scenarioId,
        batch.batch_id,
        { limit: 500 },
      );
      setEntries(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron cargar los cambios.");
    } finally {
      setLoading(false);
    }
  }, [batch.batch_id, batch.preview, scenarioId]);

  function toggle() {
    const next = !expanded;
    setExpanded(next);
    if (next && entries === null) {
      void loadEntries();
    }
  }

  const sameTime = batch.started_at === batch.ended_at;
  const rows = entries ?? batch.preview;

  return (
    <Card>
      <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <strong>{batch.changed_by}</strong>
              <Badge variant={batch.source === "API" ? "info" : "neutral"}>
                {sourceLabel(batch.source)}
              </Badge>
              {isLegacy ? <Badge variant="warning">Legacy</Badge> : null}
              <span className="muted" style={{ fontSize: 12 }}>
                {sameTime
                  ? formatDateTime(batch.started_at)
                  : `${formatDateTime(batch.started_at)} – ${formatDateTime(batch.ended_at)}`}
              </span>
            </div>
            {batch.batch_label ? (
              <div style={{ fontSize: 13 }}>{batch.batch_label}</div>
            ) : null}
            {batch.params_touched.length > 0 ? (
              <div className="muted" style={{ fontSize: 12 }}>
                Parámetros afectados: {batch.params_touched.slice(0, 6).join(", ")}
                {batch.params_touched.length > 6 ? `… (+${batch.params_touched.length - 6})` : ""}
              </div>
            ) : null}
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {ins > 0 ? <Badge variant="success">+{ins}</Badge> : null}
            {upd > 0 ? <Badge variant="info">~{upd}</Badge> : null}
            {del > 0 ? <Badge variant="danger">-{del}</Badge> : null}
            <Badge variant="neutral">{batch.entries_count} cambios</Badge>
            <Button
              variant="ghost"
              onClick={toggle}
              aria-expanded={expanded}
              aria-label={expanded ? "Colapsar batch" : "Expandir batch"}
            >
              {expanded ? "Ocultar" : "Ver detalle"}
            </Button>
          </div>
        </div>

        {expanded ? (
          <div>
            {loading ? (
              <div className="muted">Cargando cambios…</div>
            ) : error ? (
              <div style={{ color: "rgb(239,68,68)" }}>{error}</div>
            ) : rows.length === 0 ? (
              <div className="muted">Sin cambios para mostrar.</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    fontSize: 12,
                  }}
                >
                  <thead>
                    <tr style={{ textAlign: "left" }}>
                      <th style={{ padding: 6, borderBottom: "1px solid rgba(148,163,184,0.25)" }}>
                        Parámetro
                      </th>
                      <th style={{ padding: 6, borderBottom: "1px solid rgba(148,163,184,0.25)" }}>
                        Dimensiones
                      </th>
                      <th style={{ padding: 6, borderBottom: "1px solid rgba(148,163,184,0.25)" }}>
                        Cambio
                      </th>
                      <th style={{ padding: 6, borderBottom: "1px solid rgba(148,163,184,0.25)" }}>
                        Acción
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((e) => (
                      <tr
                        key={e.id}
                        style={{ borderBottom: "1px solid rgba(148,163,184,0.12)" }}
                      >
                        <td style={{ padding: 6, fontFamily: "monospace" }}>{e.param_name}</td>
                        <td style={{ padding: 6 }}>
                          <DimensionChips dims={asDims(e.dimensions_json)} />
                        </td>
                        <td style={{ padding: 6 }}>
                          <DiffCell entry={e} />
                        </td>
                        <td style={{ padding: 6 }}>
                          <Badge variant={actionVariant(e.action)}>{e.action}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {entries === null && batch.preview.length < batch.entries_count ? (
                  <div className="muted" style={{ fontSize: 12, padding: "8px 0" }}>
                    Mostrando {batch.preview.length} de {batch.entries_count}.{" "}
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => void loadEntries()}
                    >
                      Cargar todos
                    </button>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

export function ScenarioHistoryPage() {
  const { id } = useParams<{ id: string }>();
  const scenarioId = Number(id);
  const { push } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [facets, setFacets] = useState<ScenarioAuditFacets | null>(null);
  const [page, setPage] = useState<ScenarioAuditPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [facetsLoading, setFacetsLoading] = useState(true);
  const [offset, setOffset] = useState(0);

  // Estado de filtros (inicializado desde URL).
  const [search, setSearch] = useState(searchParams.get("q") ?? "");
  const [paramNames, setParamNames] = useState<string[]>(searchParams.getAll("param_name"));
  const [techNames, setTechNames] = useState<string[]>(searchParams.getAll("technology_name"));
  const [fuelNames, setFuelNames] = useState<string[]>(searchParams.getAll("fuel_name"));
  const [emissionNames, setEmissionNames] = useState<string[]>(searchParams.getAll("emission_name"));
  const [regionNames, setRegionNames] = useState<string[]>(searchParams.getAll("region_name"));
  const [udcNames, setUdcNames] = useState<string[]>(searchParams.getAll("udc_name"));
  const [users, setUsers] = useState<string[]>(searchParams.getAll("changed_by"));
  const [actions, setActions] = useState<string[]>(searchParams.getAll("action"));
  const [sources, setSources] = useState<string[]>(searchParams.getAll("source"));
  const [yearFrom, setYearFrom] = useState<string>(searchParams.get("year_from") ?? "");
  const [yearTo, setYearTo] = useState<string>(searchParams.get("year_to") ?? "");
  const [fromDate, setFromDate] = useState<string>(searchParams.get("from_date") ?? "");
  const [toDate, setToDate] = useState<string>(searchParams.get("to_date") ?? "");
  const [groupByBatch, setGroupByBatch] = useState<boolean>(
    (searchParams.get("group_by_batch") ?? "true") !== "false",
  );

  const filters: ScenarioAuditFilters = useMemo(
    () => ({
      param_name: paramNames.length ? paramNames : undefined,
      technology_name: techNames.length ? techNames : undefined,
      fuel_name: fuelNames.length ? fuelNames : undefined,
      emission_name: emissionNames.length ? emissionNames : undefined,
      region_name: regionNames.length ? regionNames : undefined,
      udc_name: udcNames.length ? udcNames : undefined,
      changed_by: users.length ? users : undefined,
      action: actions.length ? actions : undefined,
      source: sources.length ? sources : undefined,
      year_from: yearFrom ? Number(yearFrom) : undefined,
      year_to: yearTo ? Number(yearTo) : undefined,
      from_date: fromDate || undefined,
      to_date: toDate || undefined,
      q: search || undefined,
      group_by_batch: groupByBatch,
      offset,
      limit: PAGE_SIZE,
    }),
    [
      paramNames,
      techNames,
      fuelNames,
      emissionNames,
      regionNames,
      udcNames,
      users,
      actions,
      sources,
      yearFrom,
      yearTo,
      fromDate,
      toDate,
      search,
      groupByBatch,
      offset,
    ],
  );

  // Persistir filtros en URL.
  useEffect(() => {
    const sp = new URLSearchParams();
    paramNames.forEach((v) => sp.append("param_name", v));
    techNames.forEach((v) => sp.append("technology_name", v));
    fuelNames.forEach((v) => sp.append("fuel_name", v));
    emissionNames.forEach((v) => sp.append("emission_name", v));
    regionNames.forEach((v) => sp.append("region_name", v));
    udcNames.forEach((v) => sp.append("udc_name", v));
    users.forEach((v) => sp.append("changed_by", v));
    actions.forEach((v) => sp.append("action", v));
    sources.forEach((v) => sp.append("source", v));
    if (yearFrom) sp.set("year_from", yearFrom);
    if (yearTo) sp.set("year_to", yearTo);
    if (fromDate) sp.set("from_date", fromDate);
    if (toDate) sp.set("to_date", toDate);
    if (search) sp.set("q", search);
    if (!groupByBatch) sp.set("group_by_batch", "false");
    setSearchParams(sp, { replace: true });
  }, [
    paramNames,
    techNames,
    fuelNames,
    emissionNames,
    regionNames,
    udcNames,
    users,
    actions,
    sources,
    yearFrom,
    yearTo,
    fromDate,
    toDate,
    search,
    groupByBatch,
    setSearchParams,
  ]);

  useEffect(() => {
    if (!Number.isFinite(scenarioId)) return;
    let cancelled = false;
    void (async () => {
      try {
        const sc = await scenariosApi.getScenarioById(scenarioId);
        if (!cancelled) setScenario(sc);
      } catch (e) {
        if (!cancelled) {
          push(
            e instanceof Error ? e.message : "No se pudo cargar el escenario.",
            "error",
          );
        }
      }
      try {
        const f = await scenariosApi.getScenarioAuditFacets(scenarioId);
        if (!cancelled) setFacets(f);
      } catch (e) {
        if (!cancelled) {
          push(
            e instanceof Error ? e.message : "No se pudieron cargar los filtros.",
            "error",
          );
        }
      } finally {
        if (!cancelled) setFacetsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scenarioId, push]);

  // Re-fetch on filter change. Reset offset cuando cambia cualquier filtro
  // (excepto el offset mismo).
  useEffect(() => {
    setOffset(0);
  }, [
    paramNames,
    techNames,
    fuelNames,
    emissionNames,
    regionNames,
    udcNames,
    users,
    actions,
    sources,
    yearFrom,
    yearTo,
    fromDate,
    toDate,
    search,
    groupByBatch,
  ]);

  useEffect(() => {
    if (!Number.isFinite(scenarioId)) return;
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const res = await scenariosApi.listScenarioAudit(scenarioId, filters);
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
  }, [scenarioId, filters, push]);

  function clearFilters() {
    setParamNames([]);
    setTechNames([]);
    setFuelNames([]);
    setEmissionNames([]);
    setRegionNames([]);
    setUdcNames([]);
    setUsers([]);
    setActions([]);
    setSources([]);
    setYearFrom("");
    setYearTo("");
    setFromDate("");
    setToDate("");
    setSearch("");
  }

  const totalBatches = page?.total_batches ?? 0;
  const totalEntries = page?.total_entries ?? 0;
  const items = (page?.items ?? []) as (ScenarioAuditBatch | OsemosysParamAuditEntry)[];

  return (
    <section className="pageSection">
      <header className="page__header" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h1 style={{ margin: 0 }}>Historial de cambios</h1>
          {scenario ? (
            <Link to={paths.scenarioDetail(scenario.id)} className="btn btn--ghost">
              ← {scenario.name}
            </Link>
          ) : null}
        </div>
        <p className="muted" style={{ margin: 0 }}>
          Cada fila representa un cambio sobre un valor del escenario. Los cambios
          se agrupan por operación (batch) — abre un grupo para ver el detalle.
        </p>
      </header>

      {/* KPIs */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 10,
          marginTop: 12,
        }}
      >
        <Card>
          <div style={{ padding: 12 }}>
            <div className="muted" style={{ fontSize: 12 }}>
              Total cambios
            </div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>{totalEntries}</div>
          </div>
        </Card>
        <Card>
          <div style={{ padding: 12 }}>
            <div className="muted" style={{ fontSize: 12 }}>
              Operaciones (batches)
            </div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>{totalBatches}</div>
          </div>
        </Card>
        <Card>
          <div style={{ padding: 12 }}>
            <div className="muted" style={{ fontSize: 12 }}>
              Usuarios distintos
            </div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>
              {facets?.changed_by.length ?? 0}
            </div>
          </div>
        </Card>
        <Card>
          <div style={{ padding: 12 }}>
            <div className="muted" style={{ fontSize: 12 }}>
              Último cambio
            </div>
            <div style={{ fontSize: 14 }}>{formatDateTime(facets?.date_max ?? null)}</div>
          </div>
        </Card>
      </div>

      {/* Layout filtros + lista */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(240px, 280px) 1fr",
          gap: 16,
          marginTop: 16,
          alignItems: "start",
        }}
      >
        {/* Filtros */}
        <Card>
          <div
            style={{ padding: 12, display: "flex", flexDirection: "column", gap: 10 }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>Filtros</strong>
              <Button variant="ghost" onClick={clearFilters}>
                Limpiar
              </Button>
            </div>

            <TextField
              label="Buscar"
              placeholder="Parámetro, usuario, dimensión…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />

            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: 13,
              }}
            >
              <input
                type="checkbox"
                checked={groupByBatch}
                onChange={(e) => setGroupByBatch(e.target.checked)}
              />
              Agrupar por operación
            </label>

            {facetsLoading ? (
              <div className="muted" style={{ fontSize: 12 }}>
                Cargando opciones…
              </div>
            ) : facets ? (
              <>
                <MultiSelectChips
                  label="Parámetro"
                  options={facets.param_names}
                  selected={paramNames}
                  onChange={setParamNames}
                />
                <MultiSelectChips
                  label="Tecnología"
                  options={facets.technology_names}
                  selected={techNames}
                  onChange={setTechNames}
                />
                <MultiSelectChips
                  label="Fuel"
                  options={facets.fuel_names}
                  selected={fuelNames}
                  onChange={setFuelNames}
                />
                <MultiSelectChips
                  label="Emisión"
                  options={facets.emission_names}
                  selected={emissionNames}
                  onChange={setEmissionNames}
                />
                <MultiSelectChips
                  label="Región"
                  options={facets.region_names}
                  selected={regionNames}
                  onChange={setRegionNames}
                />
                <MultiSelectChips
                  label="UDC"
                  options={facets.udc_names}
                  selected={udcNames}
                  onChange={setUdcNames}
                />
                <MultiSelectChips
                  label="Usuario"
                  options={facets.changed_by}
                  selected={users}
                  onChange={setUsers}
                />
                <MultiSelectChips
                  label="Acción"
                  options={ACTIONS.filter((a) => facets.actions.includes(a))}
                  selected={actions}
                  onChange={setActions}
                />
                <MultiSelectChips
                  label="Fuente"
                  options={SOURCES.filter((s) => facets.sources.includes(s))}
                  selected={sources}
                  onChange={setSources}
                />
                <div style={{ display: "flex", gap: 6 }}>
                  <TextField
                    label="Año desde"
                    type="number"
                    value={yearFrom}
                    onChange={(e) => setYearFrom(e.target.value)}
                  />
                  <TextField
                    label="Año hasta"
                    type="number"
                    value={yearTo}
                    onChange={(e) => setYearTo(e.target.value)}
                  />
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <TextField
                    label="Fecha desde"
                    type="date"
                    value={fromDate}
                    onChange={(e) => setFromDate(e.target.value)}
                  />
                  <TextField
                    label="Fecha hasta"
                    type="date"
                    value={toDate}
                    onChange={(e) => setToDate(e.target.value)}
                  />
                </div>
              </>
            ) : null}
          </div>
        </Card>

        {/* Lista de batches o entries */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {loading && !page ? (
            <div className="muted">Cargando historial…</div>
          ) : items.length === 0 ? (
            <Card>
              <div style={{ padding: 24, textAlign: "center" }}>
                <p style={{ margin: 0 }}>
                  <strong>No hay cambios registrados</strong>
                </p>
                <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
                  {totalEntries === 0
                    ? "Este escenario aún no tiene historial."
                    : "Los filtros actuales no devuelven resultados. Intenta limpiarlos."}
                </p>
              </div>
            </Card>
          ) : groupByBatch ? (
            (items as ScenarioAuditBatch[]).map((b, idx) => (
              <BatchCard
                key={b.batch_id ?? `legacy-${idx}-${b.started_at}`}
                scenarioId={scenarioId}
                batch={b}
              />
            ))
          ) : (
            <Card>
              <div style={{ padding: 12, overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ textAlign: "left" }}>
                      <th style={{ padding: 6 }}>Fecha</th>
                      <th style={{ padding: 6 }}>Usuario</th>
                      <th style={{ padding: 6 }}>Parámetro</th>
                      <th style={{ padding: 6 }}>Dimensiones</th>
                      <th style={{ padding: 6 }}>Cambio</th>
                      <th style={{ padding: 6 }}>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(items as OsemosysParamAuditEntry[]).map((e) => (
                      <tr
                        key={e.id}
                        style={{ borderBottom: "1px solid rgba(148,163,184,0.12)" }}
                      >
                        <td style={{ padding: 6, whiteSpace: "nowrap" }}>
                          {formatDateTime(e.created_at)}
                        </td>
                        <td style={{ padding: 6 }}>{e.changed_by}</td>
                        <td style={{ padding: 6, fontFamily: "monospace" }}>{e.param_name}</td>
                        <td style={{ padding: 6 }}>
                          <DimensionChips dims={asDims(e.dimensions_json)} />
                        </td>
                        <td style={{ padding: 6 }}>
                          <DiffCell entry={e} />
                        </td>
                        <td style={{ padding: 6 }}>
                          <Badge variant={actionVariant(e.action)}>{e.action}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Paginación */}
          {(groupByBatch ? totalBatches : totalEntries) > PAGE_SIZE ? (
            <div
              style={{
                display: "flex",
                gap: 8,
                justifyContent: "center",
                alignItems: "center",
                padding: 12,
              }}
            >
              <Button
                variant="ghost"
                disabled={offset === 0 || loading}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                ← Anterior
              </Button>
              <span className="muted" style={{ fontSize: 12 }}>
                {offset + 1}–
                {Math.min(
                  offset + PAGE_SIZE,
                  groupByBatch ? totalBatches : totalEntries,
                )}{" "}
                de {groupByBatch ? totalBatches : totalEntries}
              </span>
              <Button
                variant="ghost"
                disabled={
                  loading ||
                  offset + PAGE_SIZE >= (groupByBatch ? totalBatches : totalEntries)
                }
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Siguiente →
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
