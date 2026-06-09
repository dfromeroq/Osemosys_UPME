/**
 * Catálogo de pestañas del Data Explorer: categorías madre + subcategorías.
 *
 * Filosofía de los presets:
 *  - "Demanda" y "Oferta & Transformación" filtran **por prefijo de tecnología**
 *    (DEM* vs PWR/HDG/UPS/...). No restringen variables — el usuario elige la
 *    variable con el tercer nivel de pills o con el popover de Variable.
 *  - "Emisiones", "Costos" y "Storage" filtran **por variable** (conjuntos
 *    específicos). Si aplica, también por `emission_names`.
 *  - "Todos" no filtra nada.
 *
 * Los prefijos se resuelven en cliente contra `facets.technology_names`, ya
 * que el backend sólo acepta `technology_names` como lista IN(...).
 */

export type CategoryFilters = {
  variable_names?: string[];
  /** Resolver contra facets.technology_names via startsWith() */
  technology_prefixes?: string[];
  /**
   * Resolver contra facets.fuel_names via startsWith(). Usado en categorías
   * donde algunas variables se indexan por combustible (no por tecnología),
   * para mostrarlas en el tercer nivel vía unión tech ∪ fuel.
   */
  fuel_prefixes?: string[];
  emission_names?: string[];
};

export type SubCategory = {
  id: string;
  label: string;
  icon?: string;
  filters: CategoryFilters;
};

export type Category = {
  id: string;
  label: string;
  icon?: string;
  filters: CategoryFilters;
  sub?: SubCategory[];
};

// ---------------------------------------------------------------------------
//  Conjuntos de variables para Emisiones / Costos / Storage
// ---------------------------------------------------------------------------
//  Se incluyen TANTO los nombres del refactor reciente (48 variables) como los
//  nombres ya persistidos antes del refactor — así los jobs viejos también
//  renderean algo al seleccionar un preset.

const VAR_EMISIONES = [
  "AnnualEmissions",
  "AnnualTechnologyEmission",
  "AnnualTechnologyEmissionByMode",
  "AnnualTechnologyEmissionPenaltyByEmission",
  "ModelPeriodEmissions",
  "AnnualTechnologyEmissionsPenalty",
  "DiscountedTechnologyEmissionsPenalty",
];

const VAR_COSTOS = [
  "CapitalInvestment",
  "DiscountedCapitalInvestment",
  "OperatingCost",
  "DiscountedOperatingCost",
  "VariableOperatingCost",
  "AnnualVariableOperatingCost",
  "AnnualFixedOperatingCost",
  "SalvageValue",
  "DiscountedSalvageValue",
  "TotalDiscountedCost",
  "TotalDiscountedCostByTechnology",
  "DisposalCost",
  "DiscountedDisposalCost",
  "RecoveryValue",
  "DiscountedRecoveryValue",
];

const VAR_STORAGE = [
  "NewStorageCapacity",
  "SalvageValueStorage",
  "StorageLevelYearStart",
  "StorageLevelYearFinish",
  "StorageLevelSeasonStart",
  "StorageLevelDayTypeStart",
  "StorageLevelDayTypeFinish",
  "StorageLowerLimit",
  "StorageUpperLimit",
  "AccumulatedNewStorageCapacity",
  "CapitalInvestmentStorage",
  "DiscountedCapitalInvestmentStorage",
  "DiscountedSalvageValueStorage",
  "TotalDiscountedStorageCost",
  "RateOfStorageCharge",
  "RateOfStorageDischarge",
  "NetChargeWithinYear",
  "NetChargeWithinDay",
];

// ---------------------------------------------------------------------------
//  Prefijos de tecnología (MAPA_SECTOR + familias de oferta)
// ---------------------------------------------------------------------------

const PREF_DEMANDA = [
  "DEMRES",
  "DEMIND",
  "DEMTRA",
  "DEMTER",
  "DEMCON",
  "DEMAGF",
  "DEMMIN",
  "DEMCOQ",
  "DEMDER",
  "DEMNGS",
  "DEMNSE",
];
const PREF_PWR = ["PWR", "GRD"];
const PREF_H2 = ["HDG", "H2"];
const PREF_UPSTREAM = ["UPS", "REF", "GAS", "LIQ", "CTR"];
const PREF_EXTRACCION = ["MIN", "EXT", "SOL"];
const PREF_COMERCIO = ["IMP", "EXP", "BAC", "BBG"];

