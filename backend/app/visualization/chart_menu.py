"""Estructura jerárquica del ChartSelector — fuente de verdad en código.

Este módulo es la **única** fuente de la jerarquía módulo → submódulo → chart →
sub-filtro que se siembra a `catalog_meta_*` cuando una instalación nueva o un
deploy detectan que la BD no la contiene.

Es importado por:
    - ``backend/alembic/versions/20260424_0010_seed_catalog_defaults.py``
      (siembra inicial al hacer ``alembic upgrade head``)
    - ``backend/app/visualization/catalog_sync.py``
      (sync idempotente al arrancar el API: agrega charts nuevos del código
       a la BD sin pisar ediciones del curador)

Cuando se agrega una gráfica nueva en ``CONFIGS`` (configs.py), añadir también
una entrada aquí con ``module_code`` (+ ``submodule_code`` si aplica). Al
reiniciar el API la gráfica aparece automáticamente en el catálogo editable.
"""

from __future__ import annotations

# ── Sub-filtros (listas reutilizadas por varios charts) ─────────────────────
TRA_SUB = [
    "CARRETERA", "AVI", "BOT", "SHP",
    "LDV", "FWD", "BUS", "TCK_C2P", "TCK_CSG",
    "MOT", "MIC", "TAX", "STT", "MET",
]
RES_SUB = ["CKN", "WHT", "AIR", "REF", "ILU", "TV", "OTH"]
IND_SUB = ["BOI", "FUR", "MPW", "AIR", "REF", "ILU", "OTH"]
TER_SUB = ["AIR", "ILU", "OTH"]
DEM_COMB = [
    "NGS", "DSL", "ELC", "GSL", "COA", "LPG", "WOO", "BGS", "BAG", "HDG", "FOL",
    "BDL", "JET", "WAS", "OIL", "AFR", "SAF",
]


