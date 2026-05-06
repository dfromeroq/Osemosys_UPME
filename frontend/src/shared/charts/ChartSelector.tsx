/**
 * ChartSelector — Selector jerárquico de gráficas (3 niveles)
 *
 * Nivel 1 → Módulo temático  (pills horizontales)
 * Nivel 2 → Subsector        (solo para "Demanda Final")
 * Nivel 3 → Gráfica          (lista de botones)
 *
 * Controles adicionales:
 *   - Variable de capacidad (TotalCapacityAnnual / NewCapacity / AccumulatedNewCapacity)
 *   - Agrupación            (TECNOLOGIA / COMBUSTIBLE / FUEL / GROUP)
 *   - Unidades
 *   - Sub-filtro
 *   - Localización
 */

import React, { useMemo } from 'react';

// ─── Tipos ───────────────────────────────────────────────────────────────────

export interface ChartSelection {
  tipo: string;
  un: string;
  sub_filtro?: string;
  loc?: string;
  variable?: string;
  viewMode?: 'column' | 'line' | 'area' | 'pareto' | 'porcentaje' | 'table';
  /** Agrupación enviada al backend: 'TECNOLOGIA' | 'COMBUSTIBLE' | 'FUEL' | 'GROUP' */
  agrupar_por?: string;
  /** Solo `viewMode === 'table'`: año-paso (5 = cada 5 años). null/undefined = todos. */
  tablePeriodYears?: number | null;
  /** Solo `viewMode === 'table'`: muestra valores acumulados. */
  tableCumulative?: boolean;
  /** Override del orden de series (lista de nombres). null = orden natural. */
  customSeriesOrder?: string[] | null;
  /** Override del valor mínimo del eje Y. null = auto. */
  yAxisMin?: number | null;
  /** Override del valor máximo del eje Y. null = auto. */
  yAxisMax?: number | null;
  /** Para Sector Eléctrico: filtra entre 'liquidos', 'todos', 'termica' */
  tipo_electrico?: 'liquidos' | 'todos' | 'termica';
}

interface Props {
  value: ChartSelection;
  onChange: (next: ChartSelection) => void;
  /**
   * Si true, oculta la sección "Agrupar por". Útil cuando la comparación es
   * `line-total` (cada serie es un escenario y muestra totales, no hay
   * agrupación por tecnología/combustible/sector).
   */
  hideGroupBy?: boolean;
  /**
   * Orientación actual de las barras apiladas. Se controla desde el mismo
   * selector de "Tipo de vista" (botón "Barras horizontales").
   */
  barOrientation?: 'vertical' | 'horizontal';
  onChangeBarOrientation?: (next: 'vertical' | 'horizontal') => void;
}

// ─── Constantes ──────────────────────────────────────────────────────────────

const CAPACITY_VARIABLES: { value: string; label: string }[] = [
  { value: 'TotalCapacityAnnual',    label: 'Capacidad Total Anual' },
  { value: 'NewCapacity',            label: 'Capacidad Nueva' },
  { value: 'AccumulatedNewCapacity', label: 'Capacidad Acumulada' },
];

const UNITS = ['PJ', 'GW', 'MW', 'TWh', 'Gpc'] as const;

/** Gráficas de emisión GEI con unidad intercambiable (MtCO₂eq ↔ ktCO₂eq). */
const GEI_CHART_IDS = new Set([
  'emisiones_total',
  'emisiones_sectorial',
  'emisiones_gei',
]);

/** Gráficas de contaminantes criterio (unidad fija: kt). */
const CONTAMINANTES_CHART_IDS = new Set(['emisiones_contaminantes']);

/** Gráficas con unidad fija % (factor de planta). */
const PORCENTAJE_CHART_IDS = new Set(['factor_planta']);

const EMISSION_CHART_IDS = new Set([...GEI_CHART_IDS, ...CONTAMINANTES_CHART_IDS]);

const EMISSION_UNITS: { value: string; label: string }[] = [
  { value: 'MtCO2eq', label: 'MtCO₂eq' },
  { value: 'ktCO2eq', label: 'ktCO₂eq' },
];

const EMISSION_UNIT_VALUES = new Set(EMISSION_UNITS.map((eu) => eu.value));

/** Código → nombre legible de combustible (para dropdowns de sub-filtro). */
const FUEL_LABELS: Record<string, string> = {
  CARRETERA: 'Carretera (BUS/MOT/TCK/STT/LDV/FWD/TAX/MIC)',
  NGS: 'Gas Natural',
  DSL: 'Diésel',
  ELC: 'Electricidad',
  GSL: 'Gasolina',
  COA: 'Carbón',
  LPG: 'GLP',
  WOO: 'Leña',
  BGS: 'Biogás',
  BAG: 'Bagazo',
  HDG: 'Hidrógeno',
  FOL: 'Fuel Oil',
  BDL: 'Biodiésel',
  JET: 'Jet A1',
  WAS: 'RSU',
  OIL: 'Petróleo',
  AFR: 'Residuos Agrícolas/Forestales',
  SAF: 'SAF',
  // ── Códigos de uso (subfiltros de demanda) ────────────────────────────
  // Mantenemos el código tal cual en la UI; el comentario documenta el
  // significado para que el desarrollador (y futuros lectores) sepan qué
  // representa cada uno sin necesidad de traducir en pantalla.
  ACL: 'ACL',  // Aclimatación
  AIR: 'AIR',  // Aire acondicionado
  BOI: 'BOI',  // Caldera (Boiler)
  CKN: 'CKN',  // Cocción / Estufa
  DAT: 'DAT',  // Data Center
  FAN: 'FAN',  // Ventilador
  FUR: 'FUR',  // Horno (Furnace)
  ILU: 'ILU',  // Iluminación
  MPW: 'MPW',  // Motores (Motor Power)
  OTH: 'OTH',  // Otros
  REF: 'REF',  // Refrigeración
  TV:  'TV',   // Televisor
  WHT: 'WHT',  // Calentador de agua (Water Heating)
  WSH: 'WSH',  // Lavadora (Washing)
  'con_crudo': 'Con crudo',
  'sin_crudo': 'Sin crudo',
};
/**
 * Opciones de agrupación disponibles para el backend.
 *
 * TECNOLOGIA → cada barra/serie es una tecnología individual (default actual).
 * COMBUSTIBLE → agrupa por tipo de combustible/energético usando asignar_grupo().
 * FUEL        → agrupa directamente por el campo FUEL del resultado.
 * GROUP       → combina TECHNOLOGY + FUEL y asigna grupo (combustible "compuesto").
 *
 * Los configs de capacidad (isCapacity) y porcentaje (prd_electricidad)
 * no muestran este selector porque su agrupación está fija en el backend.
 */
