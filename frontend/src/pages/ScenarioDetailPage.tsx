/**
 * ScenarioDetailPage - Detalle de un escenario energético
 *
 * Tres pestañas principales:
 * 1. Valores: parámetros OSeMOSYS (osemosys_param_value), filtros por parámetro/año, CRUD de valores,
 *    resumen agregado, propuestas de cambio para usuarios sin edición directa
 * 2. Permisos: gestión de permisos (can_edit_direct, can_propose, can_manage_values) para usuarios
 * 3. Solicitudes pendientes: aprobar/rechazar cambios propuestos por otros usuarios
 *
 * Endpoints usados:
 * - scenariosApi.getScenarioById, getEffectivePermission
 * - scenariosApi.listOsemosysValuesWide, listOsemosysWideFacets
 * - scenariosApi.createOsemosysValue, updateOsemosysValue, deactivateOsemosysValue
 * - scenariosApi.createChangeRequest, listPendingChangeRequests, reviewChangeRequest
 * - scenariosApi.listPermissions, upsertPermission
 *
 * La visibilidad de acciones depende de la política del escenario (OWNER_ONLY, OPEN, RESTRICTED).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useCurrentUser } from "@/app/providers/useCurrentUser";
import { useToast } from "@/app/providers/useToast";
import {
  scenariosApi,
  serializeYearRules,
  type ExcelUpdatePreviewRow,
  type OsemosysValueRow,
  type OsemosysWideFacets,
  type OsemosysWideFilters,
  type OsemosysWideRow,
  type ScenarioAccess,
  type YearRule,
} from "@/features/scenarios/api/scenariosApi";
import { officialImportApi } from "@/features/officialImport/api/officialImportApi";
import { catalogsApi } from "@/features/catalogs/api/catalogsApi";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ScenarioTagChip } from "@/shared/components/ScenarioTagChip";
import { ScenarioTagsPanel } from "@/shared/components/ScenarioTagsPanel";
import { ColumnFilterPopover } from "@/shared/components/ColumnFilterPopover";
import { YearRuleFilterPopover } from "@/shared/components/YearRuleFilterPopover";
import { DataTable } from "@/shared/components/DataTable";
import { Modal } from "@/shared/components/Modal";
import { TextField } from "@/shared/components/TextField";
import { UploadProgress, type UploadPhase } from "@/shared/components/UploadProgress";
import type {
  ChangeRequest,
  Scenario,
  ScenarioEditPolicy,
  ScenarioOperationJob,
  ScenarioPermission,
  ScenarioTag,
  ScenarioTagCategory,
  SimulationType,
} from "@/types/domain";

type Tab = "values" | "permissions" | "pending";

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200] as const;
const PREVIEW_PAGE_SIZE_OPTIONS = [100, 200, 500, 1000] as const;
const PREVIEW_NARROW_BREAKPOINT = 920;

type PreviewGroup = {
  key: string;
  param_name: string;
  region_name: string | null;
  technology_name: string | null;
  fuel_name: string | null;
  emission_name: string | null;
  rows: ExcelUpdatePreviewRow[];
};

function buildPreviewGroupKey(row: ExcelUpdatePreviewRow): string {
  return [
    row.param_name,
    row.region_name ?? "",
    row.technology_name ?? "",
    row.fuel_name ?? "",
    row.emission_name ?? "",
  ].join("||");
}

function getPolicyExplanation(editPolicy: ScenarioEditPolicy): string {
  if (editPolicy === "OWNER_ONLY") return "Solo el propietario administra permisos y edita valores.";
  if (editPolicy === "OPEN") return "Cualquier usuario autenticado con acceso al escenario puede editar valores.";
  return "Solo permisos explícitos pueden editar o gestionar valores.";
}

export function ScenarioDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const scenarioId = Number(id);
  const { user } = useCurrentUser();
  const { push } = useToast();
  const [tab, setTab] = useState<Tab>("values");
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [access, setAccess] = useState<ScenarioAccess | null>(null);
  const [osemosysWideRows, setOsemosysWideRows] = useState<OsemosysWideRow[]>([]);
  const [osemosysWideYears, setOsemosysWideYears] = useState<number[]>([]);
  const [osemosysHasScalar, setOsemosysHasScalar] = useState(false);
  const [osemosysTotal, setOsemosysTotal] = useState(0);
  const [columnFilters, setColumnFilters] = useState<OsemosysWideFilters>({});
  const [yearRules, setYearRules] = useState<Record<string, YearRule>>({});
  const [facets, setFacets] = useState<OsemosysWideFacets | null>(null);
  const [facetsLoading, setFacetsLoading] = useState(false);
  const [osemosysPage, setOsemosysPage] = useState(1);
  const [osemosysPageSize, setOsemosysPageSize] = useState<number>(50);
  // Búsqueda global eliminada del UI; el string vacío hace no-op en el backend.
  const osemosysSearch = "";
  const [osemosysLoading, setOsemosysLoading] = useState(false);
  // `filterParamName` se mantiene (ILIKE server-side) aunque ya no hay input
  // dedicado — se cubre con el popover de columna y la búsqueda global.
  const [filterParamName] = useState("");
  // filterYear legado — conservado como "" para no tocar signatures del fetch.
  const filterYear = "";
  // Años visibles (client-side): vacío = mostrar todos.
  const [filterYears, setFilterYears] = useState<string[]>([]);
  const [permissions, setPermissions] = useState<ScenarioPermission[]>([]);
  const [pending, setPending] = useState<ChangeRequest[]>([]);
  const [parentScenarioName, setParentScenarioName] = useState<string | null>(null);
  // Marcado true cuando los filtros activos vienen del deep-link
  // `?dq_*` (modal de calidad de datos). Se limpia al limpiar los filtros.
  const [filtersFromDataQuality, setFiltersFromDataQuality] = useState(false);
  const [loading, setLoading] = useState(true);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [openOsemosysModal, setOpenOsemosysModal] = useState(false);
  const [editingOsemosys, setEditingOsemosys] = useState<OsemosysValueRow | null>(null);
  const [proposeFor, setProposeFor] = useState<OsemosysValueRow | null>(null);
  const [proposalNewValue, setProposalNewValue] = useState("");

  const [editingCell, setEditingCell] = useState<{
    rowKey: string;
    yearKey: string;
    valueId: number;
    original: number;
  } | null>(null);
  const [cellDraft, setCellDraft] = useState("");
  const [cellSaving, setCellSaving] = useState(false);
  // Celda seleccionada (NO en edición). Habilita navegación con teclado tipo Excel.
  const [selectedCell, setSelectedCell] = useState<{
    rowIdx: number;
    yearKey: string;
  } | null>(null);
  // Extremo opuesto del rango (Shift+flecha). null = selección de 1 sola celda.
  const [selectionEnd, setSelectionEnd] = useState<{
    rowIdx: number;
    yearKey: string;
  } | null>(null);
  // Ref del contenedor scrollable de la tabla para scrollIntoView de la celda activa.
  const tableScrollRef = useRef<HTMLDivElement | null>(null);

  const [openExcelUpdateModal, setOpenExcelUpdateModal] = useState(false);
  const [excelUpdateFile, setExcelUpdateFile] = useState<File | null>(null);
  const [excelUpdateSheets, setExcelUpdateSheets] = useState<string[]>([]);
  const [excelUpdateSelectedSheet, setExcelUpdateSelectedSheet] = useState("");
  const [excelUpdateLoadingSheets, setExcelUpdateLoadingSheets] = useState(false);
  const [excelPreviewLoading, setExcelPreviewLoading] = useState(false);
  const [excelApplyLoading, setExcelApplyLoading] = useState(false);
  const [excelApplyJob, setExcelApplyJob] = useState<ScenarioOperationJob | null>(null);
  const [excelPreviewData, setExcelPreviewData] = useState<ExcelUpdatePreviewRow[] | null>(null);
  const [excelPreviewWarnings, setExcelPreviewWarnings] = useState<string[]>([]);
  const [excelPreviewNotFound, setExcelPreviewNotFound] = useState(0);
  const [excelPreviewTotalRows, setExcelPreviewTotalRows] = useState(0);
  const [excelSelectedRowIds, setExcelSelectedRowIds] = useState<Set<string>>(new Set());
  const [excelApplyResult, setExcelApplyResult] = useState<{ updated: number; inserted: number; skipped: number } | null>(null);
  const [excelPreviewSearch, setExcelPreviewSearch] = useState("");
  const [excelPreviewPage, setExcelPreviewPage] = useState(1);
  const [excelPreviewPageSize, setExcelPreviewPageSize] = useState<number>(200);
  const [excelExpandedGroupKeys, setExcelExpandedGroupKeys] = useState<Set<string>>(new Set());
  const [isPreviewNarrowViewport, setIsPreviewNarrowViewport] = useState(false);
  const [excelPreviewUploadPhase, setExcelPreviewUploadPhase] = useState<UploadPhase>("idle");
  const [excelPreviewUploadPercent, setExcelPreviewUploadPercent] = useState(0);
  const [excelPreviewUploadStartedAt, setExcelPreviewUploadStartedAt] = useState<number | null>(null);
  const [excelCollapseTimeslices, setExcelCollapseTimeslices] = useState(true);
  const [excelDownloading, setExcelDownloading] = useState(false);
  const [openPermModal, setOpenPermModal] = useState(false);
  const [openMetaModal, setOpenMetaModal] = useState(false);
  const [catalogSuggestions, setCatalogSuggestions] = useState<{
    parameters: string[];
    regions: string[];
    technologies: string[];
    fuels: string[];
    emissions: string[];
    udcs: string[];
  }>({
    parameters: [],
    regions: [],
    technologies: [],
    fuels: [],
    emissions: [],
    udcs: [],
  });
  const [osemosysForm, setOsemosysForm] = useState({
    param_name: "",
    region_name: "",
    technology_name: "",
    fuel_name: "",
    emission_name: "",
    udc_name: "",
    year: "",
    value: "",
  });
  const [permForm, setPermForm] = useState({
    username: "",
    user_identifier: "",
    can_edit_direct: false,
    can_propose: true,
    can_manage_values: false,
  });
  const [scenarioTags, setScenarioTags] = useState<ScenarioTag[]>([]);
  const [scenarioTagCategories, setScenarioTagCategories] = useState<
    ScenarioTagCategory[]
  >([]);
  const [metaForm, setMetaForm] = useState<{
    name: string;
    description: string;
    edit_policy: ScenarioEditPolicy;
    simulation_type: SimulationType;
  }>({
    name: "",
    description: "",
    edit_policy: "OWNER_ONLY",
    simulation_type: "NATIONAL",
  });
  // Para valores OSeMOSYS usamos el acceso efectivo calculado por backend.
  // Esto mantiene la semántica de OPEN: cualquier usuario autenticado puede editar valores.
  const canManagePermissions = Boolean(access?.isOwner || access?.can_edit_direct);
  const canManageValues = Boolean(access?.can_manage_values);
  const canEditScenarioMeta = Boolean(access?.isOwner || access?.can_edit_direct);

  useEffect(() => {
    if (!user) return;
    void Promise.all([
      scenariosApi.listScenarioTags(),
      scenariosApi.listScenarioTagCategories(),
    ])
      .then(([tags, cats]) => {
        setScenarioTags(tags);
        setScenarioTagCategories(cats);
      })
      .catch(() => {
        setScenarioTags([]);
        setScenarioTagCategories([]);
      });
  }, [user]);

  // Deep-link desde DataQualityModal: la lectura de `?dq_*` se hace dentro
  // del load inicial (más abajo, en el useEffect que carga el escenario)
  // para que los filtros se apliquen ANTES del primer fetch — evitando la
  // race condition con un effect tardío.

  const refreshScenarioHeader = useCallback(
    async (scId: number) => {
      const refreshed = await scenariosApi.getScenarioById(scId);
      setScenario(refreshed);
      setParentScenarioName(refreshed.base_scenario_name ?? parentScenarioName);
    },
    [parentScenarioName],
  );

  const refreshCatalogSuggestions = useCallback(
    async (seed?: {
      parameters?: Array<string | null | undefined>;
      regions?: Array<string | null | undefined>;
      technologies?: Array<string | null | undefined>;
      fuels?: Array<string | null | undefined>;
      emissions?: Array<string | null | undefined>;
      udcs?: Array<string | null | undefined>;
    }) => {
      const unique = (items: Array<string | null | undefined>): string[] =>
        Array.from(new Set(items.filter((x): x is string => Boolean(x && x.trim())))).sort((a, b) =>
          a.localeCompare(b, "es"),
        );

      try {
        const [parameters, regions, technologies, fuels, emissions] = await Promise.all([
          catalogsApi.list("parameter", { includeInactive: true, cantidad: 5000 }),
          catalogsApi.list("region", { includeInactive: true, cantidad: 5000 }),
          catalogsApi.list("technology", { includeInactive: true, cantidad: 5000 }),
          catalogsApi.list("fuel", { includeInactive: true, cantidad: 5000 }),
          catalogsApi.list("emission", { includeInactive: true, cantidad: 5000 }),
        ]);
        setCatalogSuggestions({
          parameters: unique([
            ...parameters.map((r) => r.name),
            ...(seed?.parameters ?? []),
          ]),
          regions: unique([
            ...regions.map((r) => r.name),
            ...(seed?.regions ?? []),
          ]),
          technologies: unique([
            ...technologies.map((r) => r.name),
            ...(seed?.technologies ?? []),
          ]),
          fuels: unique([
            ...fuels.map((r) => r.name),
            ...(seed?.fuels ?? []),
          ]),
          emissions: unique([
            ...emissions.map((r) => r.name),
            ...(seed?.emissions ?? []),
          ]),
          udcs: unique(seed?.udcs ?? []),
        });
      } catch {
        setCatalogSuggestions((prev) => ({
          ...prev,
          udcs: unique([...(prev.udcs ?? []), ...(seed?.udcs ?? [])]),
        }));
      }
    },
    [],
  );

  /** Carga una página de valores OSeMOSYS (formato wide) desde el servidor.
   *
   * El parámetro `yearValue` no se envía al backend: en formato wide, filtrar
   * por año equivale a ocultar columnas de años, lo cual se hace en render.
   * Los filtros por columna (`colFilters`) aplican `IN` server-side.
   */
  const fetchOsemosysPage = useCallback(
    async (
      scId: number,
      page: number,
      pageSize: number,
      searchTerm: string,
      paramName: string,
      _yearValue: string,
      colFilters: OsemosysWideFilters = {},
    ) => {
      setOsemosysLoading(true);
      try {
        const offset = (page - 1) * pageSize;
        const res = await scenariosApi.listOsemosysValuesWide(scId, {
          offset,
          limit: pageSize,
          ...(searchTerm.trim() ? { search: searchTerm.trim() } : {}),
          ...(paramName.trim() ? { param_name: paramName.trim() } : {}),
          ...colFilters,
        });
        setOsemosysWideRows(res.items);
        setOsemosysWideYears(res.years);
        setOsemosysHasScalar(res.has_scalar);
        setOsemosysTotal(res.total);

        await refreshCatalogSuggestions({
          parameters: res.items.map((r) => r.param_name),
          regions: res.items.map((r) => r.region_name),
          technologies: res.items.map((r) => r.technology_name),
          fuels: res.items.map((r) => r.fuel_name),
          emissions: res.items.map((r) => r.emission_name),
          udcs: res.items.map((r) => r.udc_name),
        });
      } catch (err) {
        push(err instanceof Error ? err.message : "Error cargando valores.", "error");
      } finally {
        setOsemosysLoading(false);
      }
    },
    [push, refreshCatalogSuggestions],
  );

  /** Recalcula los facets narrowed (exclude-self) a partir de los filtros activos. */
  const fetchFacets = useCallback(
    async (scId: number, searchTerm: string, paramName: string, colFilters: OsemosysWideFilters) => {
      setFacetsLoading(true);
      try {
        const res = await scenariosApi.listOsemosysWideFacets(scId, {
          ...(searchTerm.trim() ? { search: searchTerm.trim() } : {}),
          ...(paramName.trim() ? { param_name: paramName.trim() } : {}),
          ...colFilters,
        });
        setFacets(res);
      } catch (err) {
        push(err instanceof Error ? err.message : "Error cargando filtros.", "error");
      } finally {
        setFacetsLoading(false);
      }
    },
    [push],
  );

  /** Recarga la página actual de valores OSeMOSYS */
  const refreshOsemosysData = useCallback(
    async (scId: number, paramName = filterParamName, yearValue = filterYear) => {
      const yr = serializeYearRules(yearRules);
      const merged: OsemosysWideFilters = yr ? { ...columnFilters, year_rules: yr } : columnFilters;
      await Promise.all([
        fetchOsemosysPage(scId, osemosysPage, osemosysPageSize, osemosysSearch, paramName, yearValue, merged),
        fetchFacets(scId, osemosysSearch, paramName, merged),
      ]);
    },
    [columnFilters, fetchFacets, fetchOsemosysPage, filterParamName, filterYear, osemosysPage, osemosysPageSize, osemosysSearch, yearRules],
  );

  /** Combina filtros de columna categórica con las reglas de año en un único objeto de filtros. */
  const buildFilters = useCallback(
    (cols: OsemosysWideFilters, rules: Record<string, YearRule>): OsemosysWideFilters => {
      const yr = serializeYearRules(rules);
      return yr ? { ...cols, year_rules: yr } : cols;
    },
    [],
  );

  /** Aplica un cambio a un filtro de columna y relanza datos + facets narrowed. */
  const applyColumnFilter = useCallback(
    (column: keyof OsemosysWideFilters, values: string[]) => {
      setColumnFilters((prev) => {
        const next: OsemosysWideFilters = { ...prev };
        if (values.length === 0) delete next[column];
        else (next as Record<string, unknown>)[column] = values;
        if (scenario) {
          const merged = buildFilters(next, yearRules);
          setOsemosysPage(1);
          void fetchOsemosysPage(scenario.id, 1, osemosysPageSize, osemosysSearch, filterParamName, filterYear, merged);
          void fetchFacets(scenario.id, osemosysSearch, filterParamName, merged);
        }
        return next;
      });
    },
    [buildFilters, fetchFacets, fetchOsemosysPage, filterParamName, filterYear, osemosysPageSize, osemosysSearch, scenario, yearRules],
  );

  /** Aplica/limpia una regla sobre un año concreto. `null` elimina la regla. */
  const applyYearRule = useCallback(
    (year: number, rule: YearRule | null) => {
      setYearRules((prev) => {
        const next = { ...prev };
        if (rule === null) delete next[String(year)];
        else next[String(year)] = rule;
        if (scenario) {
          const merged = buildFilters(columnFilters, next);
          setOsemosysPage(1);
          void fetchOsemosysPage(scenario.id, 1, osemosysPageSize, osemosysSearch, filterParamName, filterYear, merged);
          void fetchFacets(scenario.id, osemosysSearch, filterParamName, merged);
        }
        return next;
      });
    },
    [buildFilters, columnFilters, fetchFacets, fetchOsemosysPage, filterParamName, filterYear, osemosysPageSize, osemosysSearch, scenario],
  );

  const clearAllColumnFilters = useCallback(() => {
    setColumnFilters({});
    setYearRules({});
    if (scenario) {
      setOsemosysPage(1);
      void fetchOsemosysPage(scenario.id, 1, osemosysPageSize, osemosysSearch, filterParamName, filterYear, {});
      void fetchFacets(scenario.id, osemosysSearch, filterParamName, {});
    }
  }, [fetchFacets, fetchOsemosysPage, filterParamName, filterYear, osemosysPageSize, osemosysSearch, scenario]);

  const hasActiveColumnFilters = useMemo(
    () =>
      Object.values(columnFilters).some((v) => Array.isArray(v) && v.length > 0) ||
      Object.keys(yearRules).length > 0,
    [columnFilters, yearRules],
  );

  // ── Navegación tipo Excel ────────────────────────────────────────────
  // `cellKeysShown` = orden visible de columnas editables (escalar + años).
  // Lo usan tanto el render de la tabla como las funciones de navegación.
  const cellKeysShown = useMemo<string[]>(() => {
    const filterYearsSet = new Set(filterYears);
    const yearsShown =
      filterYears.length > 0
        ? osemosysWideYears.filter((y) => filterYearsSet.has(String(y)))
        : osemosysWideYears;
    const scalarShown = osemosysHasScalar && filterYears.length === 0;
    const keys: string[] = [];
    if (scalarShown) keys.push("scalar");
    for (const y of yearsShown) keys.push(String(y));
    return keys;
  }, [filterYears, osemosysWideYears, osemosysHasScalar]);

  /** Mueve la selección (colapsa rango). */
  const moveSelection = useCallback(
    (drow: number, dcol: number) => {
      setSelectionEnd(null);
      setSelectedCell((prev) => {
        if (!prev) return prev;
        const nRows = osemosysWideRows.length;
        if (nRows === 0 || cellKeysShown.length === 0) return prev;
        const colIdx = cellKeysShown.indexOf(prev.yearKey);
        if (colIdx < 0) return prev;
        const newRow = Math.max(0, Math.min(nRows - 1, prev.rowIdx + drow));
        const newCol = Math.max(0, Math.min(cellKeysShown.length - 1, colIdx + dcol));
        return { rowIdx: newRow, yearKey: cellKeysShown[newCol]! };
      });
    },
    [osemosysWideRows.length, cellKeysShown],
  );

  /** Extiende el rango (Shift+flecha) sin mover el ancla `selectedCell`. */
  const extendSelection = useCallback(
    (drow: number, dcol: number) => {
      const nRows = osemosysWideRows.length;
      if (nRows === 0 || cellKeysShown.length === 0 || !selectedCell) return;
      const cur = selectionEnd ?? selectedCell;
      const colIdx = cellKeysShown.indexOf(cur.yearKey);
      if (colIdx < 0) return;
      const newRow = Math.max(0, Math.min(nRows - 1, cur.rowIdx + drow));
      const newCol = Math.max(0, Math.min(cellKeysShown.length - 1, colIdx + dcol));
      setSelectionEnd({ rowIdx: newRow, yearKey: cellKeysShown[newCol]! });
    },
    [osemosysWideRows.length, cellKeysShown, selectedCell, selectionEnd],
  );

  /** Rectángulo normalizado (r1≤r2, c1≤c2) o null. */
  const selectionRect = useMemo(() => {
    if (!selectedCell) return null;
    const end = selectionEnd ?? selectedCell;
    const c1raw = cellKeysShown.indexOf(selectedCell.yearKey);
    const c2raw = cellKeysShown.indexOf(end.yearKey);
    if (c1raw < 0 || c2raw < 0) return null;
    return {
      r1: Math.min(selectedCell.rowIdx, end.rowIdx),
      r2: Math.max(selectedCell.rowIdx, end.rowIdx),
      c1: Math.min(c1raw, c2raw),
      c2: Math.max(c1raw, c2raw),
    };
  }, [selectedCell, selectionEnd, cellKeysShown]);

  const isCellInSelection = useCallback(
    (rowIdx: number, yearKey: string) => {
      if (!selectionRect) return false;
      const c = cellKeysShown.indexOf(yearKey);
      return (
        rowIdx >= selectionRect.r1 &&
        rowIdx <= selectionRect.r2 &&
        c >= selectionRect.c1 &&
        c <= selectionRect.c2
      );
    },
    [selectionRect, cellKeysShown],
  );

  /** Construye TSV (\t entre celdas, \n entre filas) del rango actual. */
  const buildTsvFromSelection = useCallback((): string | null => {
    if (!selectionRect) return null;
    const lines: string[] = [];
    for (let r = selectionRect.r1; r <= selectionRect.r2; r++) {
      const row = osemosysWideRows[r];
      if (!row) continue;
      const cells: string[] = [];
      for (let c = selectionRect.c1; c <= selectionRect.c2; c++) {
        const yk = cellKeysShown[c]!;
        const cell = row.cells[yk];
        cells.push(cell ? formatCellValue(cell.value) : "");
      }
      lines.push(cells.join("\t"));
    }
    return lines.join("\n");
  }, [selectionRect, osemosysWideRows, cellKeysShown]);

  /** Inicia edición en la celda seleccionada. `prefill` reemplaza el valor inicial
   *  (útil para "type to edit": escribir un dígito empieza a editar con ese valor). */
  const startEditFromSelected = useCallback(
    (prefill?: string) => {
      if (!selectedCell || !canManageValues) return;
      const row = osemosysWideRows[selectedCell.rowIdx];
      if (!row) return;
      const cell = row.cells[selectedCell.yearKey];
      if (!cell) return; // No hay celda — usar "+ Año" para crear.
      setEditingCell({
        rowKey: row.group_key,
        yearKey: selectedCell.yearKey,
        valueId: cell.id,
        original: cell.value,
      });
      setCellDraft(prefill !== undefined ? prefill : String(cell.value));
    },
    [selectedCell, canManageValues, osemosysWideRows],
  );

  /** Listener global de teclado cuando hay celda seleccionada y no se está editando. */
  useEffect(() => {
    if (!selectedCell || editingCell) return;
    const onKey = (e: KeyboardEvent) => {
      // Si el foco está en otro input/select (modal, búsqueda, etc.), no robar.
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (target?.isContentEditable) return;

      // Ctrl/Cmd + C/V se manejan en otro listener (eventos copy/paste nativos).
      // Aquí sólo flechas/Tab/Enter/F2/Escape y "type-to-edit".
      switch (e.key) {
        case "ArrowUp":
          e.preventDefault();
          if (e.shiftKey) extendSelection(-1, 0);
          else moveSelection(-1, 0);
          return;
        case "ArrowDown":
          e.preventDefault();
          if (e.shiftKey) extendSelection(1, 0);
          else moveSelection(1, 0);
          return;
        case "ArrowLeft":
          e.preventDefault();
          if (e.shiftKey) extendSelection(0, -1);
          else moveSelection(0, -1);
          return;
        case "ArrowRight":
          e.preventDefault();
          if (e.shiftKey) extendSelection(0, 1);
          else moveSelection(0, 1);
          return;
        case "Tab":
          e.preventDefault();
          moveSelection(0, e.shiftKey ? -1 : 1);
          return;
        case "Enter":
          e.preventDefault();
          if (canManageValues) startEditFromSelected();
          return;
        case "F2":
          e.preventDefault();
          if (canManageValues) startEditFromSelected();
          return;
        case "Escape":
          e.preventDefault();
          setSelectionEnd(null);
          setSelectedCell(null);
          return;
        default:
          // Pasamos atajos del navegador (Ctrl/Cmd + algo) para que copy/paste/etc. funcionen.
          if (e.ctrlKey || e.metaKey || e.altKey) return;
          // "Type to edit": cualquier carácter imprimible numérico arranca edición
          // sustituyendo el valor (comportamiento Excel).
          if (
            canManageValues &&
            e.key.length === 1 &&
            /[0-9.\-,]/.test(e.key)
          ) {
            e.preventDefault();
            startEditFromSelected(e.key);
          }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [
    selectedCell,
    editingCell,
    moveSelection,
    extendSelection,
    startEditFromSelected,
    canManageValues,
  ]);

  /** Mantiene visible la celda activa: scroll automático al navegar o tras refresh.
   *
   * Se dispara con cambios en `selectedCell` (navegación) y en `osemosysWideRows`
   * (refresh post-paste). `block: "nearest"` evita scroll innecesario; `inline:
   * "nearest"` lo hace también horizontal. La extremidad del rango (`selectionEnd`)
   * también se considera para que extender con Shift+flecha siga visible.
   */
  useEffect(() => {
    const target = selectionEnd ?? selectedCell;
    if (!target) return;
    const root = tableScrollRef.current;
    if (!root) return;
    // Buscar la celda real por data-attrs. Usamos la API de selector con escape
    // por si yearKey contuviera caracteres especiales (no es el caso hoy).
    const sel = `td[data-cell-row="${target.rowIdx}"][data-cell-key="${CSS.escape(target.yearKey)}"]`;
    const el = root.querySelector<HTMLElement>(sel);
    if (el) {
      el.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [selectedCell, selectionEnd, osemosysWideRows]);

  /** Listener global de copiar/pegar para celdas seleccionadas (sin estar en edit). */
  useEffect(() => {
    if (!selectedCell || editingCell) return;
    const isFocusInInput = () => {
      const tag = (document.activeElement as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
      const el = document.activeElement as HTMLElement | null;
      return !!el?.isContentEditable;
    };

    const onCopy = (e: ClipboardEvent) => {
      if (isFocusInInput()) return; // No interferir con copy del navegador.
      const tsv = buildTsvFromSelection();
      if (tsv === null) return;
      e.preventDefault();
      e.clipboardData?.setData("text/plain", tsv);
    };

    const onPaste = (e: ClipboardEvent) => {
      if (isFocusInInput()) return;
      if (!canManageValues) return;
      const text = e.clipboardData?.getData("text/plain") ?? "";
      if (!text) return;
      e.preventDefault();
      // Soporta tanto valor simple como TSV multi-celda.
      const cleaned = text.replace(/\r\n?/g, "\n");
      const matrix = cleaned.split("\n").map((line) => line.split("\t"));
      while (matrix.length > 0 && matrix[matrix.length - 1]!.every((c) => c === "")) {
        matrix.pop();
      }
      if (matrix.length === 0) return;
      void pasteMatrixAt(matrix, {
        rowIdx: selectedCell.rowIdx,
        yearKey: selectedCell.yearKey,
      });
    };

    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);
    return () => {
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("paste", onPaste);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCell, editingCell, selectionRect, canManageValues]);

  // Carga escenario, permisos, valores OSeMOSYS y solicitudes pendientes al montar
  useEffect(() => {
    if (!Number.isFinite(scenarioId) || !user) return;
    const load = async () => {
      setLoading(true);
      try {
        const sc = await scenariosApi.getScenarioById(scenarioId);
        if (!sc) {
          setScenario(null);
          return;
        }
        setScenario(sc);
          setMetaForm({
            name: sc.name,
            description: sc.description ?? "",
            edit_policy: sc.edit_policy,
            simulation_type: sc.simulation_type,
          });
        setParentScenarioName(sc.base_scenario_name ?? null);

        const myAccess = await scenariosApi.getEffectivePermission(sc, user);
        setAccess(myAccess);

        if (sc.base_scenario_id && !sc.base_scenario_name) {
          try {
            const parent = await scenariosApi.getScenarioById(sc.base_scenario_id);
            setParentScenarioName(parent.name);
          } catch {
            setParentScenarioName(`#${sc.base_scenario_id}`);
          }
        }

        // Si la URL trae `?dq_*` (deep-link desde DataQualityModal), aplicamos
        // los filtros AQUÍ — antes del primer fetch — para evitar la race
        // condition entre el load inicial y un useEffect tardío.
        const dqParamNames = searchParams.get("dq_param_names");
        const dqRegions = searchParams.get("dq_region_names");
        const dqTechnologies = searchParams.get("dq_technology_names");
        const dqYear = searchParams.get("dq_year");
        let initialFilters: OsemosysWideFilters = {};
        if (dqParamNames || dqRegions || dqTechnologies || dqYear) {
          if (dqParamNames) initialFilters.param_names = dqParamNames.split(",").filter(Boolean);
          if (dqRegions) initialFilters.region_names = dqRegions.split(",").filter(Boolean);
          if (dqTechnologies) initialFilters.technology_names = dqTechnologies.split(",").filter(Boolean);
          setColumnFilters(initialFilters);
          if (dqYear) setFilterYears([dqYear]);
          setFiltersFromDataQuality(true);
          // Limpiar los dq_* de la URL preservando otros params.
          const cleaned = new URLSearchParams(searchParams);
          ["dq_param_names", "dq_region_names", "dq_technology_names", "dq_year"].forEach((k) =>
            cleaned.delete(k),
          );
          setSearchParams(cleaned, { replace: true });
        }

        await Promise.all([
          fetchOsemosysPage(sc.id, 1, osemosysPageSize, "", "", "", initialFilters),
          fetchFacets(sc.id, "", "", initialFilters),
        ]);

        if (myAccess.isOwner || myAccess.can_edit_direct) {
          const [perms, pendingList] = await Promise.all([
            scenariosApi.listPermissions(sc.id),
            scenariosApi.listPendingChangeRequests(sc.id),
          ]);
          setPermissions(perms);
          setPending(pendingList);
        } else {
          setPermissions([]);
          setPending([]);
        }
      } catch (err: unknown) {
        push(err instanceof Error ? err.message : "No se pudo cargar el escenario.", "error");
      } finally {
        setLoading(false);
      }
    };
    void load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId, user]);

  // Recarga al cambiar página
  useEffect(() => {
    if (!scenario) return;
    const merged = buildFilters(columnFilters, yearRules);
    void fetchOsemosysPage(scenario.id, osemosysPage, osemosysPageSize, osemosysSearch, filterParamName, filterYear, merged);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [osemosysPage, osemosysPageSize]);
  function openCreateOsemosys() {
    setEditingOsemosys(null);
    setOsemosysForm({
      param_name: "",
      region_name: "",
      technology_name: "",
      fuel_name: "",
      emission_name: "",
      udc_name: "",
      year: "",
      value: "",
    });
    setOpenOsemosysModal(true);
  }

  /** Guarda valor OSeMOSYS (crear o actualizar según si estamos editando) */
  async function submitOsemosysValue() {
    if (!scenario || !canManageValues) return;
    if (!osemosysForm.param_name.trim()) {
      push("El parámetro es obligatorio.", "error");
      return;
    }
    const numericValue = Number(osemosysForm.value);
    if (!Number.isFinite(numericValue)) {
      push("El valor debe ser numérico.", "error");
      return;
    }
    const payload = {
      param_name: osemosysForm.param_name.trim(),
      ...(osemosysForm.region_name.trim() ? { region_name: osemosysForm.region_name.trim() } : {}),
      ...(osemosysForm.technology_name.trim()
        ? { technology_name: osemosysForm.technology_name.trim() }
        : {}),
      ...(osemosysForm.fuel_name.trim() ? { fuel_name: osemosysForm.fuel_name.trim() } : {}),
      ...(osemosysForm.emission_name.trim() ? { emission_name: osemosysForm.emission_name.trim() } : {}),
      ...(osemosysForm.udc_name.trim() ? { udc_name: osemosysForm.udc_name.trim() } : {}),
      ...(osemosysForm.year.trim() ? { year: Number(osemosysForm.year) } : {}),
      value: numericValue,
    };
    try {
      if (editingOsemosys) {
        await scenariosApi.updateOsemosysValue(scenario.id, editingOsemosys.id, payload);
      } else {
        await scenariosApi.createOsemosysValue(scenario.id, payload);
      }
      setOpenOsemosysModal(false);
      await refreshOsemosysData(scenario.id);
      await refreshScenarioHeader(scenario.id);
      push("Valor OSeMOSYS guardado.", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo guardar el valor OSeMOSYS.", "error");
    }
  }

  /** Sintetiza un `OsemosysValueRow` desde un grupo wide + clave de celda.
   *
   * Necesario porque las propuestas/modal legacy esperan ese shape.
   */
  function widePairToRow(group: OsemosysWideRow, yearKey: string): OsemosysValueRow | null {
    const cell = group.cells[yearKey];
    if (!cell) return null;
    return {
      id: cell.id,
      id_scenario: scenarioId,
      param_name: group.param_name,
      region_name: group.region_name,
      technology_name: group.technology_name,
      fuel_name: group.fuel_name,
      emission_name: group.emission_name,
      udc_name: group.udc_name,
      year: yearKey === "scalar" ? null : Number(yearKey),
      value: cell.value,
    };
  }

  /** Trunca a máx. 4 decimales para visualización; el valor original se mantiene al editar. */
  function formatCellValue(v: number): string {
    if (!Number.isFinite(v)) return String(v);
    if (Number.isInteger(v)) return String(v);
    return Number.parseFloat(v.toFixed(4)).toString();
  }

  function startEditCell(rowKey: string, yearKey: string, cell: { id: number; value: number }) {
    setEditingCell({ rowKey, yearKey, valueId: cell.id, original: cell.value });
    setCellDraft(String(cell.value));
  }

  function cancelEditCell() {
    setEditingCell(null);
    setCellDraft("");
  }

  /** Persiste la edición inline de una celda. Sin cambio si el valor no varía.
   *
   * `advance`: tras commit, mueve la selección al vecino indicado. Permite que
   *  Enter avance hacia abajo y Tab a la derecha (comportamiento Excel).
   */
  async function commitEditCell(advance: "down" | "up" | "right" | "left" | null = null) {
    if (!editingCell || !scenario) return;
    const trimmed = cellDraft.trim();
    const nextValue = Number(trimmed);
    if (!trimmed || !Number.isFinite(nextValue)) {
      push("El valor debe ser numérico.", "error");
      return;
    }

    // Calcula la celda a la que avanzar (antes de cerrar la edición para tener acceso a editingCell).
    const computeAdvance = (): { rowIdx: number; yearKey: string } | null => {
      if (!advance) return null;
      const rowIdx = osemosysWideRows.findIndex((g) => g.group_key === editingCell.rowKey);
      if (rowIdx < 0) return null;
      const colIdx = cellKeysShown.indexOf(editingCell.yearKey);
      if (colIdx < 0) return null;
      const drow = advance === "down" ? 1 : advance === "up" ? -1 : 0;
      const dcol = advance === "right" ? 1 : advance === "left" ? -1 : 0;
      const newRow = Math.max(0, Math.min(osemosysWideRows.length - 1, rowIdx + drow));
      const newCol = Math.max(0, Math.min(cellKeysShown.length - 1, colIdx + dcol));
      return { rowIdx: newRow, yearKey: cellKeysShown[newCol]! };
    };
    const nextSel = computeAdvance();

    if (nextValue === editingCell.original) {
      // No-op: cancela y avanza si corresponde.
      cancelEditCell();
      if (nextSel) setSelectedCell(nextSel);
      return;
    }
    const group = osemosysWideRows.find((g) => g.group_key === editingCell.rowKey);
    if (!group) {
      cancelEditCell();
      return;
    }
    const yearKey = editingCell.yearKey;
    setCellSaving(true);
    try {
      const payload = {
        param_name: group.param_name,
        ...(group.region_name ? { region_name: group.region_name } : {}),
        ...(group.technology_name ? { technology_name: group.technology_name } : {}),
        ...(group.fuel_name ? { fuel_name: group.fuel_name } : {}),
        ...(group.emission_name ? { emission_name: group.emission_name } : {}),
        ...(group.udc_name ? { udc_name: group.udc_name } : {}),
        ...(yearKey !== "scalar" ? { year: Number(yearKey) } : {}),
        value: nextValue,
      };
      await scenariosApi.updateOsemosysValue(scenario.id, editingCell.valueId, payload);
      // Actualiza sólo la celda afectada para evitar recargar la página entera.
      setOsemosysWideRows((prev) =>
        prev.map((r) =>
          r.group_key === editingCell.rowKey
            ? { ...r, cells: { ...r.cells, [yearKey]: { id: editingCell.valueId, value: nextValue } } }
            : r,
        ),
      );
      await refreshScenarioHeader(scenario.id);
      push("Valor actualizado.", "success");
      setEditingCell(null);
      setCellDraft("");
      if (nextSel) setSelectedCell(nextSel);
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo guardar el valor.", "error");
    } finally {
      setCellSaving(false);
    }
  }

  /** Parsea texto del portapapeles como TSV (filas: `\n`, celdas: `\t`).
   *
   * Limpia retornos `\r`, descarta filas/celdas finales completamente vacías.
   * Retorna `null` si el texto es de una sola celda (no hay tab ni salto).
   */
  function parseTsvMatrix(text: string): string[][] | null {
    if (!text) return null;
    const cleaned = text.replace(/\r\n?/g, "\n");
    if (!cleaned.includes("\t") && !cleaned.includes("\n")) return null;
    const rows = cleaned.split("\n").map((line) => line.split("\t"));
    // Quitar filas finales totalmente vacías (algunos copy de Excel agregan).
    while (rows.length > 0 && rows[rows.length - 1]!.every((c) => c === "")) {
      rows.pop();
    }
    return rows.length > 0 ? rows : null;
  }

  /** Aplica una matriz TSV a partir de la celda en edición como ancla superior-izquierda.
   *
   * Para cada celda destino:
   *  - Parsea el valor; si no es numérico, salta.
   *  - Si la celda destino existe en la BD → PUT (update).
   *  - Si está vacía → POST (create) con las dims de la fila destino.
   * Llamadas en paralelo con concurrencia 6. Toast con resumen al terminar.
   */
  async function pasteMatrixAt(
    matrix: string[][],
    anchorOverride?: { rowIdx: number; yearKey: string },
  ) {
    if (!scenario || !canManageValues) return;
    // Anchor: explícito (paste por selección) o derivado de editingCell (paste durante edición).
    let anchorRowIdx: number;
    let anchorYearKey: string;
    if (anchorOverride) {
      anchorRowIdx = anchorOverride.rowIdx;
      anchorYearKey = anchorOverride.yearKey;
    } else if (editingCell) {
      anchorRowIdx = osemosysWideRows.findIndex((r) => r.group_key === editingCell.rowKey);
      anchorYearKey = editingCell.yearKey;
    } else {
      return;
    }
    if (anchorRowIdx < 0) return;

    const cellKeys = cellKeysShown;
    const anchorColIdx = cellKeys.indexOf(anchorYearKey);
    if (anchorColIdx < 0) return;

    type Task = () => Promise<{ kind: "ok"; isNew: boolean } | { kind: "skip" } | { kind: "err"; msg: string }>;
    const tasks: Task[] = [];
    let outOfBounds = 0;
    let nonNumeric = 0;

    for (let di = 0; di < matrix.length; di++) {
      const targetRow = osemosysWideRows[anchorRowIdx + di];
      if (!targetRow) {
        outOfBounds += matrix[di]!.length;
        continue;
      }
      const cells = matrix[di]!;
      for (let dj = 0; dj < cells.length; dj++) {
        const targetYearKey = cellKeys[anchorColIdx + dj];
        if (!targetYearKey) {
          outOfBounds++;
          continue;
        }
        const raw = (cells[dj] ?? "").trim();
        if (raw === "") continue; // Celda vacía en TSV: ignorar (sin sobrescribir).
        const numeric = Number(raw.replace(",", "."));
        if (!Number.isFinite(numeric)) {
          nonNumeric++;
          continue;
        }

        const groupForTask = targetRow;
        const yearKeyForTask = targetYearKey;
        const existingCell = groupForTask.cells[yearKeyForTask];
        const payload = {
          param_name: groupForTask.param_name,
          ...(groupForTask.region_name ? { region_name: groupForTask.region_name } : {}),
          ...(groupForTask.technology_name ? { technology_name: groupForTask.technology_name } : {}),
          ...(groupForTask.fuel_name ? { fuel_name: groupForTask.fuel_name } : {}),
          ...(groupForTask.emission_name ? { emission_name: groupForTask.emission_name } : {}),
          ...(groupForTask.udc_name ? { udc_name: groupForTask.udc_name } : {}),
          ...(yearKeyForTask !== "scalar" ? { year: Number(yearKeyForTask) } : {}),
          value: numeric,
        };

        if (existingCell) {
          // Skip si el valor no cambia.
          if (existingCell.value === numeric) continue;
          tasks.push(async () => {
            try {
              await scenariosApi.updateOsemosysValue(scenario.id, existingCell.id, payload);
              return { kind: "ok", isNew: false };
            } catch (e) {
              return { kind: "err", msg: e instanceof Error ? e.message : "update fail" };
            }
          });
        } else {
          tasks.push(async () => {
            try {
              await scenariosApi.createOsemosysValue(scenario.id, payload);
              return { kind: "ok", isNew: true };
            } catch (e) {
              return { kind: "err", msg: e instanceof Error ? e.message : "create fail" };
            }
          });
        }
      }
    }

    if (tasks.length === 0) {
      const parts: string[] = [];
      if (outOfBounds > 0) parts.push(`${outOfBounds} fuera de la tabla`);
      if (nonNumeric > 0) parts.push(`${nonNumeric} no numéricas`);
      push(parts.length ? `Nada que pegar (${parts.join(", ")}).` : "Nada que pegar.", "info");
      return;
    }

    if (tasks.length > 500) {
      const ok = window.confirm(
        `Vas a actualizar ${tasks.length} celdas. Esto tomará varios segundos. ¿Continuar?`,
      );
      if (!ok) return;
    }

    setCellSaving(true);
    try {
      // Pool de concurrencia 6 — equilibrio entre throughput y carga al backend.
      const CONCURRENCY = 6;
      let updated = 0;
      let created = 0;
      let failed = 0;
      let cursor = 0;
      const workers = Array.from({ length: Math.min(CONCURRENCY, tasks.length) }, async () => {
        while (cursor < tasks.length) {
          const idx = cursor++;
          const res = await tasks[idx]!();
          if (res.kind === "ok") {
            if (res.isNew) created++;
            else updated++;
          } else if (res.kind === "err") {
            failed++;
          }
        }
      });
      await Promise.all(workers);

      const parts: string[] = [];
      if (updated > 0) parts.push(`${updated} actualizada(s)`);
      if (created > 0) parts.push(`${created} creada(s)`);
      if (failed > 0) parts.push(`${failed} fallida(s)`);
      if (nonNumeric > 0) parts.push(`${nonNumeric} no numéricas`);
      if (outOfBounds > 0) parts.push(`${outOfBounds} fuera de tabla`);
      push(`Pegado: ${parts.join(", ")}.`, failed > 0 ? "error" : "success");

      // Refresca tabla y header para reflejar todo (ids nuevos, total de combinaciones).
      await refreshOsemosysData(scenario.id);
      await refreshScenarioHeader(scenario.id);
      cancelEditCell();
    } finally {
      setCellSaving(false);
    }
  }

  /** Borra TODAS las celdas (años y escalar) de una combinación en `osemosys_param_value`.
   *
   * Equivale a desactivar la fila entera del formato wide. Pide confirmación
   * explícita indicando el número de celdas que se eliminarán.
   */
  async function deactivateWideRow(group: OsemosysWideRow) {
    if (!scenario || !canManageValues) return;
    const cellIds = Object.values(group.cells).map((c) => c.id);
    if (cellIds.length === 0) return;
    const descr = `${group.param_name} · ${group.technology_name ?? "—"} · ${group.fuel_name ?? "—"}`;
    const confirmed = window.confirm(
      `Eliminar ${cellIds.length} celda(s) de esta combinación?\n\n${descr}\n\n` +
        "Esto borra físicamente las filas en la base de datos (queda registro en auditoría).",
    );
    if (!confirmed) return;
    try {
      await Promise.all(cellIds.map((id) => scenariosApi.deactivateOsemosysValue(scenario.id, id)));
      setOsemosysWideRows((prev) => prev.filter((r) => r.group_key !== group.group_key));
      await refreshScenarioHeader(scenario.id);
      push("Combinación eliminada.", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo eliminar la combinación.", "error");
    }
  }

  /** Crea solicitud de cambio para un valor; en política OPEN se aplica directo */
  async function submitProposal() {
    if (!scenario || !proposeFor) return;
    const newValue = Number(proposalNewValue);
    if (!Number.isFinite(newValue)) {
      push("El nuevo valor debe ser numérico.", "error");
      return;
    }
    try {
      const created = await scenariosApi.createChangeRequest({
        id_osemosys_param_value: proposeFor.id,
        new_value: newValue,
      });
      if (scenario.edit_policy !== "OPEN" && (access?.isOwner || access?.can_edit_direct)) {
        setPending((prev) => [created, ...prev]);
      } else {
        await refreshOsemosysData(scenario.id);
        await refreshScenarioHeader(scenario.id);
      }
      setProposeFor(null);
      setProposalNewValue("");
      push("Solicitud de cambio creada.", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo crear la solicitud.", "error");
    }
  }


  function resetExcelUpdateState() {
    setExcelUpdateFile(null);
    setExcelUpdateSheets([]);
    setExcelUpdateSelectedSheet("");
    setExcelPreviewData(null);
    setExcelPreviewWarnings([]);
    setExcelPreviewNotFound(0);
    setExcelPreviewTotalRows(0);
    setExcelSelectedRowIds(new Set());
    setExcelApplyResult(null);
    setExcelApplyJob(null);
    setExcelPreviewSearch("");
    setExcelPreviewPage(1);
    setExcelPreviewPageSize(200);
    setExcelPreviewUploadPhase("idle");
    setExcelPreviewUploadPercent(0);
    setExcelPreviewUploadStartedAt(null);
    setExcelCollapseTimeslices(true);
  }

  function handleExcelUpdateFileChange(file: File | null) {
    setExcelUpdateFile(file);
    setExcelUpdateSheets([]);
    setExcelUpdateSelectedSheet("");
    setExcelPreviewData(null);
    setExcelApplyResult(null);
    setExcelPreviewPage(1);
    setExcelPreviewUploadPhase("idle");
    setExcelPreviewUploadPercent(0);
    setExcelPreviewUploadStartedAt(null);
  }

  async function loadExcelUpdateSheets() {
    if (!excelUpdateFile) return;
    setExcelUpdateLoadingSheets(true);
    try {
      const res = await officialImportApi.listWorkbookSheets(excelUpdateFile);
      setExcelUpdateSheets(res.sheets);
      if (res.sheets.length >= 1) {
        setExcelUpdateSelectedSheet(res.sheets[0] ?? "");
      }
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudieron leer las hojas del Excel.", "error");
    } finally {
      setExcelUpdateLoadingSheets(false);
    }
  }

  async function handleDownloadExcel(format: "sand" | "raw") {
    if (!scenario) return;
    setExcelDownloading(true);
    try {
      const { blob, filename } = await scenariosApi.downloadScenarioExcel(scenario.id, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      push(`Descarga ${format.toUpperCase()} iniciada.`, "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo descargar el Excel.", "error");
    } finally {
      setExcelDownloading(false);
    }
  }

  async function submitExcelPreview() {
    if (!scenario || !excelUpdateFile || !excelUpdateSelectedSheet.trim()) return;
    setExcelPreviewLoading(true);
    setExcelPreviewData(null);
    setExcelApplyResult(null);
    setExcelPreviewPage(1);
    setExcelExpandedGroupKeys(new Set());
    setExcelPreviewUploadPhase("uploading");
    setExcelPreviewUploadPercent(0);
    setExcelPreviewUploadStartedAt(Date.now());
    try {
      const result = await scenariosApi.previewScenarioFromExcel(
        scenario.id,
        {
          file: excelUpdateFile,
          sheet_name: excelUpdateSelectedSheet,
          collapse_timeslices: excelCollapseTimeslices,
        },
        (percent) => {
          setExcelPreviewUploadPercent(percent);
          if (percent >= 100) setExcelPreviewUploadPhase("processing");
        },
      );
      setExcelPreviewData(result.changes);
      setExcelPreviewWarnings(result.warnings);
      setExcelPreviewNotFound(result.not_found);
      setExcelPreviewTotalRows(result.total_rows_read);
      // El backend ya solo devuelve filas con valor distinto; todas son candidatas a aplicar
      const selected = new Set(result.changes.map((ch) => ch.preview_id));
      setExcelSelectedRowIds(selected);
      if (result.changes.length === 0) {
        push("No se detectaron cambios respecto al escenario actual.", "info");
      }
      setExcelPreviewUploadPhase("done");
    } catch (err) {
      setExcelPreviewUploadPhase("error");
      push(err instanceof Error ? err.message : "Error generando preview.", "error");
    } finally {
      setExcelPreviewLoading(false);
    }
  }

  async function submitExcelApply() {
    if (!scenario || !excelPreviewData) return;
    const toApply = excelPreviewData
      .filter((r) => excelSelectedRowIds.has(r.preview_id))
      .map((r) => ({
        preview_id: r.preview_id,
        action: r.action,
        row_id: r.row_id,
        param_name: r.param_name,
        region_name: r.region_name,
        technology_name: r.technology_name,
        fuel_name: r.fuel_name,
        emission_name: r.emission_name,
        timeslice_code: r.timeslice_code,
        mode_of_operation_code: r.mode_of_operation_code,
        season_code: r.season_code,
        daytype_code: r.daytype_code,
        dailytimebracket_code: r.dailytimebracket_code,
        storage_set_code: r.storage_set_code,
        udc_set_code: r.udc_set_code,
        year: r.year,
        new_value: r.new_value,
      }));
    if (toApply.length === 0) {
      push("No hay cambios seleccionados para aplicar.", "info");
      return;
    }
    setExcelApplyLoading(true);
    try {
      const job = await scenariosApi.applyExcelChangesAsync(scenario.id, toApply);
      setExcelApplyJob(job);
      push("Actualización iniciada. Puedes ver el avance en este popup.", "info");
    } catch (err) {
      push(err instanceof Error ? err.message : "Error aplicando cambios.", "error");
      setExcelApplyLoading(false);
    }
  }

  useEffect(() => {
    if (!excelApplyJob) return;
    const isActive = excelApplyJob.status === "QUEUED" || excelApplyJob.status === "RUNNING";
    if (!isActive) return;
    const timer = window.setInterval(() => {
      void scenariosApi
        .getScenarioOperationById(excelApplyJob.id)
        .then(async (job) => {
          setExcelApplyJob(job);
          if (job.status === "SUCCEEDED") {
            const result = job.result_json as { updated?: number; inserted?: number; skipped?: number } | null;
            setExcelApplyResult({
              updated: Number(result?.updated ?? 0),
              inserted: Number(result?.inserted ?? 0),
              skipped: Number(result?.skipped ?? 0),
            });
            setExcelApplyLoading(false);
            if (scenario) {
              await refreshOsemosysData(scenario.id);
              await refreshScenarioHeader(scenario.id);
            }
            push("Actualización completada correctamente.", "success");
          } else if (job.status === "FAILED") {
            setExcelApplyLoading(false);
            push(job.error_message ?? "La actualización asíncrona falló.", "error");
          }
        })
        .catch(() => {
          // No interrumpimos el flujo por errores transitorios de polling.
        });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [excelApplyJob, push, refreshOsemosysData, refreshScenarioHeader, scenario]);

  useEffect(() => {
    const updateViewportMode = () => {
      setIsPreviewNarrowViewport(window.innerWidth < PREVIEW_NARROW_BREAKPOINT);
    };
    updateViewportMode();
    window.addEventListener("resize", updateViewportMode);
    return () => window.removeEventListener("resize", updateViewportMode);
  }, []);

  const excelPreviewFiltered = useMemo(() => {
    if (!excelPreviewData) return [];
    const term = excelPreviewSearch.trim().toLowerCase();
    if (!term) return excelPreviewData;
    return excelPreviewData.filter((r) =>
      [r.param_name, r.region_name, r.technology_name, r.fuel_name, r.emission_name, r.year?.toString()]
        .filter(Boolean)
        .some((v) => v!.toLowerCase().includes(term)),
    );
  }, [excelPreviewData, excelPreviewSearch]);

  const excelPreviewTotalPages = useMemo(
    () => Math.max(1, Math.ceil(excelPreviewFiltered.length / excelPreviewPageSize)),
    [excelPreviewFiltered.length, excelPreviewPageSize],
  );

  const excelPreviewCurrentPage = Math.min(excelPreviewPage, excelPreviewTotalPages);
  const excelPreviewPageRows = useMemo(() => {
    const start = (excelPreviewCurrentPage - 1) * excelPreviewPageSize;
    return excelPreviewFiltered.slice(start, start + excelPreviewPageSize);
  }, [excelPreviewCurrentPage, excelPreviewPageSize, excelPreviewFiltered]);

  const excelPreviewGroupedPage = useMemo<PreviewGroup[]>(() => {
    const grouped = new Map<string, PreviewGroup>();
    for (const row of excelPreviewPageRows) {
      const key = buildPreviewGroupKey(row);
      const existing = grouped.get(key);
      if (existing) {
        existing.rows.push(row);
      } else {
        grouped.set(key, {
          key,
          param_name: row.param_name,
          region_name: row.region_name,
          technology_name: row.technology_name,
          fuel_name: row.fuel_name,
          emission_name: row.emission_name,
          rows: [row],
        });
      }
    }
    return Array.from(grouped.values());
  }, [excelPreviewPageRows]);

  useEffect(() => {
    if (!excelPreviewGroupedPage.length) {
      setExcelExpandedGroupKeys(new Set());
      return;
    }
    setExcelExpandedGroupKeys((prev) => {
      const next = new Set<string>();
      for (const group of excelPreviewGroupedPage) {
        if (prev.has(group.key)) next.add(group.key);
      }
      if (next.size === 0) {
        for (const group of excelPreviewGroupedPage.slice(0, 8)) {
          next.add(group.key);
        }
      }
      return next;
    });
  }, [excelPreviewGroupedPage]);

  const policyExplanation = useMemo(() => {
    if (!scenario) return "";
    return getPolicyExplanation(scenario.edit_policy);
  }, [scenario]);

  const policyLabel = useMemo(() => {
    if (!scenario) return "";
    if (scenario.edit_policy === "OWNER_ONLY") return "Solo propietario";
    if (scenario.edit_policy === "OPEN") return "Abierta";
    return "Restringida";
  }, [scenario]);

  async function submitScenarioMetadata() {
    if (!scenario || !canEditScenarioMeta) return;
    if (!metaForm.name.trim()) {
      push("El nombre del escenario es obligatorio.", "error");
      return;
    }
    try {
      const updated = await scenariosApi.updateScenario(scenario.id, {
        name: metaForm.name.trim(),
        description: metaForm.description.trim() || null,
        edit_policy: metaForm.edit_policy,
        simulation_type: metaForm.simulation_type,
      });
      setScenario(updated);
      setMetaForm({
        name: updated.name,
        description: updated.description ?? "",
        edit_policy: updated.edit_policy,
        simulation_type: updated.simulation_type,
      });
      setParentScenarioName(updated.base_scenario_name ?? parentScenarioName);
      setOpenMetaModal(false);
      push("Metadatos del escenario actualizados.", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo actualizar el escenario.", "error");
    }
  }

  async function submitPermission() {
    if (!scenario) return;
    const identifier = permForm.user_identifier.trim()
      ? permForm.user_identifier.trim()
      : permForm.username.trim()
        ? `user:${permForm.username.trim()}`
        : "";
    if (!identifier) {
      push("Ingresa el username o el identificador del usuario.", "error");
      return;
    }
    try {
      const permissionPayload = {
        user_identifier: identifier,
        can_edit_direct: permForm.can_edit_direct,
        can_propose: permForm.can_propose,
        can_manage_values: permForm.can_manage_values,
      };
      const upserted = await scenariosApi.upsertPermission(scenario.id, permissionPayload);
      setPermissions((prev) => {
        const exists = prev.some((p) => p.id === upserted.id);
        return exists ? prev.map((p) => (p.id === upserted.id ? upserted : p)) : [upserted, ...prev];
      });
      setOpenPermModal(false);
      push("Permiso actualizado.", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo actualizar el permiso.", "error");
    }
  }

  async function reviewRequest(changeRequestId: number, decision: "APPROVED" | "REJECTED") {
    if (!scenario) return;
    try {
      await scenariosApi.reviewChangeRequest(changeRequestId, decision);
      const nextPending = await scenariosApi.listPendingChangeRequests(scenario.id);
      setPending(nextPending);
      await refreshOsemosysData(scenario.id);
      await refreshScenarioHeader(scenario.id);
      push(`Solicitud ${decision === "APPROVED" ? "aprobada" : "rechazada"}.`, "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo procesar la solicitud.", "error");
    }
  }

  // Estados de carga y error antes del render principal
  if (loading) return <section className="pageSection">Cargando escenario...</section>;
  if (!scenario) return <section className="pageSection">Escenario no encontrado.</section>;

  return (
    <section className="pageSection" style={{ display: "grid", gap: 14 }}>
      <div className="toolbarRow">
        <div>
          <h1 style={{ margin: 0 }}>{scenario.name}</h1>
          <p style={{ margin: "6px 0 0", opacity: 0.75 }}>{scenario.description}</p>
          {(scenario.tags && scenario.tags.length > 0) || scenario.tag ? (
            <div style={{ marginTop: 8, display: "flex", gap: 4, flexWrap: "wrap" }}>
              {(scenario.tags ?? (scenario.tag ? [scenario.tag] : [])).map((t) => (
                <ScenarioTagChip key={t.id} tag={t} size="sm" showCategory />
              ))}
            </div>
          ) : null}
          <small style={{ opacity: 0.7 }}>
            Política de edición: <strong>{policyLabel}</strong> · {policyExplanation}
          </small>
        </div>
        {canEditScenarioMeta ? (
          <Button
            variant="ghost"
            onClick={() => {
              setMetaForm({
                name: scenario.name,
                description: scenario.description ?? "",
                edit_policy: scenario.edit_policy,
                simulation_type: scenario.simulation_type,
              });
              setOpenMetaModal(true);
            }}
          >
            Editar escenario
          </Button>
        ) : null}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Button variant={tab === "values" ? "primary" : "ghost"} onClick={() => setTab("values")}>
          Valores
        </Button>
        <Button
          variant={tab === "permissions" ? "primary" : "ghost"}
          onClick={() => setTab("permissions")}
        >
          Permisos
        </Button>
        <Button variant={tab === "pending" ? "primary" : "ghost"} onClick={() => setTab("pending")}>
          Solicitudes pendientes
        </Button>
      </div>

      {tab === "values" ? (
        <div style={{ display: "grid", gap: 10 }}>
          <div className="toolbarRow">
            <h3 style={{ margin: 0 }}>Valores OSeMOSYS por escenario</h3>
            <div style={{ display: "flex", gap: 8 }}>
              <Button
                variant="ghost"
                onClick={() => void handleDownloadExcel("sand")}
                disabled={excelDownloading}
              >
                {excelDownloading ? "Descargando..." : "Descargar SAND"}
              </Button>
              <Button
                variant="ghost"
                onClick={() => void handleDownloadExcel("raw")}
                disabled={excelDownloading}
              >
                {excelDownloading ? "Descargando..." : "Descargar RAW"}
              </Button>
              {canManageValues ? (
                <>
                  <Button variant="primary" onClick={openCreateOsemosys}>
                    Agregar valor
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      resetExcelUpdateState();
                      setOpenExcelUpdateModal(true);
                    }}
                  >
                    Editar desde Excel
                  </Button>
                </>
              ) : null}
            </div>
          </div>
          <small style={{ opacity: 0.75 }}>
            Estos son los valores base de simulación (`osemosys_param_value`) importados desde Excel.
          </small>
          <small style={{ opacity: 0.7 }}>
            SAND agrupa años por fila; RAW exporta una fila por registro.
          </small>

          <article style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, padding: 14, display: "grid", gap: 8 }}>
            <h4 style={{ margin: 0 }}>Lineage</h4>
            {scenario.base_scenario_id ? (
              <>
                <div style={{ opacity: 0.82 }}>
                  Hijo de <strong>{parentScenarioName ?? scenario.base_scenario_name ?? `#${scenario.base_scenario_id}`}</strong>
                </div>
                <small style={{ opacity: 0.76 }}>
                  Se guarda una referencia simple de los parámetros tocados en este escenario para ayudar a recordar qué cambió.
                </small>
                {scenario.changed_param_names && scenario.changed_param_names.length > 0 ? (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {scenario.changed_param_names.map((paramName) => (
                      <Badge key={paramName} variant="info">
                        {paramName}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p style={{ margin: 0, opacity: 0.78 }}>
                    Todavía no hay parámetros marcados como modificados en este escenario derivado.
                  </p>
                )}
              </>
            ) : (
              <p style={{ margin: 0, opacity: 0.78 }}>Este escenario no tiene padre directo.</p>
            )}
          </article>

          {/* Banner si los filtros vienen del modal de calidad. */}
          {filtersFromDataQuality && (hasActiveColumnFilters || filterYears.length > 0) && (
            <div
              role="status"
              style={{
                padding: "10px 14px",
                borderRadius: 8,
                background: "rgba(245,158,11,0.10)",
                border: "1px solid rgba(245,158,11,0.40)",
                color: "var(--text)",
                fontSize: 13,
                lineHeight: 1.4,
                display: "flex",
                gap: 12,
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <span aria-hidden style={{ fontSize: 16 }}>⚠</span>
              <div style={{ flex: 1 }}>
                <strong>Vista filtrada desde el reporte de calidad.</strong>{" "}
                Estás viendo solo las filas que contribuyen al conflicto detectado.
                Edita los valores que necesites y luego abre <em>Calidad de datos</em>
                {" "}desde la lista de escenarios y pulsa <em>Refrescar</em> para
                recalcular el reporte.
              </div>
              <Button
                variant="ghost"
                onClick={() => {
                  setFilterYears([]);
                  clearAllColumnFilters();
                  setFiltersFromDataQuality(false);
                }}
              >
                Quitar filtro
              </Button>
            </div>
          )}

          {/* Filtros activos: chips visibles arriba de la tabla. */}
          {(hasActiveColumnFilters || filterYears.length > 0) && (
            <div
              style={{
                padding: "10px 12px",
                borderRadius: 8,
                background: "rgba(56,189,248,0.06)",
                border: "1px solid rgba(56,189,248,0.30)",
                display: "flex",
                gap: 8,
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <span style={{ fontSize: 12, opacity: 0.85, fontWeight: 600 }}>
                Filtros activos:
              </span>
              {(["param_names", "region_names", "technology_names", "fuel_names", "emission_names", "udc_names"] as const).map(
                (col) => {
                  const values = columnFilters[col];
                  if (!Array.isArray(values) || values.length === 0) return null;
                  const labelByCol: Record<string, string> = {
                    param_names: "Parámetro",
                    region_names: "Región",
                    technology_names: "Tecnología",
                    fuel_names: "Combustible",
                    emission_names: "Emisión",
                    udc_names: "UDC",
                  };
                  return (
                    <FilterChip
                      key={col}
                      label={labelByCol[col] ?? col}
                      values={values}
                      onClear={() => applyColumnFilter(col, [])}
                    />
                  );
                },
              )}
              {filterYears.length > 0 && (
                <FilterChip
                  label="Año"
                  values={filterYears}
                  onClear={() => setFilterYears([])}
                />
              )}
              <div style={{ marginLeft: "auto" }}>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setFilterYears([]);
                    clearAllColumnFilters();
                    setFiltersFromDataQuality(false);
                  }}
                >
                  Limpiar todo
                </Button>
              </div>
            </div>
          )}

          {/* Años visibles (selector compacto) */}
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
              <span style={{ opacity: 0.8 }}>Años visibles:</span>
              <ColumnFilterPopover
                columnLabel="Años visibles"
                options={osemosysWideYears.map((y) => String(y))}
                selected={filterYears}
                onChange={setFilterYears}
              />
              <small style={{ opacity: 0.65 }}>
                {filterYears.length === 0 ? "todos" : `${filterYears.length} seleccionados`}
              </small>
            </div>
          </div>

          {osemosysLoading ? (
            <div style={{ padding: 20, textAlign: "center", opacity: 0.7 }}>Cargando...</div>
          ) : (
            <>
              {(() => {
                const selectedYearsSet = new Set(filterYears);
                const yearsShown = filterYears.length > 0
                  ? osemosysWideYears.filter((y) => selectedYearsSet.has(String(y)))
                  : osemosysWideYears;
                // Escalar se oculta si hay selección explícita de años (no lo incluye).
                const scalarShown = osemosysHasScalar && filterYears.length === 0;
                type CatColKey = "param_names" | "region_names" | "technology_names" | "fuel_names" | "emission_names" | "udc_names";
                const dimHeaders: { label: string; filterKey: CatColKey; facetKey: keyof OsemosysWideFacets }[] = [
                  { label: "Parámetro", filterKey: "param_names", facetKey: "param_names" },
                  { label: "Región", filterKey: "region_names", facetKey: "region_names" },
                  { label: "Tecnología", filterKey: "technology_names", facetKey: "technology_names" },
                  { label: "Combustible", filterKey: "fuel_names", facetKey: "fuel_names" },
                  { label: "Emisión", filterKey: "emission_names", facetKey: "emission_names" },
                  { label: "UDC", filterKey: "udc_names", facetKey: "udc_names" },
                ];
                const totalCols =
                  dimHeaders.length + (scalarShown ? 1 : 0) + yearsShown.length + 1;
                return (
                  <div
                    ref={tableScrollRef}
                    style={{
                      overflow: "auto",
                      maxHeight: "70vh",
                      border: "1px solid rgba(255,255,255,0.08)",
                      borderRadius: 12,
                    }}
                  >
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead style={{ background: "rgba(255,255,255,0.03)" }}>
                        <tr>
                          {dimHeaders.map((h) => (
                            <th
                              key={h.label}
                              style={{
                                textAlign: "left",
                                fontSize: 13,
                                padding: "8px 10px",
                                color: "var(--muted)",
                                position: "sticky",
                                top: 0,
                                background: "rgba(20,20,24,0.95)",
                                whiteSpace: "nowrap",
                              }}
                            >
                              <span style={{ display: "inline-flex", alignItems: "center" }}>
                                {h.label}
                                <ColumnFilterPopover
                                  columnLabel={h.label}
                                  options={facets?.[h.facetKey] ?? []}
                                  selected={columnFilters[h.filterKey] ?? []}
                                  loading={facetsLoading}
                                  onChange={(next) => applyColumnFilter(h.filterKey, next)}
                                />
                              </span>
                            </th>
                          ))}
                          {scalarShown ? (
                            <th
                              style={{
                                textAlign: "right",
                                fontSize: 13,
                                padding: "10px 12px",
                                color: "var(--muted)",
                                background: "rgba(20,20,24,0.95)",
                                position: "sticky",
                                top: 0,
                              }}
                            >
                              Valor (no temporal)
                            </th>
                          ) : null}
                          {yearsShown.map((y) => (
                            <th
                              key={y}
                              style={{
                                textAlign: "right",
                                fontSize: 13,
                                padding: "8px 10px",
                                color: "var(--muted)",
                                background: "rgba(20,20,24,0.95)",
                                whiteSpace: "nowrap",
                                position: "sticky",
                                top: 0,
                              }}
                            >
                              <span style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
                                {y}
                                <YearRuleFilterPopover
                                  year={y}
                                  rule={yearRules[String(y)] ?? null}
                                  onChange={(r) => applyYearRule(y, r)}
                                />
                              </span>
                            </th>
                          ))}
                          <th
                            style={{
                              textAlign: "left",
                              fontSize: 13,
                              padding: "10px 12px",
                              color: "var(--muted)",
                              background: "rgba(20,20,24,0.95)",
                              position: "sticky",
                              top: 0,
                            }}
                          >
                            Acciones
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {osemosysWideRows.length === 0 ? (
                          <tr>
                            <td colSpan={totalCols} style={{ padding: 14, opacity: 0.75 }}>
                              Sin registros.
                            </td>
                          </tr>
                        ) : (
                          osemosysWideRows.map((g, rowIdx) => {
                            const cellKeys: string[] = [];
                            if (scalarShown) cellKeys.push("scalar");
                            for (const y of yearsShown) cellKeys.push(String(y));
                            return (
                              <tr key={g.group_key} style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                                <td style={{ padding: "4px 10px", fontSize: 13 }}>{g.param_name}</td>
                                <td style={{ padding: "4px 10px", fontSize: 13 }}>{g.region_name ?? "—"}</td>
                                <td style={{ padding: "4px 10px", fontSize: 13 }}>{g.technology_name ?? "—"}</td>
                                <td style={{ padding: "4px 10px", fontSize: 13 }}>{g.fuel_name ?? "—"}</td>
                                <td style={{ padding: "4px 10px", fontSize: 13 }}>{g.emission_name ?? "—"}</td>
                                <td style={{ padding: "4px 10px", fontSize: 13 }}>{g.udc_name ?? "—"}</td>
                                {cellKeys.map((yearKey) => {
                                  const cell = g.cells[yearKey];
                                  const isEditing =
                                    editingCell?.rowKey === g.group_key && editingCell.yearKey === yearKey;
                                  const isAnchor =
                                    !isEditing &&
                                    selectedCell?.rowIdx === rowIdx &&
                                    selectedCell.yearKey === yearKey;
                                  const inRange = !isEditing && isCellInSelection(rowIdx, yearKey);
                                  const canEdit = canManageValues && !!cell;
                                  const canPropose = !canManageValues && !!access?.can_propose && !!cell;
                                  // Click: marca selección + colapsa rango. Si tiene celda y es editable, inicia edit.
                                  // Shift+Click: extiende rango sin entrar a edit.
                                  const onClick = (ev: React.MouseEvent) => {
                                    if (ev.shiftKey) {
                                      // Extender rango si ya hay ancla; si no, fija ancla.
                                      if (selectedCell) setSelectionEnd({ rowIdx, yearKey });
                                      else setSelectedCell({ rowIdx, yearKey });
                                      return;
                                    }
                                    setSelectionEnd(null);
                                    setSelectedCell({ rowIdx, yearKey });
                                    if (!cell) return;
                                    if (canManageValues) {
                                      startEditCell(g.group_key, yearKey, cell);
                                    } else if (canPropose) {
                                      const row = widePairToRow(g, yearKey);
                                      if (row) setProposeFor(row);
                                    }
                                  };
                                  return (
                                    <td
                                      key={yearKey}
                                      // data-attrs para que el efecto de scrollIntoView pueda
                                      // localizar la celda activa por consulta DOM.
                                      data-cell-row={rowIdx}
                                      data-cell-key={yearKey}
                                      style={{
                                        padding: "2px 8px",
                                        textAlign: "right",
                                        fontSize: 13,
                                        fontVariantNumeric: "tabular-nums",
                                        cursor: "pointer",
                                        background: isEditing
                                          ? "rgba(80,140,255,0.08)"
                                          : isAnchor
                                            ? "rgba(80,140,255,0.10)"
                                            : inRange
                                              ? "rgba(80,140,255,0.05)"
                                              : undefined,
                                        outline: isAnchor ? "2px solid rgba(80,140,255,0.8)" : undefined,
                                        outlineOffset: isAnchor ? "-2px" : undefined,
                                      }}
                                      onClick={isEditing ? undefined : onClick}
                                      title={
                                        cell
                                          ? `Valor: ${cell.value}${
                                              canEdit
                                                ? " · Click para editar · ↑↓←→ para navegar"
                                                : canPropose
                                                  ? " · Click para proponer cambio"
                                                  : ""
                                            }`
                                          : "Sin valor — usar «Agregar valor» para crear"
                                      }
                                    >
                                      {!cell ? (
                                        <span style={{ opacity: 0.35 }}>—</span>
                                      ) : isEditing ? (
                                        <input
                                          autoFocus
                                          // type="text" en vez de "number" para que el navegador
                                          // entregue al onPaste el contenido COMPLETO (number
                                          // sólo deja pasar el primer dígito de TSV multi-celda).
                                          type="text"
                                          inputMode="decimal"
                                          value={cellDraft}
                                          disabled={cellSaving}
                                          onChange={(e) => setCellDraft(e.target.value)}
                                          onPaste={(e) => {
                                            const text = e.clipboardData.getData("text/plain");
                                            const matrix = parseTsvMatrix(text);
                                            if (matrix === null) return; // single-cell paste: deja al input.
                                            // Multi-celda: interceptamos.
                                            e.preventDefault();
                                            void pasteMatrixAt(matrix);
                                          }}
                                          onKeyDown={(e) => {
                                            // Excel-style: Enter↓, Shift+Enter↑, Tab→, Shift+Tab←, Esc cancela.
                                            if (e.key === "Enter") {
                                              e.preventDefault();
                                              void commitEditCell(e.shiftKey ? "up" : "down");
                                            } else if (e.key === "Tab") {
                                              e.preventDefault();
                                              void commitEditCell(e.shiftKey ? "left" : "right");
                                            } else if (e.key === "Escape") {
                                              e.preventDefault();
                                              cancelEditCell();
                                              setSelectedCell({ rowIdx, yearKey });
                                            }
                                          }}
                                          onBlur={() => {
                                            if (!cellSaving) void commitEditCell();
                                          }}
                                          style={{
                                            width: "100%",
                                            minWidth: 80,
                                            padding: "2px 6px",
                                            textAlign: "right",
                                            fontVariantNumeric: "tabular-nums",
                                            background: "transparent",
                                            border: "1px solid rgba(80,140,255,0.45)",
                                            borderRadius: 4,
                                            color: "inherit",
                                          }}
                                        />
                                      ) : (
                                        formatCellValue(cell.value)
                                      )}
                                    </td>
                                  );
                                })}
                                <td style={{ padding: "4px 8px" }}>
                                  {canManageValues ? (
                                    <div style={{ display: "flex", gap: 4 }}>
                                      <button
                                        type="button"
                                        className="wide-icon-btn"
                                        aria-label="Agregar año"
                                        title="Agregar año a esta combinación"
                                        onClick={() => {
                                          // Abrir el modal legacy para crear una nueva celda (año) en este grupo.
                                          setEditingOsemosys(null);
                                          setOsemosysForm({
                                            param_name: g.param_name,
                                            region_name: g.region_name ?? "",
                                            technology_name: g.technology_name ?? "",
                                            fuel_name: g.fuel_name ?? "",
                                            emission_name: g.emission_name ?? "",
                                            udc_name: g.udc_name ?? "",
                                            year: "",
                                            value: "",
                                          });
                                          setOpenOsemosysModal(true);
                                        }}
                                      >
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                          <line x1="12" y1="5" x2="12" y2="19" />
                                          <line x1="5" y1="12" x2="19" y2="12" />
                                        </svg>
                                      </button>
                                      {Object.keys(g.cells).length > 0 ? (
                                        <button
                                          type="button"
                                          className="wide-icon-btn wide-icon-btn--danger"
                                          aria-label="Eliminar combinación"
                                          title="Eliminar TODAS las celdas de esta combinación (hard delete)"
                                          onClick={() => void deactivateWideRow(g)}
                                        >
                                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                            <line x1="6" y1="6" x2="18" y2="18" />
                                            <line x1="18" y1="6" x2="6" y2="18" />
                                          </svg>
                                        </button>
                                      ) : null}
                                    </div>
                                  ) : (
                                    <span style={{ opacity: 0.65, fontSize: 12 }}>—</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                );
              })()}

              {/* Paginación server-side */}
              {(() => {
                const totalPages = Math.max(1, Math.ceil(osemosysTotal / osemosysPageSize));
                return (
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <small style={{ opacity: 0.75 }}>
                        Página {osemosysPage} de {totalPages}
                      </small>
                      <small style={{ opacity: 0.75 }}>
                        · {osemosysTotal.toLocaleString()} combinaciones en total
                      </small>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, opacity: 0.85 }}>
                        Por página:
                        <select
                          value={osemosysPageSize}
                          onChange={(e) => {
                            setOsemosysPageSize(Number(e.target.value) || 50);
                            setOsemosysPage(1);
                          }}
                          style={{ padding: "2px 6px", borderRadius: 6, background: "transparent", color: "inherit" }}
                        >
                          {PAGE_SIZE_OPTIONS.map((n) => (
                            <option key={n} value={n}>{n}</option>
                          ))}
                        </select>
                      </label>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button
                          className="btn btn--ghost"
                          type="button"
                          disabled={osemosysPage <= 1}
                          onClick={() => setOsemosysPage((p) => Math.max(1, p - 1))}
                        >
                          Anterior
                        </button>
                        <button
                          className="btn btn--ghost"
                          type="button"
                          disabled={osemosysPage >= totalPages}
                          onClick={() => setOsemosysPage((p) => Math.min(totalPages, p + 1))}
                        >
                          Siguiente
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </>
          )}
        </div>
      ) : null}

      {tab === "permissions" ? (
        <div style={{ display: "grid", gap: 10 }}>
          <div className="toolbarRow">
            <h3 style={{ margin: 0 }}>Permisos del escenario</h3>
            {canManagePermissions ? (
              <Button variant="primary" onClick={() => setOpenPermModal(true)}>
                Agregar / editar permiso
              </Button>
            ) : (
              <small style={{ opacity: 0.75 }}>Visible solo para propietario o administradores del escenario.</small>
            )}
          </div>
          {canManagePermissions ? (
            <DataTable
              rows={permissions}
              rowKey={(r) => String(r.id)}
              columns={[
                {
                  key: "identifier",
                  header: "Usuario",
                  render: (r) => (r.user_identifier.startsWith("user:") ? r.user_identifier.slice(5) : r.user_identifier),
                },
                {
                  key: "edit",
                  header: "Administra",
                  render: (r) => (
                    <Badge variant={r.can_edit_direct ? "success" : "neutral"}>{r.can_edit_direct ? "Sí" : "No"}</Badge>
                  ),
                },
                {
                  key: "prop",
                  header: "Puede proponer",
                  render: (r) => (
                    <Badge variant={r.can_propose ? "success" : "neutral"}>{r.can_propose ? "Sí" : "No"}</Badge>
                  ),
                },
                {
                  key: "manage",
                  header: "Gestiona valores",
                  render: (r) => (
                    <Badge variant={r.can_manage_values ? "success" : "neutral"}>
                      {r.can_manage_values ? "Sí" : "No"}
                    </Badge>
                  ),
                },
              ]}
              searchableText={(r) => `${r.user_identifier}`}
            />
          ) : (
            <p style={{ opacity: 0.8 }}>No tienes permisos para administrar esta sección.</p>
          )}
        </div>
      ) : null}

      {tab === "pending" ? (
        <div style={{ display: "grid", gap: 10 }}>
          <h3 style={{ margin: 0 }}>Solicitudes pendientes</h3>
          <DataTable
            rows={pending}
            rowKey={(r) => String(r.id)}
            columns={[
              { key: "req", header: "Solicitante", render: (r) => r.created_by },
              { key: "change", header: "Cambio", render: (r) => `${r.old_value} → ${r.new_value}` },
              { key: "date", header: "Fecha", render: (r) => new Date(r.created_at).toLocaleString() },
              {
                key: "act",
                header: "Acciones",
                render: (r) =>
                  canManagePermissions ? (
                    <div style={{ display: "flex", gap: 8 }}>
                      <Button variant="primary" onClick={() => reviewRequest(r.id, "APPROVED")}>
                        Aprobar
                      </Button>
                      <Button variant="ghost" onClick={() => reviewRequest(r.id, "REJECTED")}>
                        Rechazar
                      </Button>
                    </div>
                  ) : (
                    <span style={{ opacity: 0.65 }}>Solo propietario / administradores</span>
                  ),
              },
            ]}
            searchableText={(r) => `${r.created_by} ${r.status}`}
          />
        </div>
      ) : null}

      <Modal
        open={openMetaModal}
        title="Editar escenario"
        onClose={() => setOpenMetaModal(false)}
        footer={
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Button variant="ghost" onClick={() => setOpenMetaModal(false)}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={() => void submitScenarioMetadata()}>
              Guardar cambios
            </Button>
          </div>
        }
      >
        <div style={{ display: "grid", gap: 10 }}>
          <TextField label="Nombre" value={metaForm.name} onChange={(e) => setMetaForm((prev) => ({ ...prev, name: e.target.value }))} />
          <TextField label="Descripción" value={metaForm.description} onChange={(e) => setMetaForm((prev) => ({ ...prev, description: e.target.value }))} />
          <label className="field">
            <span className="field__label">Política de edición</span>
            <select
              className="field__input"
              value={metaForm.edit_policy}
              onChange={(e) =>
                setMetaForm((prev) => ({
                  ...prev,
                  edit_policy: e.target.value as ScenarioEditPolicy,
                }))
              }
            >
              <option value="OWNER_ONLY">Solo propietario</option>
              <option value="OPEN">Abierta</option>
              <option value="RESTRICTED">Restringida</option>
            </select>
          </label>
          <label className="field">
            <span className="field__label">Tipo de simulación</span>
            <select
              className="field__input"
              value={metaForm.simulation_type}
              onChange={(e) =>
                setMetaForm((prev) => ({
                  ...prev,
                  simulation_type: e.target.value as SimulationType,
                }))
              }
            >
              <option value="NATIONAL">Nacional</option>
              <option value="REGIONAL">Regional</option>
            </select>
          </label>
          <small style={{ opacity: 0.75 }}>{getPolicyExplanation(metaForm.edit_policy)}</small>
          {scenario && canEditScenarioMeta ? (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                Etiquetas
              </div>
              <ScenarioTagsPanel
                scenarioId={scenario.id}
                scenarioName={scenario.name}
                tags={scenario.tags ?? (scenario.tag ? [scenario.tag] : [])}
                categories={scenarioTagCategories}
                availableTags={scenarioTags}
                canEdit
                onTagsChange={(next) => {
                  setScenario((prev) =>
                    prev ? { ...prev, tags: next, tag: next[0] ?? null } : prev,
                  );
                }}
              />
            </div>
          ) : null}
        </div>
      </Modal>

      <Modal
        open={openOsemosysModal}
        title={editingOsemosys ? "Editar valor OSeMOSYS" : "Crear valor OSeMOSYS"}
        onClose={() => setOpenOsemosysModal(false)}
        footer={
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Button variant="ghost" onClick={() => setOpenOsemosysModal(false)}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={() => void submitOsemosysValue()}>
              Guardar
            </Button>
          </div>
        }
      >
        <div style={{ display: "grid", gap: 10 }}>
          <TextField
            label="Parámetro"
            value={osemosysForm.param_name}
            list="osemosys-param-suggestions"
            onChange={(e) => setOsemosysForm((p) => ({ ...p, param_name: e.target.value }))}
          />
          <datalist id="osemosys-param-suggestions">
            {catalogSuggestions.parameters.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <TextField
            label="Región (opcional)"
            value={osemosysForm.region_name}
            list="osemosys-region-suggestions"
            onChange={(e) => setOsemosysForm((p) => ({ ...p, region_name: e.target.value }))}
          />
          <datalist id="osemosys-region-suggestions">
            {catalogSuggestions.regions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <TextField
            label="Tecnología (opcional)"
            value={osemosysForm.technology_name}
            list="osemosys-tech-suggestions"
            onChange={(e) => setOsemosysForm((p) => ({ ...p, technology_name: e.target.value }))}
          />
          <datalist id="osemosys-tech-suggestions">
            {catalogSuggestions.technologies.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <TextField
            label="Combustible (opcional)"
            value={osemosysForm.fuel_name}
            list="osemosys-fuel-suggestions"
            onChange={(e) => setOsemosysForm((p) => ({ ...p, fuel_name: e.target.value }))}
          />
          <datalist id="osemosys-fuel-suggestions">
            {catalogSuggestions.fuels.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <TextField
            label="Emisión (opcional)"
            value={osemosysForm.emission_name}
            list="osemosys-emission-suggestions"
            onChange={(e) => setOsemosysForm((p) => ({ ...p, emission_name: e.target.value }))}
          />
          <datalist id="osemosys-emission-suggestions">
            {catalogSuggestions.emissions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <TextField
            label="UDC (opcional)"
            value={osemosysForm.udc_name}
            list="osemosys-udc-suggestions"
            onChange={(e) => setOsemosysForm((p) => ({ ...p, udc_name: e.target.value }))}
          />
          <datalist id="osemosys-udc-suggestions">
            {catalogSuggestions.udcs.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <TextField
            label="Año (opcional)"
            type="number"
            value={osemosysForm.year}
            onChange={(e) => setOsemosysForm((p) => ({ ...p, year: e.target.value }))}
          />
          <TextField
            label="Valor"
            type="number"
            value={osemosysForm.value}
            onChange={(e) => setOsemosysForm((p) => ({ ...p, value: e.target.value }))}
          />
        </div>
      </Modal>

      <Modal
        open={openPermModal}
        title="Agregar / editar permiso"
        onClose={() => setOpenPermModal(false)}
        footer={
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Button variant="ghost" onClick={() => setOpenPermModal(false)}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={submitPermission}>
              Guardar permiso
            </Button>
          </div>
        }
      >
        <div style={{ display: "grid", gap: 10 }}>
          <TextField
            label="Username del usuario"
            value={permForm.username}
            onChange={(e) => setPermForm((p) => ({ ...p, username: e.target.value }))}
          />
          <TextField
            label="Identificador (opcional, si no es username)"
            value={permForm.user_identifier}
            onChange={(e) => setPermForm((p) => ({ ...p, user_identifier: e.target.value }))}
          />
          <label>
            <input
              type="checkbox"
              checked={permForm.can_edit_direct}
              onChange={(e) => setPermForm((p) => ({ ...p, can_edit_direct: e.target.checked }))}
            />{" "}
            Administra el escenario
          </label>
          <label>
            <input
              type="checkbox"
              checked={permForm.can_propose}
              onChange={(e) => setPermForm((p) => ({ ...p, can_propose: e.target.checked }))}
            />{" "}
            Puede proponer cambios
          </label>
          <label>
            <input
              type="checkbox"
              checked={permForm.can_manage_values}
              onChange={(e) => setPermForm((p) => ({ ...p, can_manage_values: e.target.checked }))}
            />{" "}
            Gestiona valores
          </label>
        </div>
      </Modal>

      <Modal
        open={Boolean(proposeFor)}
        title="Proponer cambio OSeMOSYS"
        onClose={() => setProposeFor(null)}
        footer={
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Button variant="ghost" onClick={() => setProposeFor(null)}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={() => void submitProposal()}>
              Crear solicitud
            </Button>
          </div>
        }
      >
        <div style={{ display: "grid", gap: 10 }}>
          <div style={{ opacity: 0.8 }}>
            Valor actual: <strong>{proposeFor?.value}</strong>
          </div>
          <TextField
            label="Nuevo valor"
            type="number"
            value={proposalNewValue}
            onChange={(e) => setProposalNewValue(e.target.value)}
          />
        </div>
      </Modal>

      <Modal
        open={openExcelUpdateModal}
        title={
          excelApplyResult
            ? "Resultado de actualización"
            : excelPreviewData
              ? "Vista previa de cambios"
              : "Editar escenario desde Excel"
        }
        onClose={() => {
          if (!excelPreviewLoading && !excelApplyLoading) setOpenExcelUpdateModal(false);
        }}
        footer={
          excelApplyResult ? (
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <Button variant="primary" onClick={() => setOpenExcelUpdateModal(false)}>
                Cerrar
              </Button>
            </div>
          ) : excelPreviewData ? (
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <Button
                variant="ghost"
                disabled={excelApplyLoading}
                onClick={() => {
                  setExcelPreviewData(null);
                  setExcelSelectedRowIds(new Set());
                  setExcelPreviewSearch("");
                  setExcelExpandedGroupKeys(new Set());
                }}
              >
                Volver
              </Button>
              <div style={{ display: "flex", gap: 8 }}>
                <Button variant="ghost" disabled={excelApplyLoading} onClick={() => setOpenExcelUpdateModal(false)}>
                  Cancelar
                </Button>
                <Button
                  variant="primary"
                  disabled={excelApplyLoading || excelSelectedRowIds.size === 0}
                  onClick={() => void submitExcelApply()}
                >
                  {excelApplyLoading
                    ? "Aplicando..."
                    : `Aplicar ${excelSelectedRowIds.size} cambio${excelSelectedRowIds.size !== 1 ? "s" : ""}`}
                </Button>
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <Button
                variant="ghost"
                disabled={excelPreviewLoading}
                onClick={() => setOpenExcelUpdateModal(false)}
              >
                Cancelar
              </Button>
              <Button
                variant="primary"
                disabled={excelPreviewLoading || !excelUpdateFile || !excelUpdateSelectedSheet}
                onClick={() => void submitExcelPreview()}
              >
                {excelPreviewLoading ? "Analizando..." : "Vista previa"}
              </Button>
            </div>
          )
        }
      >
        <div style={{ display: "grid", gap: 14 }}>
          {/* ── Carga durante análisis ── */}
          {excelPreviewLoading ? (
            <UploadProgress
              phase={excelPreviewUploadPhase}
              uploadPercent={excelPreviewUploadPercent}
              fileSizeBytes={excelUpdateFile?.size ?? 0}
              startedAt={excelPreviewUploadStartedAt}
            />
          ) : excelApplyResult ? (
            <div
              style={{
                padding: 14,
                borderRadius: 10,
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                display: "grid",
                gap: 6,
                fontSize: 14,
              }}
            >
              <strong>Actualización completada</strong>
              <div>
                Registros actualizados:{" "}
                <strong style={{ color: "var(--success, #4caf50)" }}>{excelApplyResult.updated}</strong>
              </div>
              <div>
                Registros insertados:{" "}
                <strong style={{ color: "var(--success, #4caf50)" }}>{excelApplyResult.inserted}</strong>
              </div>
              {excelApplyResult.skipped > 0 && (
                <div>
                  Omitidos:{" "}
                  <strong style={{ color: "var(--warning, #ff9800)" }}>{excelApplyResult.skipped}</strong>
                </div>
              )}
            </div>
          ) : excelPreviewData ? (
            /* ── Paso 2: Preview con tabla seleccionable ── */
            <>
              {excelApplyLoading && excelApplyJob ? (
                <div
                  style={{
                    padding: 10,
                    borderRadius: 10,
                    border: "1px solid rgba(255,255,255,0.1)",
                    background: "rgba(255,255,255,0.03)",
                    display: "grid",
                    gap: 4,
                    fontSize: 13,
                  }}
                >
                  <strong>Procesando actualización...</strong>
                  <span>
                    Estado: {excelApplyJob.status} · {Math.round(excelApplyJob.progress)}%
                  </span>
                  <span style={{ opacity: 0.85 }}>
                    {excelApplyJob.message ?? excelApplyJob.stage ?? "Aplicando cambios al escenario."}
                  </span>
                </div>
              ) : null}
              <div
                style={{
                  display: "flex",
                  gap: 16,
                  flexWrap: "wrap",
                  fontSize: 13,
                  opacity: 0.85,
                }}
              >
                <span>Filas leídas: <strong>{excelPreviewTotalRows}</strong></span>
                <span>
                  Filas detectadas (update + insert):{" "}
                  <strong style={{ color: "var(--success, #4caf50)" }}>{excelPreviewData.length}</strong>
                </span>
                <span>
                  No encontrados:{" "}
                  <strong style={{ color: excelPreviewNotFound > 0 ? "var(--warning, #ff9800)" : "inherit" }}>
                    {excelPreviewNotFound}
                  </strong>
                </span>
                <span>
                  Seleccionados: <strong>{excelSelectedRowIds.size}</strong> / {excelPreviewData.length}
                </span>
              </div>
              <small style={{ opacity: 0.75 }}>
                Solo se muestran parámetros cuyo valor difiere del actual (se leyeron {excelPreviewTotalRows} filas del Excel).
                {" "}El preview refleja el procesamiento SAND completo (defaults, agregación por timeslice y derivados).
              </small>

              {excelPreviewWarnings.length > 0 && (
                <details>
                  <summary style={{ cursor: "pointer", opacity: 0.85, fontSize: 13 }}>
                    Advertencias ({excelPreviewWarnings.length})
                  </summary>
                  <ul style={{ maxHeight: 150, overflow: "auto", fontSize: 12, margin: "6px 0 0", paddingLeft: 18 }}>
                    {excelPreviewWarnings.map((w, i) => (
                      <li key={i} style={{ opacity: 0.8 }}>{w}</li>
                    ))}
                  </ul>
                </details>
              )}

              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <Button
                  variant="ghost"
                  onClick={() => {
                    const allIds = new Set(excelPreviewData.map((r) => r.preview_id));
                    setExcelSelectedRowIds(allIds);
                  }}
                >
                  Seleccionar todos
                </Button>
                <Button variant="ghost" onClick={() => setExcelSelectedRowIds(new Set())}>
                  Deseleccionar todos
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    const changed = new Set<string>();
                    for (const r of excelPreviewData) {
                      if (r.old_value === null || Math.abs(r.old_value - r.new_value) > 1e-12) {
                        changed.add(r.preview_id);
                      }
                    }
                    setExcelSelectedRowIds(changed);
                  }}
                >
                  Solo con cambios
                </Button>
                <div style={{ marginLeft: "auto", maxWidth: 260 }}>
                  <input
                    type="text"
                    placeholder="Buscar en preview..."
                    value={excelPreviewSearch}
                    onChange={(e) => {
                      setExcelPreviewSearch(e.target.value);
                      setExcelPreviewPage(1);
                    }}
                    style={{
                      width: "100%",
                      padding: "6px 10px",
                      borderRadius: 8,
                      background: "var(--surface, #1a1a2e)",
                      color: "inherit",
                      border: "1px solid rgba(255,255,255,0.12)",
                      fontSize: 13,
                    }}
                  />
                </div>
              </div>

              <div
                style={{
                  maxHeight: 440,
                  overflowY: "auto",
                  overflowX: isPreviewNarrowViewport ? "auto" : "hidden",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                  padding: 10,
                }}
              >
                {excelPreviewFiltered.length === 0 ? (
                  <div style={{ padding: 18, opacity: 0.7, textAlign: "center" }}>
                    {excelPreviewSearch.trim() ? "Sin resultados para la búsqueda." : "No hay cambios para mostrar."}
                  </div>
                ) : (
                  <div
                    style={{
                      display: "grid",
                      gap: 10,
                      minWidth: isPreviewNarrowViewport ? 760 : "unset",
                    }}
                  >
                    {excelPreviewGroupedPage.map((group) => {
                      const groupIds = group.rows.map((r) => r.preview_id);
                      const selectedInGroup = groupIds.filter((id) => excelSelectedRowIds.has(id)).length;
                      const allGroupSelected = selectedInGroup > 0 && selectedInGroup === groupIds.length;
                      const expanded = excelExpandedGroupKeys.has(group.key);
                      const hasNewRows = group.rows.some((r) => r.action === "insert");
                      return (
                        <section
                          key={group.key}
                          style={{
                            border: "1px solid rgba(255,255,255,0.08)",
                            borderRadius: 10,
                            background: "rgba(255,255,255,0.02)",
                          }}
                        >
                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "auto 1fr auto auto",
                              alignItems: "center",
                              gap: 10,
                              padding: "11px 12px",
                              borderBottom: expanded ? "1px solid rgba(255,255,255,0.06)" : "none",
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={allGroupSelected}
                              onChange={(e) => {
                                setExcelSelectedRowIds((prev) => {
                                  const next = new Set(prev);
                                  if (e.target.checked) {
                                    for (const id of groupIds) next.add(id);
                                  } else {
                                    for (const id of groupIds) next.delete(id);
                                  }
                                  return next;
                                });
                              }}
                            />
                            <div style={{ minWidth: 0 }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                <strong>{group.param_name}</strong>
                                {hasNewRows ? (
                                  <span
                                    style={{
                                      fontSize: 11,
                                      padding: "2px 8px",
                                      borderRadius: 999,
                                      border: "1px solid rgba(91, 192, 222, 0.45)",
                                      background: "rgba(91, 192, 222, 0.18)",
                                      color: "#c9f0ff",
                                    }}
                                  >
                                    Nuevo
                                  </span>
                                ) : null}
                              </div>
                              <div style={{ marginTop: 3, fontSize: 12, opacity: 0.82 }}>
                                Región: {group.region_name ?? <span style={{ color: "rgba(255,255,255,0.45)" }}>—</span>}
                                {" · "}
                                Tecnología: {group.technology_name ?? <span style={{ color: "rgba(255,255,255,0.45)" }}>—</span>}
                                {" · "}
                                Combustible: {group.fuel_name ?? <span style={{ color: "rgba(255,255,255,0.45)" }}>—</span>}
                                {" · "}
                                Emisión: {group.emission_name ?? <span style={{ color: "rgba(255,255,255,0.45)" }}>—</span>}
                              </div>
                            </div>
                            <small style={{ opacity: 0.75 }}>
                              {selectedInGroup}/{group.rows.length}
                            </small>
                            <button
                              type="button"
                              className="btn btn--ghost"
                              onClick={() => {
                                setExcelExpandedGroupKeys((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(group.key)) next.delete(group.key);
                                  else next.add(group.key);
                                  return next;
                                });
                              }}
                            >
                              {expanded ? "Ocultar" : "Expandir"}
                            </button>
                          </div>

                          {expanded ? (
                            <div style={{ padding: "8px 12px 12px" }}>
                              <div
                                style={{
                                  display: "grid",
                                  gridTemplateColumns:
                                    "36px minmax(90px, 0.9fr) minmax(120px, 1fr) minmax(120px, 1fr)",
                                  gap: 10,
                                  padding: "7px 4px",
                                  fontSize: 12,
                                  color: "var(--muted)",
                                  borderBottom: "1px solid rgba(255,255,255,0.06)",
                                }}
                              >
                                <span />
                                <strong style={{ textAlign: "right" }}>Año</strong>
                                <strong style={{ textAlign: "right" }}>Valor actual</strong>
                                <strong style={{ textAlign: "right" }}>Nuevo valor</strong>
                              </div>
                              {group.rows.map((r) => {
                                const unchanged = r.old_value !== null && Math.abs(r.old_value - r.new_value) <= 1e-12;
                                const isSelected = excelSelectedRowIds.has(r.preview_id);
                                return (
                                  <div
                                    key={r.preview_id}
                                    style={{
                                      display: "grid",
                                      gridTemplateColumns:
                                        "36px minmax(90px, 0.9fr) minmax(120px, 1fr) minmax(120px, 1fr)",
                                      gap: 10,
                                      alignItems: "center",
                                      padding: "9px 4px",
                                      borderBottom: "1px solid rgba(255,255,255,0.05)",
                                      opacity: unchanged ? 0.55 : isSelected ? 1 : 0.7,
                                      background: isSelected && !unchanged ? "rgba(76,175,80,0.06)" : "transparent",
                                    }}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={isSelected}
                                      onChange={() => {
                                        setExcelSelectedRowIds((prev) => {
                                          const next = new Set(prev);
                                          if (next.has(r.preview_id)) next.delete(r.preview_id);
                                          else next.add(r.preview_id);
                                          return next;
                                        });
                                      }}
                                    />
                                    <div style={{ textAlign: "right", fontFamily: "monospace" }}>
                                      {r.year ?? <span style={{ color: "rgba(255,255,255,0.45)" }}>—</span>}
                                    </div>
                                    <div style={{ textAlign: "right", fontFamily: "monospace" }}>
                                      {r.old_value ?? <span style={{ color: "rgba(255,255,255,0.45)" }}>—</span>}
                                    </div>
                                    <div
                                      style={{
                                        textAlign: "right",
                                        fontFamily: "monospace",
                                        fontWeight: unchanged ? 400 : 600,
                                        color: unchanged ? "inherit" : "var(--success, #4caf50)",
                                      }}
                                    >
                                      {r.new_value}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          ) : null}
                        </section>
                      );
                    })}
                  </div>
                )}
              </div>
              {excelPreviewFiltered.length > 0 ? (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <small style={{ opacity: 0.75 }}>
                    Mostrando {(excelPreviewCurrentPage - 1) * excelPreviewPageSize + 1}-
                    {Math.min(excelPreviewCurrentPage * excelPreviewPageSize, excelPreviewFiltered.length)} de{" "}
                    {excelPreviewFiltered.length.toLocaleString()} cambios filtrados
                  </small>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, opacity: 0.85 }}>
                      Filas:
                      <select
                        value={excelPreviewPageSize}
                        onChange={(e) => {
                          setExcelPreviewPageSize(Number(e.target.value) || 200);
                          setExcelPreviewPage(1);
                        }}
                        style={{ padding: "2px 6px", borderRadius: 6, background: "transparent", color: "inherit" }}
                      >
                        {PREVIEW_PAGE_SIZE_OPTIONS.map((size) => (
                          <option key={size} value={size}>
                            {size}
                          </option>
                        ))}
                      </select>
                    </label>
                    <small style={{ opacity: 0.75 }}>
                      Página {excelPreviewCurrentPage} de {excelPreviewTotalPages}
                    </small>
                    <button
                      className="btn btn--ghost"
                      type="button"
                      disabled={excelPreviewCurrentPage <= 1}
                      onClick={() => setExcelPreviewPage((p) => Math.max(1, p - 1))}
                    >
                      Anterior
                    </button>
                    <button
                      className="btn btn--ghost"
                      type="button"
                      disabled={excelPreviewCurrentPage >= excelPreviewTotalPages}
                      onClick={() => setExcelPreviewPage((p) => Math.min(excelPreviewTotalPages, p + 1))}
                    >
                      Siguiente
                    </button>
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            /* ── Paso 1: Seleccionar archivo y hoja ── */
            <>
              <div>
                <label style={{ display: "block", marginBottom: 6, fontSize: 13, fontWeight: 500 }}>
                  Archivo Excel (.xlsm / .xlsx)
                </label>
                <input
                  type="file"
                  accept=".xlsm,.xlsx,.xls"
                  disabled={excelPreviewLoading}
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    handleExcelUpdateFileChange(f);
                  }}
                />
              </div>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <Button
                  variant="ghost"
                  onClick={() => void loadExcelUpdateSheets()}
                  disabled={!excelUpdateFile || excelUpdateLoadingSheets}
                >
                  {excelUpdateLoadingSheets ? "Leyendo hojas..." : "Listar hojas"}
                </Button>
                <small style={{ opacity: 0.75 }}>Para archivos grandes, este paso puede tardar unos segundos.</small>
              </div>

              <label className="field">
                <span className="field__label">Hoja a importar</span>
                <select
                  className="field__input"
                  value={excelUpdateSelectedSheet}
                  disabled={excelPreviewLoading || !excelUpdateSheets.length}
                  onChange={(e) => setExcelUpdateSelectedSheet(e.target.value)}
                >
                  <option value="">{excelUpdateSheets.length ? "Selecciona..." : "Primero lista las hojas"}</option>
                  {excelUpdateSheets.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </label>

              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: "pointer",
                  userSelect: "none",
                  fontSize: 13,
                }}
              >
                <input
                  type="checkbox"
                  checked={excelCollapseTimeslices}
                  onChange={(e) => setExcelCollapseTimeslices(e.target.checked)}
                  disabled={excelPreviewLoading}
                />
                Agregar/colapsar timeslices al comparar con el escenario (desmarcar para usar timeslices del Excel)
              </label>

              <small style={{ opacity: 0.65 }}>
                Se analizará el archivo y se mostrará una vista previa de los cambios antes de aplicarlos.
                Se podrán aplicar actualizaciones e inserciones de nuevos registros.
                La detección usa paridad total con el procesamiento SAND.
              </small>
            </>
          )}
        </div>
      </Modal>

    </section>
  );
}


/**
 * Chip que muestra un filtro activo con su valor (o conteo si son varios)
 * y un botón "×" para limpiarlo. Usado en la barra de "Filtros activos".
 */
function FilterChip({
  label,
  values,
  onClear,
}: {
  label: string;
  values: string[];
  onClear: () => void;
}) {
  const display =
    values.length === 1
      ? values[0]
      : values.length <= 3
        ? values.join(", ")
        : `${values.slice(0, 2).join(", ")} +${values.length - 2}`;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 8px 4px 10px",
        borderRadius: 999,
        background: "rgba(56,189,248,0.14)",
        border: "1px solid rgba(56,189,248,0.40)",
        fontSize: 12,
        maxWidth: 320,
      }}
      title={values.join(", ")}
    >
      <span style={{ opacity: 0.75 }}>{label}:</span>
      <strong style={{
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        maxWidth: 220,
      }}>{display}</strong>
      <button
        type="button"
        onClick={onClear}
        title={`Quitar filtro de ${label}`}
        aria-label={`Quitar filtro de ${label}`}
        style={{
          marginLeft: 2,
          background: "transparent",
          border: "none",
          color: "inherit",
          cursor: "pointer",
          fontSize: 14,
          lineHeight: 1,
          padding: "2px 4px",
          opacity: 0.75,
        }}
      >
        ×
      </button>
    </span>
  );
}