# ── MENU ────────────────────────────────────────────────────────────────────
# Estructura: lista ordenada de módulos. Cada módulo puede tener:
#   - "charts": lista directa de charts (sin submódulo)
#   - "subs":   lista de submódulos, cada uno con sus "charts"
#
# Cada chart admite:
#   tipo (str)                          — id único, debe matchear configs.CONFIGS
#   label (str)                         — título mostrado en el ChartSelector
#   allowed (list[str], opcional)       — agrupaciones permitidas
#   default_grouping (str, opcional)    — agrupación inicial (default "TECNOLOGIA")
#   is_capacity (bool, opcional)        — flag es_capacidad
#   soporta_pareto (bool, opcional)     — flag soporta_pareto
#   has_loc (bool, opcional)            — flag has_loc
#   sub_filtros (list[str], opcional)   — sub-filtros del chart (CARRETERA, …)
#   sub_label (str, opcional)           — etiqueta del grupo de sub-filtros
MENU = [
    {"code": "electrico", "label": "Sector Eléctrico", "icon": "⚡",
     "charts": [
         {"tipo": "elec_produccion", "label": "Producción de Electricidad - ProductionByTechnology",
          "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "prd_electricidad", "label": "Producción de Electricidad - ProductionByTechnology (%)"},
         {"tipo": "cap_electricidad", "label": "Matriz Eléctrica (Capacidad) - TotalCapacityAnnual",
          "is_capacity": True},
         {"tipo": "factor_planta", "label": "Factor de Planta (%)"},
     ]},
    {"code": "demanda", "label": "Demanda Final — Sectores", "icon": "🏠",
     "subs": [
         {"code": "consum_combustible", "label": "🔥 Todos los Sectores",
          "charts": [{"tipo": "dem_consumo_combustible", "label": "Consumo Por Sector",
                      "sub_label": "Combustible", "sub_filtros": DEM_COMB,
                      "allowed": ["SECTOR", "FUEL"], "default_grouping": "SECTOR"}]},
         {"code": "residencial", "label": "🏘️ Residencial",
          "charts": [
              {"tipo": "res_total", "label": "Sector Residencial - Consumo Total - UseByTechnology",
               "sub_label": "Uso", "has_loc": True, "sub_filtros": RES_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
              {"tipo": "res_uso", "label": "Sector Residencial - ProductionByTechnology",
               "sub_label": "Uso", "has_loc": True, "sub_filtros": RES_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
          ]},
         {"code": "industrial", "label": "🏗️ Industrial",
          "charts": [
              {"tipo": "ind_total", "label": "Sector Industrial - Consumo Total - UseByTechnology",
               "sub_label": "Uso", "sub_filtros": IND_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
              {"tipo": "ind_uso", "label": "Sector Industrial - ProductionByTechnology",
               "sub_label": "Uso", "sub_filtros": IND_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
          ]},
         {"code": "transporte", "label": "🚗 Transporte",
          "charts": [
              {"tipo": "tra_total", "label": "Sector Transporte - Consumo Total - UseByTechnology",
               "sub_label": "Modo", "sub_filtros": TRA_SUB,
               "allowed": ["TECNOLOGIA", "FUEL", "TRANSPORTE_GRUPO"], "soporta_pareto": True},
              {"tipo": "tra_uso", "label": "Sector Transporte - ProductionByTechnology",
               "sub_label": "Modo", "sub_filtros": TRA_SUB,
               "allowed": ["TECNOLOGIA", "FUEL", "TRANSPORTE_GRUPO"], "soporta_pareto": True},
          ]},
         {"code": "terciario", "label": "🏢 Terciario",
          "charts": [
              {"tipo": "ter_total", "label": "Sector Terciario - Consumo Total - UseByTechnology",
               "sub_label": "Uso", "sub_filtros": TER_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
              {"tipo": "ter_uso", "label": "Sector Terciario - ProductionByTechnology",
               "sub_label": "Uso", "sub_filtros": TER_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
          ]},
         {"code": "construccion", "label": "🔨 Construcción",
          "charts": [{"tipo": "con_total", "label": "Sector Construcción - Consumo Total - UseByTechnology",
                      "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True}]},
         {"code": "agroforestal", "label": "🌾 Agroforestal",
          "charts": [{"tipo": "agf_total", "label": "Sector Agroforestal - Consumo Total - UseByTechnology",
                      "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True}]},
         {"code": "mineria_dem", "label": "⛏️ Minería (demanda)",
          "charts": [{"tipo": "min_total", "label": "Sector Minería - Consumo Total - UseByTechnology",
                      "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True}]},
         {"code": "coquerias", "label": "🧱 Coquerías",
          "charts": [{"tipo": "coq_total", "label": "Sector Coquerías - Consumo Total - UseByTechnology",
                      "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True}]},
         {"code": "otros_dem", "label": "📦 Otros Sectores",
          "charts": [{"tipo": "otros_total", "label": "Otros Sectores - Consumo Total - UseByTechnology",
                      "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True}]},
     ]},
    {"code": "capacidades", "label": "Capacidades Instaladas", "icon": "🏭",
     "charts": [
         {"tipo": "cap_industrial", "label": "Sector Industrial (Capacidad) - TotalCapacityAnnual", "is_capacity": True},
         {"tipo": "cap_transporte", "label": "Sector Transporte (Capacidad) - TotalCapacityAnnual", "is_capacity": True},
         {"tipo": "cap_terciario",  "label": "Sector Terciario (Capacidad) - TotalCapacityAnnual", "is_capacity": True},
         {"tipo": "cap_otros",      "label": "Otros Sectores (Capacidad) - TotalCapacityAnnual", "is_capacity": True},
         {"tipo": "ref_capacidad",  "label": "Capacidad de Refinación por Derivado", "is_capacity": True},
     ]},
    {"code": "upstream", "label": "Upstream & Refinación", "icon": "🛢️",
     "charts": [
         {"tipo": "gas_consumo",         "label": "Gas Natural - UseByTechnology",                       "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "gas_produccion",      "label": "Gas Natural - ProductionByTechnology",                "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "gas_capacidad",      "label": "Gas Natural — Capacidad de Extracción y Regasificación - TotalCapacityAnnual", "is_capacity": True},
         {"tipo": "gas_import_export",  "label": "Gas Natural — Importaciones y Exportaciones - ProductionByTechnology", "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "ref_total",           "label": "Refinerías - ProductionByTechnology",                 "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "ref_consumo",         "label": "Refinerías — Consumo Total por Tecnología",           "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "ref_import",          "label": "Refinerías - Importaciones - ProductionByTechnology", "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "ref_cartagena",       "label": "Refinería de Cartagena - UseByTechnology",            "allowed": ["FUEL"], "soporta_pareto": True},
         {"tipo": "ref_barrancabermeja", "label": "Refinería de Barrancabermeja - UseByTechnology",       "allowed": ["FUEL"], "soporta_pareto": True},
         {"tipo": "liquidos_prod_import","label": "Líquidos - Producción + Importación",                  "allowed": ["TECNOLOGIA", "FUEL"]},
         {"tipo": "ups_refinacion",      "label": "Upstream Refinación - ProductionByTechnology",        "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "saf_produccion",      "label": "SAF - Producción - ProductionByTechnology",           "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "imp_exp_crudo",      "label": "Crudo - Importaciones y Exportaciones - ProductionByTechnology", "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "elec_consumo_liquidos", "label": "Consumo de Líquidos - Sector Eléctrico - UseByTechnology", "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "ref_produccion_importaciones", "label": "Refinerías + Importaciones de Líquidos - ProductionByTechnology", "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
     ]},
    {"code": "mineria", "label": "Minería & Extracción", "icon": "⛏️",
     "charts": [
         {"tipo": "min_hidrocarburos",   "label": "Minería Hidrocarburos - ProductionByTechnology",       "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "min_carbon",          "label": "Minería Carbón - ProductionByTechnology",              "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "extraccion_min",      "label": "Minería - Extracción - ProductionByTechnology",        "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "solidos_extraccion",  "label": "Sólidos - Extracción - ProductionByTechnology",        "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "solidos_import",      "label": "Sólidos - Importación - ProductionByTechnology",       "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "solidos_flujos",      "label": "Sólidos - Importación/Exportación - ProductionByTechnology", "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
     ]},
    {"code": "hidrogeno", "label": "Hidrógeno", "icon": "💧",
     "charts": [
         {"tipo": "cap_h2",     "label": "Hidrógeno - ProductionByTechnology",   "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "h2_consumo", "label": "Hidrógeno - Consumo - UseByTechnology", "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
     ]},
    {"code": "comercio", "label": "Comercio Exterior", "icon": "🚢",
     "charts": [{"tipo": "exp_liquidos_gas", "label": "Exportaciones — Líquidos y Gas", "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True}]},
    {"code": "emisiones", "label": "Emisiones", "icon": "🌿",
     "charts": [
         {"tipo": "emisiones_total",             "label": "Emisiones - Total Anual - AnnualEmissions"},
         {"tipo": "emisiones_sectorial",         "label": "Emisiones - Por Sector - AnnualTechnologyEmission"},
         {"tipo": "emisiones_gei",               "label": "Emisiones GEI por Sector (CO₂, CH₄, N₂O)"},
         {"tipo": "emisiones_contaminantes",     "label": "Emisiones Contaminantes Criterio"},
         {"tipo": "emisiones_contaminantes_pct", "label": "Emisiones Contaminantes Criterio (%)"},
     ]},
    {"code": "otros", "label": "Otros", "icon": "♻️",
     "charts": [{"tipo": "oferta_bioenergia", "label": "Oferta Bioenergía - ProductionByTechnology", "allowed": ["TECNOLOGIA", "FUEL"]}]},
]


def iter_charts():
    """Itera ``(module, submodule_or_None, chart_dict)`` para todos los charts."""
    for m in MENU:
        if m.get("charts"):
            for c in m["charts"]:
                yield m, None, c
        if m.get("subs"):
            for sub in m["subs"]:
                for c in sub["charts"]:
                    yield m, sub, c


def guess_variable_default(chart: dict) -> str:
    """Deduce ``variable_default`` desde el label del chart."""
    label = chart.get("label", "")
    if "TotalCapacityAnnual" in label or chart.get("is_capacity"):
        return "TotalCapacityAnnual"
    if "UseByTechnology" in label:
        return "UseByTechnology"
    if "ProductionByTechnology" in label:
        return "ProductionByTechnology"
    if "AnnualTechnologyEmission" in label:
        return "AnnualTechnologyEmission"
    if "AnnualEmissions" in label:
        return "AnnualEmissions"
    return "UseByTechnology"


def chart_flags(chart: dict) -> dict:
    """Devuelve el dict ``flags_json`` para una entrada de chart."""
    return {
        "es_capacidad": bool(chart.get("is_capacity", False)),
        "soporta_pareto": bool(chart.get("soporta_pareto", False)),
        "has_loc": bool(chart.get("has_loc", False)),
        "has_sub_filtro": bool(chart.get("sub_filtros")),
        "sub_filtro_label": chart.get("sub_label"),
    }