export const CATEGORIES: Category[] = [
  {
    id: "todos",
    label: "Todos",
    icon: "🌐",
    filters: {},
  },
  {
    id: "demanda",
    label: "Demanda final",
    icon: "🏠",
    filters: { technology_prefixes: PREF_DEMANDA },
    sub: [
      {
        id: "dem_todos",
        label: "Todos los sectores",
        icon: "🔥",
        filters: { technology_prefixes: PREF_DEMANDA },
      },
      { id: "dem_res", label: "Residencial", icon: "🏘️", filters: { technology_prefixes: ["DEMRES"] } },
      { id: "dem_ind", label: "Industrial", icon: "🏗️", filters: { technology_prefixes: ["DEMIND"] } },
      { id: "dem_tra", label: "Transporte", icon: "🚗", filters: { technology_prefixes: ["DEMTRA"] } },
      { id: "dem_ter", label: "Terciario", icon: "🏢", filters: { technology_prefixes: ["DEMTER"] } },
      { id: "dem_con", label: "Construcción", icon: "🔨", filters: { technology_prefixes: ["DEMCON"] } },
      { id: "dem_agf", label: "Agroforestal", icon: "🌾", filters: { technology_prefixes: ["DEMAGF"] } },
      { id: "dem_min", label: "Minería", icon: "⛏️", filters: { technology_prefixes: ["DEMMIN"] } },
      { id: "dem_coq", label: "Coquerías", icon: "🧱", filters: { technology_prefixes: ["DEMCOQ"] } },
    ],
  },
  {
    id: "oferta",
    label: "Oferta & Transformación",
    icon: "⚡",
    filters: {
      technology_prefixes: [
        ...PREF_PWR,
        ...PREF_H2,
        ...PREF_UPSTREAM,
        ...PREF_EXTRACCION,
        ...PREF_COMERCIO,
      ],
    },
    sub: [
      {
        id: "ofr_todos",
        label: "Todos",
        icon: "🏭",
        filters: {
          technology_prefixes: [
            ...PREF_PWR,
            ...PREF_H2,
            ...PREF_UPSTREAM,
            ...PREF_EXTRACCION,
            ...PREF_COMERCIO,
          ],
        },
      },
      {
        id: "ofr_elec",
        label: "Electricidad",
        icon: "🔌",
        filters: { technology_prefixes: PREF_PWR, fuel_prefixes: ["ELC"] },
      },
      {
        id: "ofr_h2",
        label: "Hidrógeno",
        icon: "💧",
        filters: { technology_prefixes: PREF_H2, fuel_prefixes: ["HDG", "H2"] },
      },
      {
        id: "ofr_ups",
        label: "Upstream / Refinería",
        icon: "🛢️",
        filters: {
          technology_prefixes: PREF_UPSTREAM,
          fuel_prefixes: ["OIL", "GSL", "DSL", "JET", "FOL", "LPG", "NGS", "LIQ"],
        },
      },
      {
        id: "ofr_ext",
        label: "Extracción / Minería",
        icon: "⛏️",
        filters: {
          technology_prefixes: PREF_EXTRACCION,
          fuel_prefixes: ["COA", "WOO", "BAG", "BGS", "AFR", "URN"],
        },
      },
      {
        id: "ofr_com",
        label: "Comercio exterior",
        icon: "🚢",
        filters: { technology_prefixes: PREF_COMERCIO },
      },
    ],
  },
  {
    id: "emisiones",
    label: "Emisiones",
    icon: "🌿",
    filters: { variable_names: VAR_EMISIONES },
    sub: [
      { id: "emi_todas", label: "Todas", icon: "🌫️", filters: { variable_names: VAR_EMISIONES } },
      {
        id: "emi_gei",
        label: "GEI",
        icon: "🌡️",
        filters: {
          variable_names: VAR_EMISIONES,
          emission_names: ["EMIC02", "EMICO2", "EMICH4", "EMIN2O"],
        },
      },
      {
        id: "emi_cont",
        label: "Contaminantes",
        icon: "🏭",
        filters: {
          variable_names: VAR_EMISIONES,
          emission_names: [
            "EMIBC",
            "EMICO",
            "EMICOVDM",
            "EMINH3",
            "EMINOx",
            "EMIPM10",
            "EMIPM2_5",
            "EMISOx",
          ],
        },
      },
    ],
  },
  {
    id: "costos",
    label: "Costos",
    icon: "💰",
    filters: { variable_names: VAR_COSTOS },
    sub: [
      { id: "cos_todos", label: "Todos", icon: "💵", filters: { variable_names: VAR_COSTOS } },
      {
        id: "cos_inv",
        label: "Inversión",
        icon: "🏦",
        filters: {
          variable_names: [
            "CapitalInvestment",
            "DiscountedCapitalInvestment",
            "CapitalInvestmentStorage",
            "DiscountedCapitalInvestmentStorage",
          ],
        },
      },
      {
        id: "cos_op",
        label: "Operativos",
        icon: "⚙️",
        filters: {
          variable_names: [
            "OperatingCost",
            "DiscountedOperatingCost",
            "VariableOperatingCost",
            "AnnualVariableOperatingCost",
            "AnnualFixedOperatingCost",
          ],
        },
      },
      {
        id: "cos_salvage",
        label: "Salvage / Recovery",
        icon: "♻️",
        filters: {
          variable_names: [
            "SalvageValue",
            "DiscountedSalvageValue",
            "SalvageValueStorage",
            "DiscountedSalvageValueStorage",
            "RecoveryValue",
            "DiscountedRecoveryValue",
            "DisposalCost",
            "DiscountedDisposalCost",
          ],
        },
      },
      {
        id: "cos_desc",
        label: "Totales descontados",
        icon: "📉",
        filters: {
          variable_names: [
            "TotalDiscountedCost",
            "TotalDiscountedCostByTechnology",
            "TotalDiscountedStorageCost",
          ],
        },
      },
    ],
  },
  {
    id: "storage",
    label: "Storage",
    icon: "🔋",
    filters: { variable_names: VAR_STORAGE },
    sub: [
      { id: "sto_todos", label: "Todos", icon: "🔋", filters: { variable_names: VAR_STORAGE } },
      {
        id: "sto_niv",
        label: "Niveles",
        icon: "📊",
        filters: {
          variable_names: [
            "StorageLevelYearStart",
            "StorageLevelYearFinish",
            "StorageLevelSeasonStart",
            "StorageLevelDayTypeStart",
            "StorageLevelDayTypeFinish",
            "StorageLowerLimit",
            "StorageUpperLimit",
          ],
        },
      },
      {
        id: "sto_flujos",
        label: "Carga / Descarga",
        icon: "🔄",
        filters: {
          variable_names: [
            "RateOfStorageCharge",
            "RateOfStorageDischarge",
            "NetChargeWithinYear",
            "NetChargeWithinDay",
          ],
        },
      },
      {
        id: "sto_cap",
        label: "Capacidad",
        icon: "🏗️",
        filters: { variable_names: ["NewStorageCapacity", "AccumulatedNewStorageCapacity"] },
      },
      {
        id: "sto_cos",
        label: "Costos storage",
        icon: "💰",
        filters: {
          variable_names: [
            "CapitalInvestmentStorage",
            "DiscountedCapitalInvestmentStorage",
            "SalvageValueStorage",
            "DiscountedSalvageValueStorage",
            "TotalDiscountedStorageCost",
          ],
        },
      },
    ],
  },
];