const AGRUPACION_OPTIONS: { value: string; label: string; description: string }[] = [
  {
    value: 'TECNOLOGIA',
    label: 'Por Tecnología',
    description: 'Una serie por cada tecnología individual',
  },
  {
    value: 'FUEL',
    label: 'Por combustible',
    description: 'Agrupa directamente por el campo FUEL del resultado',
  },
  {
    value: 'SECTOR',
    label: 'Por Sector',
    description: 'Agrupa por sectores de demanda',
  },
];

// IDs de charts que NO deben mostrar el selector de agrupación
// (su agrupación está fija en el backend o no tiene sentido cambiarlo)
const CHARTS_SIN_AGRUPACION = new Set([
  'factor_planta',           // es_factor_planta → fijo en backend
  'emisiones_total',         // agrupa por YEAR → fijo
  'emisiones_sectorial',     // agrupa por SECTOR → fijo
  'emisiones_gei',           // agrupa por SECTOR (incluye PWR) → fijo
  'emisiones_contaminantes', // agrupa por EMISION → fijo
  'h2_produccion_verde',     // H2_PRODUCCION fijo en backend
]);

// ─── Estructura del menú ─────────────────────────────────────────────────────

interface ChartItem {
  id: string;
  label: string;
  isCapacity?: boolean;
  hasSub?: boolean;
  hasLoc?: boolean;
  subFiltros?: string[];
  /** Etiqueta del dropdown de sub-filtro (ej. 'Combustible', 'Uso', 'Modo'). Default: 'Sub-filtro'. */
  subFiltroLabel?: string;
  /** Agrupaciones válidas para esta gráfica. Si no se define, se muestran todas. */
  allowedGroupings?: string[];
  /** Agrupación por defecto al seleccionar esta gráfica. */
  defaultGrouping?: string;
  /** True si esta gráfica soporta vista Pareto (barras por tecnología + % acumulado). */
  soportaPareto?: boolean;
  /** True si esta gráfica soporta vista Porcentaje (normaliza cada año a 100%). */
  soportaPorcentaje?: boolean;
  /**
   * True si esta gráfica soporta vista Tabla (matriz con categorías × años,
   * con períodos opcionales y acumulado). Default `true` — la mayoría de los
   * charts con `categories` tienen sentido como tabla.
   */
  soportaTabla?: boolean;
}

interface Subsector {
  id: string;
  label: string;
  charts: ChartItem[];
}

interface Module {
  id: string;
  emoji: string;
  label: string;
  subsectors?: Subsector[];
  charts?: ChartItem[];
}

