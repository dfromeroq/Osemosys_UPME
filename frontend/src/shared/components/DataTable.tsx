/**
 * Tabla de datos genérica con búsqueda global, filtro por columna y paginación.
 *
 * Cada columna puede declarar un filtro independiente:
 *   - `filter: { type: 'text' }`         → input de texto (busca "contains")
 *   - `filter: { type: 'select', options }` → dropdown single-select
 *   - `filter: { type: 'multiselect' }`  → dropdown con búsqueda + checkboxes.
 *       Las opciones se auto-derivan de los valores únicos devueltos por
 *       `getValue(row)`; si se pasan `options`, se usa ese catálogo fijo
 *       y además se garantiza que aparezcan las opciones aún sin datos.
 * Todos los casos requieren `getValue(row)` (cadena).
 */
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { DataTableColumnFilter } from "@/shared/components/DataTableColumnFilter";
import { TextField } from "@/shared/components/TextField";

export type ColumnFilterConfig<T> = {
  type: "text" | "select" | "multiselect";
  /** Valor que se evalúa para el filtro (cadena) */
  getValue: (row: T) => string;
  /** Opciones cuando type='select' o para extender multiselect */
  options?: { value: string; label: string }[];
  /** Label opcional al renderizar un valor como chip/opción (multiselect). */
  getLabel?: (value: string) => string;
  placeholder?: string;
};

/** Definición de columna: clave, encabezado y función de renderizado por fila */
export type ColumnDef<T> = {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  filter?: ColumnFilterConfig<T>;
};