const REGIONAL_PREFIXES = new Set(["AN", "CA", "IN", "NE", "OR", "SE", "SO"]);

function stripRegionalPrefix(code: string): string {
  if (code.length >= 4 && code[2] === "_") {
    const prefix = code.substring(0, 2);
    if (REGIONAL_PREFIXES.has(prefix)) {
      return code.substring(3);
    }
  }
  return code;
}

/**
 * Resuelve `technology_prefixes` contra la lista disponible de tecnologías
 * (facets). Devuelve sólo los nombres que empiezan por algún prefijo.
 * Para modelos regionales, ignora el prefijo geográfico (AN_, CA_, etc.)
 * al hacer la comparación.
 */
export function resolveTechnologyNames(
  prefixes: readonly string[] | undefined,
  available: readonly string[],
): string[] {
  if (!prefixes || prefixes.length === 0) return [];
  return available.filter((name) =>
    prefixes.some((p) => name.startsWith(p) || stripRegionalPrefix(name).startsWith(p)),
  );
}

/** Idéntico a resolveTechnologyNames pero para combustibles. */
export function resolveFuelNames(
  prefixes: readonly string[] | undefined,
  available: readonly string[],
): string[] {
  return resolveTechnologyNames(prefixes, available);
}

/** Compara dos arrays de strings sin orden. */
export function arraysEqualUnordered(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const s = new Set(a);
  for (const v of b) if (!s.has(v)) return false;
  return true;
}