const MENU: Module[] = [
  {
    id: 'electrico',
    emoji: '⚡',
    label: 'Sector Eléctrico',
    charts: [
      // Líquidos (3 gráficas)
      { id: 'elec_produccion_liquidos', label: 'Generación Líquidos - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
      { id: 'elec_cap_liquidos', label: 'Matriz Líquidos (Capacidad) - TotalCapacityAnnual', isCapacity: true },
      { id: 'elec_fp_liquidos', label: 'Factor de Planta - Líquidos (%)' },
      // Todos (3 gráficas originales)
      { id: 'elec_produccion', label: 'Producción de Electricidad - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
      { id: 'cap_electricidad', label: 'Matriz Eléctrica (Capacidad) - TotalCapacityAnnual', isCapacity: true },
      { id: 'factor_planta', label: 'Factor de Planta (%)' },
      // Gen. Térmica (3 gráficas)
      { id: 'elec_produccion_termica', label: 'Generación Térmica - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
      { id: 'elec_cap_termica', label: 'Matriz Térmica (Capacidad) - TotalCapacityAnnual', isCapacity: true },
      { id: 'elec_fp_termica', label: 'Factor de Planta - Térmica (%)' },
    ],
  },
  {
    id: 'demanda',
    emoji: '🏠',
    label: 'Demanda Final — Sectores',
    subsectors: [
      { id: 'consum_combustible', label: '🔥 Todos los Sectores', charts: [
          { id: 'dem_consumo_combustible', label: 'Consumo Por Sector', hasSub: true, subFiltroLabel: 'Combustible', subFiltros: ['NGS','DSL','ELC','GSL','COA','LPG','WOO','BGS','BAG','HDG','FOL','BDL','JET','WAS','OIL','AFR','SAF'], allowedGroupings: ['SECTOR', 'FUEL'], defaultGrouping: 'SECTOR' },
        ]},
      {
        id: 'residencial', label: '🏘️ Residencial',
        charts: [
          { id: 'res_total', label: 'Sector Residencial - Consumo Total - UseByTechnology', hasSub: true, subFiltroLabel: 'Uso', hasLoc: true, subFiltros: ['CKN','WHT','AIR','REF','ILU','TV','FAN','WSH','OTH'], allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'res_uso',   label: 'Sector Residencial - ProductionByTechnology',           hasSub: true, subFiltroLabel: 'Uso', hasLoc: true, subFiltros: ['CKN','WHT','AIR','REF','ILU','TV','FAN','WSH','OTH'], allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
        ],
      },
      {
        id: 'industrial', label: '🏗️ Industrial',
        charts: [
          { id: 'ind_total', label: 'Sector Industrial - Consumo Total - UseByTechnology', hasSub: true, subFiltroLabel: 'Uso', subFiltros: ['BOI','FUR','MPW','AIR','REF','ILU','OTH'], allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'ind_uso',   label: 'Sector Industrial - ProductionByTechnology',           hasSub: true, subFiltroLabel: 'Uso', subFiltros: ['BOI','FUR','MPW','AIR','REF','ILU','OTH'], allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
        ],
      },
      {
        id: 'transporte', label: '🚗 Transporte',
        charts: [
          { id: 'tra_total', label: 'Sector Transporte - Consumo Total - UseByTechnology', hasSub: true, subFiltroLabel: 'Modo', subFiltros: ['CARRETERA','AVI','BOT','SHP','LDV','FWD','BUS','TCK_C2P','TCK_CSG','MOT','MIC','TAX','STT','MET'], allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'tra_uso',   label: 'Sector Transporte - ProductionByTechnology',           hasSub: true, subFiltroLabel: 'Modo', subFiltros: ['CARRETERA','AVI','BOT','SHP','LDV','FWD','BUS','TCK_C2P','TCK_CSG','MOT','MIC','TAX','STT','MET'], allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
        ],
      },
      {
        id: 'terciario', label: '🏢 Terciario',
        charts: [
          { id: 'ter_total', label: 'Sector Terciario - Consumo Total - UseByTechnology', hasSub: true, subFiltroLabel: 'Uso', subFiltros: ['ACL','AIR','CKN','DAT','FAN','ILU','MPW','REF','OTH'], allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'ter_uso',   label: 'Sector Terciario - ProductionByTechnology',           hasSub: true, subFiltroLabel: 'Uso', subFiltros: ['ACL','AIR','CKN','DAT','FAN','ILU','MPW','REF','OTH'], allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
        ],
      },
      { id: 'construccion', label: '🔨 Construcción',      charts: [{ id: 'con_total',   label: 'Sector Construcción - Consumo Total - UseByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true }] },
      { id: 'agroforestal', label: '🌾 Agroforestal',      charts: [{ id: 'agf_total',   label: 'Sector Agroforestal - Consumo Total - UseByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true }] },
      { id: 'mineria_dem',  label: '⛏️ Minería (demanda)', charts: [{ id: 'min_total',   label: 'Sector Minería - Consumo Total - UseByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true }] },
      { id: 'coquerias',    label: '🧱 Coquerías',          charts: [{ id: 'coq_total',   label: 'Sector Coquerías - Consumo Total - UseByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true }] },

      { id: 'otros_dem',    label: '📦 Otros Sectores',     charts: [{ id: 'otros_total', label: 'Otros Sectores - Consumo Total - UseByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true }] },
    ],
  },
  {
    id: 'capacidades',
    emoji: '🏭',
    label: 'Capacidades Instaladas',
    charts: [
      { id: 'cap_industrial', label: 'Sector Industrial (Capacidad) - TotalCapacityAnnual',  isCapacity: true },
      { id: 'cap_transporte', label: 'Sector Transporte (Capacidad) - TotalCapacityAnnual',  isCapacity: true },
      { id: 'cap_terciario',  label: 'Sector Terciario (Capacidad) - TotalCapacityAnnual',   isCapacity: true },
      { id: 'cap_otros',      label: 'Otros Sectores (Capacidad) - TotalCapacityAnnual',     isCapacity: true },
      { id: 'ref_capacidad',  label: 'Capacidad de Refinación por Derivado',                 isCapacity: false, allowedGroupings: ['TECNOLOGIA', 'FUEL'], },
    ],
  },
  {
    id: 'upstream',
    emoji: '🛢️',
    label: 'Upstream & Refinación',
    subsectors: [
      {
        id: 'otros',
        label: '🔧 Otros',
        charts: [
          { id: 'gas_consumo',    label: 'Gas Natural - UseByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'gas_produccion', label: 'Gas Natural - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'ups_refinacion', label: 'Upstream Refinación - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'saf_produccion', label: 'SAF - Producción - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
        ],
      },
      {
        id: 'liquidos',
        label: '🛢️ Líquidos',
        charts: [
          { id: 'liquidos_prod_import', label: 'Líquidos - Producción + Importación', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'imp_liquidos', label: 'Líquidos - Importación - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'exp_liquidos', label: 'Líquidos - Exportación - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'dem_consumo_liquidos', label: 'Consumo de Líquidos - Sectores de Demanda', allowedGroupings: ['FUEL'], defaultGrouping: 'FUEL', soportaPareto: true },
          // { id: 'dem_consumo_liquidos_exp_use', label: 'Consumo de Líquidos — Demanda y Exportaciones', allowedGroupings: ['FUEL'], defaultGrouping: 'FUEL', soportaPareto: true },
          { id: 'dem_consumo_liquidos_total', label: 'Consumo de Líquidos - Sectores de Demanda + Sector Eléctrico', allowedGroupings: ['FUEL'], defaultGrouping: 'FUEL', soportaPareto: true },
        ],
      },
      {
        id: 'refinerias',
        label: '🏭 Refinerías',
        charts: [
          { id: 'ref_total',      label: 'Refinerías - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'ref_import',     label: 'Refinerías - Importaciones - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'ref_consumo',    label: 'Refinerías — Consumo Total por Tecnología', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'ref_cartagena',   label: 'Refinería de Cartagena - UseByTechnology', allowedGroupings: ['FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'ref_barrancabermeja', label: 'Refinería de Barrancabermeja - UseByTechnology', allowedGroupings: ['FUEL'], soportaPareto: true, soportaPorcentaje: true },
          { id: 'ref_ambas', label: 'Refinerías (Cartagena + Barrancabermeja) - UseByTechnology', 
            hasSub: true, subFiltroLabel: 'Crudo', 
            subFiltros: ['con_crudo', 'sin_crudo'],
            allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
        ],
      },
    ],
  },
  {
    id: 'mineria',
    emoji: '⛏️',
    label: 'Minería & Extracción',
    charts: [
      { id: 'min_hidrocarburos',  label: 'Minería Hidrocarburos - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
      { id: 'min_carbon',         label: 'Minería Carbón - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
      { id: 'extraccion_min',     label: 'Minería - Extracción - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
      { id: 'solidos_extraccion', label: 'Sólidos - Extracción - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
      { id: 'solidos_import',     label: 'Sólidos - Importación - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
      { id: 'solidos_flujos',     label: 'Sólidos - Importación/Exportación - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
    ],
  },
    {
      id: 'hidrogeno',
      emoji: '💧',
      label: 'Hidrógeno',
      charts: [
        { id: 'cap_h2',     label: 'Hidrógeno - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true , soportaPorcentaje: true },
        { id: 'h2_consumo', label: 'Hidrógeno - Consumo - UseByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true },
        { id: 'cap_electrolisis_verde', label: 'Capacidad Total de Electrólisis Verde', isCapacity: true },
        { id: 'h2_produccion_verde', label: 'Hidrógeno Producción (Verde/Azul/Gris)', soportaPareto: true, soportaPorcentaje: true },
      ],
    },
  {
    id: 'comercio',
    emoji: '🚢',
    label: 'Comercio Exterior',
    charts: [{ id: 'exp_liquidos_gas', label: 'Exportaciones — Líquidos y Gas', allowedGroupings: ['TECNOLOGIA', 'FUEL'], soportaPareto: true, soportaPorcentaje: true }],
  },
  {
    id: 'emisiones',
    emoji: '🌿',
    label: 'Emisiones',
    charts: [
      { id: 'emisiones_total',     label: 'Emisiones - Total Anual - AnnualEmissions' },
      { id: 'emisiones_sectorial', label: 'Emisiones - Por Sector - AnnualTechnologyEmission', soportaPorcentaje: true },
      { id: 'emisiones_gei',       label: 'Emisiones GEI por Sector (CO₂, CH₄, N₂O)', soportaPorcentaje: true },
      { id: 'emisiones_contaminantes', label: 'Emisiones Contaminantes Criterio (BC, CO, COV, NH₃, NOₓ, PM10, PM2.5, SOₓ)', soportaPorcentaje: true },
    ],
  },
  {
    id: 'bioenergía',
    emoji: '♻️',
    label: 'bioenergía',
    charts: [
      { id: 'oferta_bioenergia', label: 'Oferta Bioenergía - ProductionByTechnology', allowedGroupings: ['TECNOLOGIA', 'FUEL'] },
    ],
  },
  ];

const FIRST_MODULE = MENU[0] as Module;

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Etiqueta legible de una gráfica (para mostrar en UI fuera del selector). */
export function getChartLabel(tipo: string): string | undefined {
  return findChartItem(tipo)?.label;
}

export type ChartLocation = { moduleId: string; subsectorId?: string };

/** Devuelve módulo (y subsector si aplica, sólo Demanda Final) para un chart `tipo`. */
export function getChartLocation(tipo: string): ChartLocation {
  return findLocation(tipo);
}

/** Subsectores definidos para un módulo (vacío si no aplica). */
export function getChartSubsectors(
  moduleId: string,
): { id: string; label: string }[] {
  const mod = MENU.find((m) => m.id === moduleId);
  if (!mod || !mod.subsectors) return [];
  return mod.subsectors.map((s) => ({ id: s.id, label: s.label }));
}

export type ChartModuleInfo = { id: string; label: string; emoji: string };

/** Módulos (primer nivel) del menú — para agrupar plantillas en UI externas. */
export function getChartModules(): ChartModuleInfo[] {
  return MENU.map((m) => ({ id: m.id, label: m.label, emoji: m.emoji }));
}

/** Módulo al que pertenece una gráfica (primer nivel de agrupación). */
export function getChartModule(tipo: string): ChartModuleInfo | undefined {
  const { moduleId } = findLocation(tipo);
  const mod = MENU.find((m) => m.id === moduleId);
  return mod ? { id: mod.id, label: mod.label, emoji: mod.emoji } : undefined;
}

function findChartItem(tipo: string): ChartItem | undefined {
  for (const mod of MENU) {
    const inFlat = mod.charts?.find((c) => c.id === tipo);
    if (inFlat) return inFlat;
    if (mod.subsectors) {
      for (const sub of mod.subsectors) {
        const inSub = sub.charts.find((c) => c.id === tipo);
        if (inSub) return inSub;
      }
    }
  }
  return undefined;
}

function findLocation(tipo: string): { moduleId: string; subsectorId?: string } {
  for (const mod of MENU) {
    if (mod.charts?.some((c) => c.id === tipo)) return { moduleId: mod.id };
    if (mod.subsectors) {
      for (const sub of mod.subsectors) {
        if (sub.charts.some((c) => c.id === tipo)) {
          return { moduleId: mod.id, subsectorId: sub.id };
        }
      }
    }
  }
  return { moduleId: FIRST_MODULE.id };
}

function chartTipoBelongsToModule(tipo: string, moduleId: string): boolean {
  const mod = MENU.find((m) => m.id === moduleId);
  if (!mod) return false;
  if (mod.charts?.some((c) => c.id === tipo)) return true;
  if (mod.subsectors) {
    return mod.subsectors.some((sub) => sub.charts.some((c) => c.id === tipo));
  }
  return false;
}

/** Determina si la gráfica activa debe mostrar el selector de agrupación */
function showsAgrupacion(item: ChartItem | undefined): boolean {
  if (!item) return false;
  if (item.isCapacity) return false;                    // fijo en backend
  if (CHARTS_SIN_AGRUPACION.has(item.id)) return false; // porcentaje / emisiones
  return true;
}

// ─── Componente ──────────────────────────────────────────────────────────────

export function ChartSelector({
  value,
  onChange,
  hideGroupBy = false,
  barOrientation,
  onChangeBarOrientation,
}: Props) {
  const loc = findLocation(value.tipo);
  const activeModule = loc.moduleId;
  const activeSubsector = loc.subsectorId ?? '';

  const currentModule: Module =
    MENU.find((m) => m.id === activeModule) ?? FIRST_MODULE;

  const currentItem = findChartItem(value.tipo);

  const subsectors: Subsector[] = currentModule.subsectors ?? [];
  const flatCharts: ChartItem[] = currentModule.charts ?? [];

  const subsectorCharts: ChartItem[] = useMemo(() => {
    const mod = MENU.find((m) => m.id === activeModule) ?? FIRST_MODULE;
    const subs = mod.subsectors;
    if (!subs || subs.length === 0) return [];
    const sub = subs.find((s) => s.id === activeSubsector) ?? subs[0];
    if (!sub) return [];
    return sub.charts ?? [];
  }, [activeModule, activeSubsector]);

  const chartsToShow = useMemo(() => {
    // Para Sector Eléctrico: filtrar por tipo_electrico
    if (currentModule.id === 'electrico') {
      const tipoMap: Record<string, string[]> = {
        'liquidos': ['elec_produccion_liquidos', 'elec_cap_liquidos', 'elec_fp_liquidos'],
        'todos': ['elec_produccion', 'cap_electricidad', 'factor_planta'],
        'termica': ['elec_produccion_termica', 'elec_cap_termica', 'elec_fp_termica'],
      };
      const tipo = value.tipo_electrico || 'todos';
      const ids = tipoMap[tipo];
      if (!ids) return [];
      return flatCharts.filter((chart): boolean => {
        const id = chart.id;
        return typeof id === 'string' && ids.includes(id);
      });
    }
    // Comportamiento normal para outros módulos
    return subsectors.length > 0 ? subsectorCharts : flatCharts;
  }, [currentModule, subsectors, subsectorCharts, flatCharts, value.tipo_electrico]);

  // Valores derivados seguros
  const activeVariable: string  = value.variable ?? '';
  const activeAgrupacion: string = value.agrupar_por ?? 'TECNOLOGIA';
  const activeCapacityLabel: string =
    CAPACITY_VARIABLES.find((cv) => cv.value === activeVariable)?.label ?? activeVariable;

  const canChangeAgrupacion = showsAgrupacion(currentItem);

  // ── Helpers internos ──────────────────────────────────────────────────────

  function selectChart(item: ChartItem): void {
    const { agrupar_por: prevAgrupacion, ...rest } = value;

    // Determinar la agrupación correcta para la nueva gráfica
    let newGrouping: string | undefined;
    if (showsAgrupacion(item)) {
      const prev = prevAgrupacion ?? 'TECNOLOGIA';
      if (item.allowedGroupings) {
        newGrouping = item.allowedGroupings.includes(prev)
          ? prev
          : (item.defaultGrouping ?? item.allowedGroupings[0] ?? 'TECNOLOGIA');
      } else {
        newGrouping = prev;
      }
    }

    // Si el viewMode actual es 'porcentaje' y la nueva gráfica no lo soporta, resetear a 'column'
    let newViewMode = rest.viewMode;
    if (newViewMode === 'porcentaje' && !item.soportaPorcentaje) {
      newViewMode = 'column';
    }
    // Si el viewMode actual es 'pareto' y la nueva gráfica no lo soporta, resetear a 'column'
    if (newViewMode === 'pareto' && !item.soportaPareto) {
      newViewMode = 'column';
    }
    // Si el viewMode actual es 'table' y la nueva gráfica lo desactiva
    // explícitamente (soportaTabla=false), resetear a 'column'.
    if (newViewMode === 'table' && item.soportaTabla === false) {
      newViewMode = 'column';
    }

    let newUn = rest.un;
    if (GEI_CHART_IDS.has(item.id) && !EMISSION_UNIT_VALUES.has(rest.un)) {
      newUn = 'MtCO2eq';
    } else if (CONTAMINANTES_CHART_IDS.has(item.id)) {
      newUn = 'kt';
    } else if (PORCENTAJE_CHART_IDS.has(item.id)) {
      newUn = '%';
    } else if (
      !EMISSION_CHART_IDS.has(item.id) &&
      !PORCENTAJE_CHART_IDS.has(item.id) &&
      (EMISSION_UNIT_VALUES.has(rest.un) || rest.un === 'ktCO2eq' || rest.un === '%')
    ) {
      newUn = 'PJ';
    }

    onChange({
      ...rest,
      tipo:       item.id,
      un:         newUn,
      variable:   item.isCapacity ? 'TotalCapacityAnnual' : '',
      sub_filtro: item.id === 'ref_ambas' ? 'con_crudo' : '',
      loc:        '',
      ...(newViewMode != null ? { viewMode: newViewMode } : {}),
      ...(newGrouping != null ? { agrupar_por: newGrouping } : {}),
    });
  }

  function handleModuleChange(moduleId: string): void {
    const mod = MENU.find((m) => m.id === moduleId);
    if (!mod) return;
    if (chartTipoBelongsToModule(value.tipo, moduleId)) return;

    if (mod.subsectors && mod.subsectors.length > 0) {
      const firstSub: Subsector | undefined = mod.subsectors[0];
      if (!firstSub) return;
      const firstChart: ChartItem | undefined = firstSub.charts[0];
      if (firstChart) selectChart(firstChart);
    } else if (mod.charts && mod.charts.length > 0) {
      const firstChart: ChartItem | undefined = mod.charts[0];
      if (firstChart) selectChart(firstChart);
    }
  }

  function handleSubsectorChange(subsectorId: string): void {
    const sub = currentModule.subsectors?.find((s) => s.id === subsectorId);
    if (!sub) return;
    if (sub.charts.some((c) => c.id === value.tipo)) {
      return;
    }
    const firstChart: ChartItem | undefined = sub.charts[0];
    if (firstChart) selectChart(firstChart);
  }

  function handleAgrupacionChange(agrupacion: string): void {
    onChange({ ...value, agrupar_por: agrupacion });
  }

  // ── Resumen para la barra de selección activa ─────────────────────────────

  const agrupacionLabel =
    AGRUPACION_OPTIONS.find((a) => a.value === activeAgrupacion)?.label ?? activeAgrupacion;


  const isEmissionChart = EMISSION_CHART_IDS.has(value.tipo);
  const isGeiChart = GEI_CHART_IDS.has(value.tipo);
  const isContaminantesChart = CONTAMINANTES_CHART_IDS.has(value.tipo);
  const isPorcentajeChart = PORCENTAJE_CHART_IDS.has(value.tipo);
  const displayUnit = isContaminantesChart
    ? 'kt'
    : isPorcentajeChart
    ? '%'
    : isGeiChart
    ? (EMISSION_UNITS.find((eu) => eu.value === value.un)?.label ?? 'MtCO₂eq')
    : value.un;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'grid', gap: 16 }}>

      {/* ── NIVEL 1: Pills de módulo ── */}
      <div>
        <p style={labelStyle}>Módulo</p>
        <div style={pillsContainerStyle}>
          {MENU.map((mod) => {
            const isActive = mod.id === activeModule;
            return (
              <button
                key={mod.id}
                type="button"
                onClick={() => handleModuleChange(mod.id)}
                style={{ ...pillStyle, ...(isActive ? pillActiveStyle : pillInactiveStyle) }}
              >
                <span style={{ fontSize: 14 }}>{mod.emoji}</span>
                <span style={{ fontSize: 12, fontWeight: isActive ? 600 : 400, lineHeight: 1.3 }}>
                  {mod.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── NIVEL 2: Subsector (solo Demanda Final) ── */}
      {subsectors.length > 0 && activeModule !== 'electrico' && (
        <div>
          <p style={labelStyle}>Sector</p>
          <div style={pillsContainerStyle}>
            {subsectors.map((sub) => {
              const defaultId: string = subsectors[0]?.id ?? '';
              const isActive = sub.id === (activeSubsector || defaultId);
              return (
                <button
                  key={sub.id}
                  type="button"
                  onClick={() => handleSubsectorChange(sub.id)}
                  style={{ ...subsectorBtnStyle, ...(isActive ? subsectorActiveStyle : subsectorInactiveStyle) }}
                >
                  {sub.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── NIVEL 3: Lista de gráficas ── */}
      {chartsToShow.length > 0 && (
        <div>
          <p style={labelStyle}>Gráfica</p>
          <div style={chartListStyle}>
            {chartsToShow.map((item) => {
              const isActive = item.id === value.tipo;
              const badge = item.isCapacity
                ? 'CAP'
                : item.label.includes('UseByTechnology') ? 'USE' : 'PRD';
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => selectChart(item)}
                  style={{ ...chartBtnStyle, ...(isActive ? chartBtnActiveStyle : chartBtnInactiveStyle) }}
                >
                  <span style={{
                    ...chartBadgeStyle,
                    background: isActive ? 'rgba(59,130,246,0.25)' : 'rgba(255,255,255,0.06)',
                    color:      isActive ? '#93c5fd'              : '#64748b',
                  }}>
                    {badge}
                  </span>
                  <span style={{ flex: 1, textAlign: 'left', fontSize: 13 }}>{item.label}</span>
                  {isActive && <span style={checkmarkStyle}>✓</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Variable de capacidad (solo caps) ── */}
      {currentItem?.isCapacity === true && (
        <div>
          <p style={labelStyle}>Variable de capacidad</p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {CAPACITY_VARIABLES.map((cv) => {
              const isActive = (activeVariable || 'TotalCapacityAnnual') === cv.value;
              return (
                <button
                  key={cv.value}
                  type="button"
                  onClick={() => onChange({ ...value, variable: cv.value })}
                  style={{ ...varBtnStyle, ...(isActive ? varBtnActiveStyle : varBtnInactiveStyle) }}
                >
                  {cv.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Agrupación (no caps, no porcentaje, no emisiones) ── */}
      {canChangeAgrupacion && !hideGroupBy && (() => {
        const allowedOptions = currentItem?.allowedGroupings
          ? AGRUPACION_OPTIONS.filter(o => currentItem.allowedGroupings!.includes(o.value))
          : AGRUPACION_OPTIONS;
        return (
          <div>
            <p style={labelStyle}>Agrupar por</p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {allowedOptions.map((opt) => {
                const isActive = activeAgrupacion === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    title={opt.description}
                    onClick={() => handleAgrupacionChange(opt.value)}
                    style={{ ...agrupBtnStyle, ...(isActive ? agrupBtnActiveStyle : agrupBtnInactiveStyle) }}
                  >
                    <span style={{ fontSize: 13 }}>
                      {opt.value === 'TECNOLOGIA' ? '⚙️'
                        : opt.value === 'COMBUSTIBLE' ? '🔥'
                        : opt.value === 'FUEL' ? '⛽'
                        : opt.value === 'SECTOR' ? '🏢'
                        : '🔗'}
                    </span>
                    <span>{opt.label}</span>
                  </button>
                );
              })}
            </div>
            <p style={agrupDescStyle}>
              {AGRUPACION_OPTIONS.find((o) => o.value === activeAgrupacion)?.description ?? ''}
            </p>
          </div>
        );
      })()}

      {/* ── Fila inferior: Unidades + Tipo de vista + Sub-filtro + Localización ── */}
      <div style={bottomRowStyle}>
      <div style={{ display: 'grid', gap: 6 }}>
        <p style={labelStyle}>Unidades</p>
        {(isContaminantesChart || isPorcentajeChart) ? (
          <div style={{
            padding: '4px 12px',
            borderRadius: 6,
            border: '1px solid rgba(251,191,36,0.4)',
            background: 'rgba(251,191,36,0.08)',
            color: '#fcd34d',
            fontSize: 12,
            fontWeight: 600,
            fontFamily: 'monospace',
            display: 'inline-block',
          }}>
            {isContaminantesChart ? 'kt' : '%'}
          </div>
        ) : isGeiChart ? (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {EMISSION_UNITS.map((eu) => (
              <button
                key={eu.value}
                type="button"
                onClick={() => onChange({ ...value, un: eu.value })}
                style={{ ...unitBtnStyle, ...(value.un === eu.value ? unitBtnActiveStyle : unitBtnInactiveStyle) }}
              >
                {eu.label}
              </button>
            ))}
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {UNITS.map((u) => (
              <button
                key={u}
                type="button"
                onClick={() => onChange({ ...value, un: u })}
                style={{ ...unitBtnStyle, ...(value.un === u ? unitBtnActiveStyle : unitBtnInactiveStyle) }}
              >
                {u}
              </button>
            ))}
          </div>
        )}
      </div>

        <div style={{ display: 'grid', gap: 6 }}>
          <p style={labelStyle}>Tipo de vista</p>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {(() => {
              const currentVm = value.viewMode ?? 'column';
              const isColumn = currentVm === 'column';
              const currentOrientation = barOrientation ?? 'vertical';
              const isVerticalBars = isColumn && currentOrientation === 'vertical';
              const isHorizontalBars = isColumn && currentOrientation === 'horizontal';
              const canPickOrientation = typeof onChangeBarOrientation === 'function';
              return (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      onChange({ ...value, viewMode: 'column' });
                      onChangeBarOrientation?.('vertical');
                    }}
                    style={{ ...viewBtnStyle, ...(isVerticalBars ? viewBtnActiveStyle : viewBtnInactiveStyle) }}
                  >
                    ▦ Columnas
                  </button>
                  {canPickOrientation && (
                    <button
                      type="button"
                      onClick={() => {
                        onChange({ ...value, viewMode: 'column' });
                        onChangeBarOrientation?.('horizontal');
                      }}
                      style={{ ...viewBtnStyle, ...(isHorizontalBars ? viewBtnActiveStyle : viewBtnInactiveStyle) }}
                    >
                      ☰ Barras horizontales
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => onChange({ ...value, viewMode: 'line' })}
                    style={{ ...viewBtnStyle, ...(currentVm === 'line' ? viewBtnActiveStyle : viewBtnInactiveStyle) }}
                  >
                    ∿ Línea
                  </button>
                  {currentItem?.soportaPorcentaje === true && (
                    <button
                      type="button"
                      onClick={() => onChange({ ...value, viewMode: 'porcentaje' })}
                      style={{ ...viewBtnStyle, ...(currentVm === 'porcentaje' ? viewBtnActiveStyle : viewBtnInactiveStyle) }}
                    >
                      % Porcentajes
                    </button>
                  )}
                  {currentItem?.soportaPareto === true && (
                    <button
                      type="button"
                      onClick={() => onChange({ ...value, viewMode: 'pareto' })}
                      style={{ ...viewBtnStyle, ...(currentVm === 'pareto' ? viewBtnActiveStyle : viewBtnInactiveStyle) }}
                    >
                      ▧ Pareto
                    </button>
                  )}
                  {/* Tabla — soporte por defecto en todos los charts (a menos
                      que se desactive explícitamente con soportaTabla=false). */}
                  {currentItem?.soportaTabla !== false && (
                    <button
                      type="button"
                      onClick={() =>
                        onChange({
                          ...value,
                          viewMode: 'table',
                          // defaults razonables para la primera vez
                          tablePeriodYears: value.tablePeriodYears ?? 5,
                          tableCumulative: value.tableCumulative ?? false,
                        })
                      }
                      style={{
                        ...viewBtnStyle,
                        ...(currentVm === 'table'
                          ? viewBtnActiveStyle
                          : viewBtnInactiveStyle),
                      }}
                    >
                      ▤ Tabla
                    </button>
                  )}
                 </>
               );
             })()}
           </div>

           {/* ── Dropdown "Tipo" para Sector Eléctrico ── */}
           {(() => {
             const elecIds = [
               'elec_produccion_liquidos', 'elec_cap_liquidos', 'elec_fp_liquidos',
               'elec_produccion', 'cap_electricidad', 'factor_planta',
               'elec_produccion_termica', 'elec_cap_termica', 'elec_fp_termica',
             ];
             if (!elecIds.includes(value.tipo)) return null;
             return (
               <div style={{ display: 'grid', gap: 6 }}>
                 <p style={labelStyle}>Tipo</p>
                 <select
                   style={selectStyle}
                   value={value.tipo_electrico || 'todos'}
                   onChange={(e) => {
                     const tipo = e.target.value as 'liquidos' | 'todos' | 'termica';
                     const chartMap: Record<string, string> = {
                       'liquidos': 'elec_produccion_liquidos',
                       'todos': 'elec_produccion',
                       'termica': 'elec_produccion_termica',
                     };
                     const chartId = chartMap[tipo] || 'elec_produccion';
                     onChange({ ...value, tipo_electrico: tipo, tipo: chartId });
                   }}
                 >
                   <option value="liquidos">🛢️ Líquido</option>
                   <option value="todos">🔌 Todos</option>
                   <option value="termica">🔥 Gen. Térmica</option>
                 </select>
               </div>
             );
           })()}

           {/* Controles específicos del modo tabla. */}
          {value.viewMode === 'table' && (
            <div
              style={{
                display: 'flex',
                gap: 12,
                alignItems: 'center',
                flexWrap: 'wrap',
                marginTop: 6,
                padding: '6px 8px',
                borderRadius: 6,
                background: 'rgba(34, 211, 238, 0.06)',
                border: '1px solid rgba(34, 211, 238, 0.25)',
              }}
            >
              <label
                style={{
                  display: 'flex',
                  gap: 6,
                  alignItems: 'center',
                  fontSize: 12,
                  color: '#a5f3fc',
                }}
              >
                <span>Cada</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={value.tablePeriodYears ?? 5}
                  onChange={(e) => {
                    const raw = e.target.value;
                    const n = raw === '' ? null : Number(raw);
                    onChange({ ...value, tablePeriodYears: n });
                  }}
                  style={{
                    width: 56,
                    padding: '2px 6px',
                    borderRadius: 4,
                    border: '1px solid rgba(34, 211, 238, 0.4)',
                    background: 'rgba(2, 6, 23, 0.7)',
                    color: '#e0f2fe',
                    fontSize: 12,
                  }}
                />
                <span>años</span>
              </label>
              <label
                style={{
                  display: 'flex',
                  gap: 6,
                  alignItems: 'center',
                  fontSize: 12,
                  color: '#a5f3fc',
                }}
              >
                <input
                  type="checkbox"
                  checked={Boolean(value.tableCumulative)}
                  onChange={(e) =>
                    onChange({ ...value, tableCumulative: e.target.checked })
                  }
                />
                <span>Acumulado</span>
              </label>
            </div>
          )}
        </div>

        {currentItem?.hasSub === true && (
          <label style={{ display: 'grid', gap: 6 }}>
            <p style={labelStyle}>{currentItem.subFiltroLabel ?? 'Sub-filtro'}</p>
            <select
              style={selectStyle}
              value={value.sub_filtro || (currentItem?.id === 'ref_ambas' ? 'con_crudo' : '')}
              onChange={(e) => onChange({ ...value, sub_filtro: e.target.value })}
            >
              {(currentItem.subFiltros ?? []).map((sf) => (
                <option key={sf} value={sf}>{FUEL_LABELS[sf] ?? sf}</option>
              ))}
            </select>
          </label>
        )}

        {currentItem?.hasLoc === true && (
          <label style={{ display: 'grid', gap: 6 }}>
            <p style={labelStyle}>Localización</p>
            <select
              style={selectStyle}
              value={value.loc ?? ''}
              onChange={(e) => onChange({ ...value, loc: e.target.value })}
            >
              <option value="">Todas</option>
              <option value="URB">Urbana (URB)</option>
              <option value="RUR">Rural (RUR)</option>
              <option value="ZNI">ZNI</option>
            </select>
          </label>
        )}
      </div>

      {/* ── Resumen de selección activa ── */}
      {value.tipo !== '' && (
        <div style={summaryStyle}>
          <span style={summaryLabelStyle}>Selección activa</span>
          <span style={{ color: '#e2e8f0', fontSize: 13 }}>
            {currentItem?.label ?? value.tipo}
            {activeVariable !== '' ? ` — ${activeCapacityLabel}` : ''}
            {value.sub_filtro != null && value.sub_filtro !== '' ? ` [${FUEL_LABELS[value.sub_filtro] ?? value.sub_filtro}]` : ''}
            {value.loc != null && value.loc !== '' ? ` (${value.loc})` : ''}
            {' '}· {displayUnit}
            {canChangeAgrupacion ? ` · ${agrupacionLabel}` : ''}
          </span>
        </div>
      )}
    </div>
  );
}

// ─── Estilos ─────────────────────────────────────────────────────────────────

const labelStyle: React.CSSProperties = {
  margin: '0 0 8px', fontSize: 11, fontWeight: 700,
  letterSpacing: '0.07em', textTransform: 'uppercase', color: '#64748b',
};
const pillsContainerStyle: React.CSSProperties = { display: 'flex', flexWrap: 'wrap', gap: 6 };
const pillStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px',
  borderRadius: 8, border: '1px solid transparent', cursor: 'pointer',
  transition: 'all 0.15s ease', fontFamily: 'inherit',
};
const pillActiveStyle: React.CSSProperties   = { background: 'rgba(59,130,246,0.18)', borderColor: 'rgba(59,130,246,0.45)', color: '#93c5fd' };
const pillInactiveStyle: React.CSSProperties = { background: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.08)', color: '#94a3b8' };

const subsectorBtnStyle: React.CSSProperties = {
  padding: '5px 11px', borderRadius: 20, border: '1px solid transparent',
  cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', transition: 'all 0.12s ease',
};
const subsectorActiveStyle: React.CSSProperties   = { background: 'rgba(139,92,246,0.2)',  borderColor: 'rgba(139,92,246,0.45)', color: '#c4b5fd' };
const subsectorInactiveStyle: React.CSSProperties = { background: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.07)', color: '#94a3b8' };

const chartListStyle: React.CSSProperties = { display: 'grid', gap: 4 };
const chartBtnStyle: React.CSSProperties  = {
  display: 'flex', alignItems: 'center', gap: 10, width: '100%',
  padding: '9px 12px', borderRadius: 8, border: '1px solid transparent',
  cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.12s ease', textAlign: 'left',
};
const chartBtnActiveStyle: React.CSSProperties   = { background: 'rgba(59,130,246,0.12)', borderColor: 'rgba(59,130,246,0.3)', color: '#e2e8f0' };
const chartBtnInactiveStyle: React.CSSProperties = { background: 'transparent', borderColor: 'transparent', color: '#94a3b8' };
const chartBadgeStyle: React.CSSProperties = {
  flexShrink: 0, fontSize: 9, fontWeight: 700, letterSpacing: '0.05em',
  padding: '2px 6px', borderRadius: 4, fontFamily: 'monospace',
};
const checkmarkStyle: React.CSSProperties = { color: '#60a5fa', fontSize: 13, fontWeight: 700, flexShrink: 0 };

const varBtnStyle: React.CSSProperties = {
  padding: '6px 14px', borderRadius: 7, border: '1px solid transparent',
  cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', transition: 'all 0.12s ease',
};
const varBtnActiveStyle: React.CSSProperties   = { background: 'rgba(16,185,129,0.18)',  borderColor: 'rgba(16,185,129,0.4)',  color: '#6ee7b7' };
const varBtnInactiveStyle: React.CSSProperties = { background: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.08)', color: '#94a3b8' };

// Estilos para el selector de agrupación (color naranja para diferenciarlo)
const agrupBtnStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6,
  padding: '6px 14px', borderRadius: 7, border: '1px solid transparent',
  cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', transition: 'all 0.12s ease',
};
const agrupBtnActiveStyle: React.CSSProperties   = { background: 'rgba(234,88,12,0.18)',  borderColor: 'rgba(234,88,12,0.45)', color: '#fb923c' };
const agrupBtnInactiveStyle: React.CSSProperties = { background: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.08)', color: '#94a3b8' };
const agrupDescStyle: React.CSSProperties = {
  margin: '6px 0 0', fontSize: 11, color: '#64748b', fontStyle: 'italic',
};

const bottomRowStyle: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: 'auto auto 1fr 1fr', gap: 20,
  alignItems: 'start', paddingTop: 4, borderTop: '1px solid rgba(255,255,255,0.06)',
};
const unitBtnStyle: React.CSSProperties = {
  padding: '4px 12px', borderRadius: 6, border: '1px solid transparent',
  cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'monospace', transition: 'all 0.12s ease',
};
const unitBtnActiveStyle: React.CSSProperties   = { background: 'rgba(251,191,36,0.18)',  borderColor: 'rgba(251,191,36,0.4)',  color: '#fcd34d' };
const unitBtnInactiveStyle: React.CSSProperties = { background: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.08)', color: '#94a3b8' };

const selectStyle: React.CSSProperties = {
  background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 7, color: '#e2e8f0', padding: '6px 10px', fontSize: 13,
  fontFamily: 'inherit', cursor: 'pointer', outline: 'none', minWidth: 140,
};
const viewBtnStyle: React.CSSProperties = {
  padding: '4px 12px', borderRadius: 6, border: '1px solid transparent',
  cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'inherit', transition: 'all 0.12s ease',
};
const viewBtnActiveStyle: React.CSSProperties   = { background: 'rgba(99,102,241,0.2)',  borderColor: 'rgba(99,102,241,0.45)', color: '#a5b4fc' };
const viewBtnInactiveStyle: React.CSSProperties = { background: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.08)', color: '#94a3b8' };

const summaryStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 4,
  padding: '10px 14px', borderRadius: 8,
  background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)',
};
const summaryLabelStyle: React.CSSProperties = {
  color: '#64748b', fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase',
};