type Props<T> = {
  rows: T[];
  columns: ColumnDef<T>[];
  rowKey: (row: T) => string;
  searchPlaceholder?: string;
  /** Si se provee, habilita el campo de búsqueda global */
  searchableText?: (row: T) => string;
  pageSize?: number;
};

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  searchPlaceholder = "Buscar...",
  searchableText,
  pageSize = 25,
}: Props<T>) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSizeState, setPageSizeState] = useState(pageSize);
  /** Filtros text + single-select: columnKey → string. */
  const [columnFilters, setColumnFilters] = useState<Record<string, string>>({});
  /** Filtros multiselect: columnKey → array de valores seleccionados (OR). */
  const [multiFilters, setMultiFilters] = useState<Record<string, string[]>>({});

  const hasColumnFilters = useMemo(
    () => columns.some((c) => c.filter),
    [columns],
  );

  /** Opciones auto-derivadas de los datos por cada columna multiselect. */
  const multiOptionsByKey = useMemo(() => {
    const byKey: Record<string, { value: string; label: string }[]> = {};
    for (const c of columns) {
      if (!c.filter || c.filter.type !== "multiselect") continue;
      const seen = new Set<string>();
      const opts: { value: string; label: string }[] = [];
      for (const o of c.filter.options ?? []) {
        if (!seen.has(o.value)) {
          seen.add(o.value);
          opts.push(o);
        }
      }
      for (const r of rows) {
        const v = c.filter.getValue(r);
        if (!v || seen.has(v)) continue;
        seen.add(v);
        opts.push({ value: v, label: c.filter.getLabel?.(v) ?? v });
      }
      opts.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: "base" }));
      byKey[c.key] = opts;
    }
    return byKey;
  }, [columns, rows]);

  /** Filtra: búsqueda global + filtros por columna. */
  const filtered = useMemo(() => {
    let out = rows;
    if (query.trim() && searchableText) {
      const q = query.trim().toLowerCase();
      out = out.filter((r) => searchableText(r).toLowerCase().includes(q));
    }
    for (const c of columns) {
      if (!c.filter) continue;
      if (c.filter.type === "multiselect") {
        const selected = multiFilters[c.key];
        if (!selected || selected.length === 0) continue;
        const set = new Set(selected);
        out = out.filter((r) => set.has(c.filter!.getValue(r)));
        continue;
      }
      const raw = (columnFilters[c.key] ?? "").trim();
      if (!raw) continue;
      const needle = raw.toLowerCase();
      const matcher =
        c.filter.type === "select"
          ? (r: T) => c.filter!.getValue(r).toLowerCase() === needle
          : (r: T) => c.filter!.getValue(r).toLowerCase().includes(needle);
      out = out.filter(matcher);
    }
    return out;
  }, [rows, query, searchableText, columns, columnFilters, multiFilters]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSizeState));
  const safePage = Math.min(page, totalPages);
  const paginated = filtered.slice(
    (safePage - 1) * pageSizeState,
    safePage * pageSizeState,
  );

  const setFilter = (key: string, value: string) => {
    setPage(1);
    setColumnFilters((prev) => {
      if (!value) {
        const next = { ...prev };
        delete next[key];
        return next;
      }
      return { ...prev, [key]: value };
    });
  };

  const setMulti = (key: string, values: string[]) => {
    setPage(1);
    setMultiFilters((prev) => {
      if (values.length === 0) {
        const next = { ...prev };
        delete next[key];
        return next;
      }
      return { ...prev, [key]: values };
    });
  };

  const clearAllFilters = () => {
    setQuery("");
    setColumnFilters({});
    setMultiFilters({});
    setPage(1);
  };

  const anyFilterActive =
    query.trim().length > 0 ||
    Object.keys(columnFilters).length > 0 ||
    Object.values(multiFilters).some((v) => v.length > 0);

  return (
    <div style={{ display: "grid", gap: 10 }}>
      {searchableText || hasColumnFilters ? (
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          {searchableText ? (
            <div style={{ maxWidth: 320, flex: "1 1 220px" }}>
              <TextField
                label="Buscar"
                value={query}
                onChange={(e) => {
                  setPage(1);
                  setQuery(e.target.value);
                }}
                placeholder={searchPlaceholder}
              />
            </div>
          ) : null}
          {anyFilterActive ? (
            <button
              className="btn btn--ghost"
              type="button"
              onClick={clearAllFilters}
              style={{ alignSelf: "flex-end" }}
            >
              Limpiar filtros
            </button>
          ) : null}
        </div>
      ) : null}

      <div
        style={{
          overflowX: "auto",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 12,
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead style={{ background: "rgba(255,255,255,0.03)" }}>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  style={{
                    textAlign: "left",
                    fontSize: 13,
                    padding: "10px 12px",
                    color: "var(--muted)",
                  }}
                >
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    {c.header}
                    {c.filter ? (
                      <DataTableColumnFilter
                        columnLabel={c.header}
                        config={c.filter}
                        multiOptions={multiOptionsByKey[c.key] ?? []}
                        textValue={columnFilters[c.key] ?? ""}
                        multiSelected={multiFilters[c.key] ?? []}
                        onTextChange={(v) => setFilter(c.key, v)}
                        onMultiChange={(vals) => setMulti(c.key, vals)}
                      />
                    ) : null}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginated.length === 0 ? (
              <tr>
                <td colSpan={columns.length} style={{ padding: 14, opacity: 0.75 }}>
                  Sin registros.
                </td>
              </tr>
            ) : (
              paginated.map((row) => (
                <tr
                  key={rowKey(row)}
                  style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      style={{ padding: "10px 12px", verticalAlign: "top" }}
                    >
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <small style={{ opacity: 0.75 }}>
            Página {safePage} de {totalPages}
          </small>
          <small style={{ opacity: 0.75 }}>
            · Mostrando {paginated.length} de {filtered.length} registros
          </small>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 13,
              opacity: 0.85,
            }}
          >
            Registros por página:
            <select
              value={pageSizeState}
              onChange={(e) => {
                const next = Number(e.target.value) || 25;
                setPageSizeState(next);
                setPage(1);
              }}
              style={{
                padding: "2px 6px",
                borderRadius: 6,
                background: "transparent",
                color: "inherit",
              }}
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn btn--ghost"
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Anterior
            </button>
            <button
              className="btn btn--ghost"
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Siguiente
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
