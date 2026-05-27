"""Siembra automática del catálogo editable de visualización.

Garantiza que al hacer ``alembic upgrade head`` (ya sea en servidor nuevo o
existente), las tablas ``catalog_meta_*`` queden pobladas con los defaults
derivados de los dicts hardcodeados:
    - COLORES_GRUPOS / COLOR_MAP_PWR / COLORES_SECTOR / COLORES_EMISIONES
      / COLOR_BASE_FAMILIA   → catalog_meta_color_palette
    - DISPLAY_NAMES + NOMBRES_COMBUSTIBLES + TITULOS_VARIABLES_CAPACIDAD
      → catalog_meta_label
    - MAPA_SECTOR             → catalog_meta_sector_mapping
    - FAMILIAS_TEC            → catalog_meta_tech_family
    - MENU estático           → catalog_meta_chart_module / _submodule /
                                _chart_config / _chart_subfilter
    - Unidades estándar       → catalog_meta_variable_unit

Idempotente: usa ``ON CONFLICT DO NOTHING`` en los únicos del schema.
Si alguna fila ya existe, no la toca.

Adicionalmente siembra los labels **dinámicos** para los códigos que aparecen
en ``osemosys_output_param_value`` pero no están en ``DISPLAY_NAMES``. Esto
requiere que ``_dynamic_label`` del módulo ``app.visualization.labels`` esté
disponible — si por cualquier razón el import falla, esa fase se salta con
warning y se puede correr después con el script
``scripts/seed_missing_result_labels.py``.

Revision ID: 20260424_0010
Revises: 20260424_0009
Create Date: 2026-04-24
"""

from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "20260424_0010"
down_revision = "20260424_0009"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")
SCHEMA = "osemosys"


# ---------------------------------------------------------------------------
#  MENU hardcoded — snapshot del ChartSelector.tsx del frontend al momento
#  del deploy. La fuente de verdad runtime para nuevos charts vive en
#  ``app.visualization.chart_menu`` (consumida por el startup-sync); este
#  bloque queda inline para que la migración no dependa del estado del paquete
#  durante ``alembic upgrade head``.
# ---------------------------------------------------------------------------
_TRA_SUB = [
    "CARRETERA", "AVI", "BOT", "SHP",
    "LDV", "FWD", "BUS", "TCK_C2P", "TCK_CSG", "MOT", "MIC", "TAX", "STT", "MET",
]
_RES_SUB = ["CKN", "WHT", "AIR", "REF", "ILU", "TV", "OTH"]
_IND_SUB = ["BOI", "FUR", "MPW", "AIR", "REF", "ILU", "OTH"]
_TER_SUB = ["AIR", "ILU", "OTH"]
_DEM_COMB = [
    "NGS", "DSL", "ELC", "GSL", "COA", "LPG", "WOO", "BGS", "BAG", "HDG", "FOL",
    "BDL", "JET", "WAS", "OIL", "AFR", "SAF",
]

_MENU = [
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
                      "sub_label": "Combustible", "sub_filtros": _DEM_COMB,
                      "allowed": ["SECTOR", "FUEL"], "default_grouping": "SECTOR"}]},
         {"code": "residencial", "label": "🏘️ Residencial",
          "charts": [
              {"tipo": "res_total", "label": "Sector Residencial - Consumo Total - UseByTechnology",
               "sub_label": "Uso", "has_loc": True, "sub_filtros": _RES_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
              {"tipo": "res_uso", "label": "Sector Residencial - ProductionByTechnology",
               "sub_label": "Uso", "has_loc": True, "sub_filtros": _RES_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
          ]},
         {"code": "industrial", "label": "🏗️ Industrial",
          "charts": [
              {"tipo": "ind_total", "label": "Sector Industrial - Consumo Total - UseByTechnology",
               "sub_label": "Uso", "sub_filtros": _IND_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
              {"tipo": "ind_uso", "label": "Sector Industrial - ProductionByTechnology",
               "sub_label": "Uso", "sub_filtros": _IND_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
          ]},
         {"code": "transporte", "label": "🚗 Transporte",
          "charts": [
              {"tipo": "tra_total", "label": "Sector Transporte - Consumo Total - UseByTechnology",
               "sub_label": "Modo", "sub_filtros": _TRA_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
              {"tipo": "tra_uso", "label": "Sector Transporte - ProductionByTechnology",
               "sub_label": "Modo", "sub_filtros": _TRA_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
          ]},
         {"code": "terciario", "label": "🏢 Terciario",
          "charts": [
              {"tipo": "ter_total", "label": "Sector Terciario - Consumo Total - UseByTechnology",
               "sub_label": "Uso", "sub_filtros": _TER_SUB,
               "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
              {"tipo": "ter_uso", "label": "Sector Terciario - ProductionByTechnology",
               "sub_label": "Uso", "sub_filtros": _TER_SUB,
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
         {"tipo": "gas_consumo",    "label": "Gas Natural - UseByTechnology",                  "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "gas_produccion", "label": "Gas Natural - ProductionByTechnology",           "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "ref_total",      "label": "Refinerías - ProductionByTechnology",            "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "ref_consumo",    "label": "Refinerías — Consumo Total por Tecnología",      "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "ref_import",     "label": "Refinerías - Importaciones - ProductionByTechnology", "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "ref_cartagena",  "label": "Refinería de Cartagena - UseByTechnology",        "allowed": ["FUEL"], "soporta_pareto": True},
         {"tipo": "ref_barrancabermeja", "label": "Refinería de Barrancabermeja - UseByTechnology", "allowed": ["FUEL"], "soporta_pareto": True},
         {"tipo": "liquidos_prod_import", "label": "Líquidos - Producción + Importación",      "allowed": ["TECNOLOGIA", "FUEL"]},
         {"tipo": "ups_refinacion", "label": "Upstream Refinación - ProductionByTechnology",   "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "saf_produccion", "label": "SAF - Producción - ProductionByTechnology",      "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
     ]},
    {"code": "mineria", "label": "Minería & Extracción", "icon": "⛏️",
     "charts": [
         {"tipo": "min_hidrocarburos",  "label": "Minería Hidrocarburos - ProductionByTechnology",  "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "min_carbon",         "label": "Minería Carbón - ProductionByTechnology",          "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "extraccion_min",     "label": "Minería - Extracción - ProductionByTechnology",    "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "solidos_extraccion", "label": "Sólidos - Extracción - ProductionByTechnology",    "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "solidos_import",     "label": "Sólidos - Importación - ProductionByTechnology",   "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
         {"tipo": "solidos_flujos",     "label": "Sólidos - Importación/Exportación - ProductionByTechnology", "allowed": ["TECNOLOGIA", "FUEL"], "soporta_pareto": True},
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
         {"tipo": "emisiones_total",        "label": "Emisiones - Total Anual - AnnualEmissions"},
         {"tipo": "emisiones_sectorial",    "label": "Emisiones - Por Sector - AnnualTechnologyEmission"},
         {"tipo": "emisiones_gei",          "label": "Emisiones GEI por Sector (CO₂, CH₄, N₂O)"},
         {"tipo": "emisiones_contaminantes", "label": "Emisiones Contaminantes Criterio"},
         {"tipo": "emisiones_contaminantes_pct", "label": "Emisiones Contaminantes Criterio (%)"},
     ]},
    {"code": "otros", "label": "Otros", "icon": "♻️",
     "charts": [{"tipo": "oferta_bioenergia", "label": "Oferta Bioenergía - ProductionByTechnology", "allowed": ["TECNOLOGIA", "FUEL"]}]},
]


def _import_dicts():
    """Importa los dicts hardcodeados del código de visualización.

    Devuelve (colores_grupos, color_map_pwr, colores_sector, colores_emisiones,
    color_base_familia, mapa_sector, familias_tec, display_names,
    nombres_combustibles, titulos_variables_capacidad).
    """
    from app.visualization.colors import (
        COLOR_BASE_FAMILIA,
        COLOR_MAP_PWR,
        COLORES_EMISIONES,
        COLORES_GRUPOS,
        FAMILIAS_TEC,
    )
    from app.visualization.configs import NOMBRES_COMBUSTIBLES, TITULOS_VARIABLES_CAPACIDAD
    from app.visualization.configs_comparacion import COLORES_SECTOR, MAPA_SECTOR
    from app.visualization.labels import DISPLAY_NAMES

    return (
        COLORES_GRUPOS, COLOR_MAP_PWR, COLORES_SECTOR, COLORES_EMISIONES,
        COLOR_BASE_FAMILIA, MAPA_SECTOR, FAMILIAS_TEC,
        DISPLAY_NAMES, NOMBRES_COMBUSTIBLES, TITULOS_VARIABLES_CAPACIDAD,
    )


def _seed_colors(conn, colores_grupos, color_map_pwr, colores_sector, colores_emisiones, color_base_familia) -> int:
    rows = []
    for i, (k, v) in enumerate(colores_grupos.items()):
        rows.append({"group": "fuel", "key": k, "color_hex": v, "sort_order": i})
    for i, (k, v) in enumerate(color_map_pwr.items()):
        rows.append({"group": "pwr", "key": k, "color_hex": v, "sort_order": i})
    for i, (k, v) in enumerate(colores_sector.items()):
        rows.append({"group": "sector", "key": k, "color_hex": v, "sort_order": i})
    for i, (k, v) in enumerate(colores_emisiones.items()):
        rows.append({"group": "emission", "key": k, "color_hex": v, "sort_order": i})
    for i, (k, v) in enumerate(color_base_familia.items()):
        rows.append({"group": "family", "key": k, "color_hex": v, "sort_order": i})
    conn.execute(
        text(f"""
            INSERT INTO {SCHEMA}.catalog_meta_color_palette ("group", key, color_hex, sort_order)
            VALUES (:group, :key, :color_hex, :sort_order)
            ON CONFLICT ("group", key) DO NOTHING
        """),
        rows,
    )
    return len(rows)


def _seed_labels(conn, display_names, nombres_combustibles, titulos_variables_capacidad, mapa_sector) -> int:
    rows = []
    for i, (code, label) in enumerate(display_names.items()):
        rows.append({"code": code, "label_es": label, "category": "technology", "sort_order": i})
    for i, (code, label) in enumerate(nombres_combustibles.items()):
        rows.append({"code": f"FUEL::{code}", "label_es": label, "category": "fuel", "sort_order": i})
    for i, (code, label) in enumerate(titulos_variables_capacidad.items()):
        rows.append({"code": f"VAR_CAP::{code}", "label_es": label, "category": "var_capacidad", "sort_order": i})
    # Sectores como labels con category='sector' (reemplaza la tab Taxonomía).
    for i, (pref, sector) in enumerate(mapa_sector.items()):
        rows.append({"code": pref, "label_es": sector, "category": "sector", "sort_order": i})
    conn.execute(
        text(f"""
            INSERT INTO {SCHEMA}.catalog_meta_label (code, label_es, category, sort_order)
            VALUES (:code, :label_es, :category, :sort_order)
            ON CONFLICT (code) DO NOTHING
        """),
        rows,
    )
    return len(rows)


def _seed_sectors(conn, mapa_sector) -> int:
    rows = [
        {"tech_prefix": p, "sector_name": s, "sort_order": i}
        for i, (p, s) in enumerate(mapa_sector.items())
    ]
    conn.execute(
        text(f"""
            INSERT INTO {SCHEMA}.catalog_meta_sector_mapping (tech_prefix, sector_name, sort_order)
            VALUES (:tech_prefix, :sector_name, :sort_order)
            ON CONFLICT (tech_prefix) DO NOTHING
        """),
        rows,
    )
    return len(rows)


def _seed_tech_families(conn, familias_tec) -> int:
    rows = []
    for family, prefixes in familias_tec.items():
        for i, pref in enumerate(prefixes):
            rows.append({"family_code": family, "tech_prefix": pref, "sort_order": i})
    conn.execute(
        text(f"""
            INSERT INTO {SCHEMA}.catalog_meta_tech_family (family_code, tech_prefix, sort_order)
            VALUES (:family_code, :tech_prefix, :sort_order)
            ON CONFLICT (family_code, tech_prefix) DO NOTHING
        """),
        rows,
    )
    return len(rows)


def _seed_modules_and_charts(conn) -> dict[str, int]:
    counts = {"modules": 0, "submodules": 0, "charts": 0, "subfilters": 0}

    # 1. Módulos
    mod_rows = [
        {"code": m["code"], "label": m["label"], "icon": m.get("icon"), "sort_order": i}
        for i, m in enumerate(_MENU)
    ]
    conn.execute(
        text(f"""
            INSERT INTO {SCHEMA}.catalog_meta_chart_module (code, label, icon, sort_order)
            VALUES (:code, :label, :icon, :sort_order)
            ON CONFLICT (code) DO NOTHING
        """),
        mod_rows,
    )
    counts["modules"] = len(mod_rows)

    # Cargar ids de módulos creados (o existentes).
    module_id_by_code = {
        row[0]: row[1]
        for row in conn.execute(
            text(f"SELECT code, id FROM {SCHEMA}.catalog_meta_chart_module")
        ).all()
    }

    # 2. Submódulos
    sub_rows = []
    for m in _MENU:
        if not m.get("subs"):
            continue
        mod_id = module_id_by_code.get(m["code"])
        if mod_id is None:
            continue
        for i, sub in enumerate(m["subs"]):
            sub_rows.append({
                "module_id": mod_id,
                "code": sub["code"],
                "label": sub["label"],
                "icon": None,
                "sort_order": i,
            })
    if sub_rows:
        conn.execute(
            text(f"""
                INSERT INTO {SCHEMA}.catalog_meta_chart_submodule
                    (module_id, code, label, icon, sort_order)
                VALUES (:module_id, :code, :label, :icon, :sort_order)
                ON CONFLICT (module_id, code) DO NOTHING
            """),
            sub_rows,
        )
    counts["submodules"] = len(sub_rows)

    # Cargar ids de submódulos.
    submodule_id_lookup = {
        (row[0], row[1]): row[2]
        for row in conn.execute(
            text(f"SELECT module_id, code, id FROM {SCHEMA}.catalog_meta_chart_submodule")
        ).all()
    }

    # 3. Chart configs — recolectar todos con su (module_id, submodule_id).
    chart_rows = []
    chart_specs = []  # para subfilters después
    sort_idx = 0
    for m in _MENU:
        mod_id = module_id_by_code.get(m["code"])
        if mod_id is None:
            continue
        if m.get("charts"):
            for c in m["charts"]:
                chart_rows.append({
                    "tipo": c["tipo"],
                    "module_id": mod_id,
                    "submodule_id": None,
                    "label_titulo": c["label"],
                    "variable_default": _guess_variable_default(c),
                    "agrupar_por_default": c.get("default_grouping", "TECNOLOGIA"),
                    "agrupaciones_permitidas_json": c.get("allowed"),
                    "flags_json": {
                        "es_capacidad": bool(c.get("is_capacity", False)),
                        "soporta_pareto": bool(c.get("soporta_pareto", False)),
                        "has_loc": bool(c.get("has_loc", False)),
                        "has_sub_filtro": bool(c.get("sub_filtros")),
                        "sub_filtro_label": c.get("sub_label"),
                    },
                    "is_visible": True,
                    "sort_order": sort_idx,
                })
                chart_specs.append((c["tipo"], c))
                sort_idx += 1
        if m.get("subs"):
            for sub in m["subs"]:
                sub_id = submodule_id_lookup.get((mod_id, sub["code"]))
                for c in sub["charts"]:
                    chart_rows.append({
                        "tipo": c["tipo"],
                        "module_id": mod_id,
                        "submodule_id": sub_id,
                        "label_titulo": c["label"],
                        "variable_default": _guess_variable_default(c),
                        "agrupar_por_default": c.get("default_grouping", "TECNOLOGIA"),
                        "agrupaciones_permitidas_json": c.get("allowed"),
                        "flags_json": {
                            "es_capacidad": bool(c.get("is_capacity", False)),
                            "soporta_pareto": bool(c.get("soporta_pareto", False)),
                            "has_loc": bool(c.get("has_loc", False)),
                            "has_sub_filtro": bool(c.get("sub_filtros")),
                            "sub_filtro_label": c.get("sub_label"),
                        },
                        "is_visible": True,
                        "sort_order": sort_idx,
                    })
                    chart_specs.append((c["tipo"], c))
                    sort_idx += 1
    if chart_rows:
        conn.execute(
            text(f"""
                INSERT INTO {SCHEMA}.catalog_meta_chart_config
                    (tipo, module_id, submodule_id, label_titulo, variable_default,
                     agrupar_por_default, agrupaciones_permitidas_json,
                     flags_json, is_visible, sort_order)
                VALUES
                    (:tipo, :module_id, :submodule_id, :label_titulo, :variable_default,
                     :agrupar_por_default, CAST(:agrupaciones_permitidas_json AS JSONB),
                     CAST(:flags_json AS JSONB), :is_visible, :sort_order)
                ON CONFLICT (tipo) DO NOTHING
            """),
            [
                {**row,
                 "agrupaciones_permitidas_json": _to_jsonb(row["agrupaciones_permitidas_json"]),
                 "flags_json": _to_jsonb(row["flags_json"])}
                for row in chart_rows
            ],
        )
    counts["charts"] = len(chart_rows)

    # 4. Sub-filtros por chart.
    chart_id_by_tipo = {
        row[0]: row[1]
        for row in conn.execute(
            text(f"SELECT tipo, id FROM {SCHEMA}.catalog_meta_chart_config")
        ).all()
    }
    sf_rows = []
    for tipo, c in chart_specs:
        chart_id = chart_id_by_tipo.get(tipo)
        if chart_id is None:
            continue
        for i, code in enumerate(c.get("sub_filtros") or []):
            sf_rows.append({
                "chart_id": chart_id,
                "group_label": c.get("sub_label"),
                "code": code,
                "display_label": None,
                "sort_order": i,
                "default_selected": False,
            })
    if sf_rows:
        conn.execute(
            text(f"""
                INSERT INTO {SCHEMA}.catalog_meta_chart_subfilter
                    (chart_id, group_label, code, display_label, sort_order, default_selected)
                VALUES
                    (:chart_id, :group_label, :code, :display_label, :sort_order, :default_selected)
                ON CONFLICT (chart_id, code) DO NOTHING
            """),
            sf_rows,
        )
    counts["subfilters"] = len(sf_rows)

    return counts


def _guess_variable_default(c: dict) -> str:
    """Deduce ``variable_default`` a partir del título del chart."""
    label = c.get("label", "")
    if "TotalCapacityAnnual" in label or c.get("is_capacity"):
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


def _seed_variable_units(conn) -> int:
    rows = [
        {
            "variable_name": "__DEFAULT_ENERGY__",
            "unit_base": "PJ",
            "display_units_json": [
                {"code": "PJ",  "label": "PJ",  "factor": 1.0},
                {"code": "GW",  "label": "GW",  "factor": 1.0 / 31.536},
                {"code": "MW",  "label": "MW",  "factor": 1.0 / 0.031536},
                {"code": "TWh", "label": "TWh", "factor": 1.0 / 3.6},
                {"code": "Gpc", "label": "Gpc", "factor": 1.0 / 1.0095581216},
                {"code": "kton", "label": "kton", "factor": None},
            ],
        },
        {
            "variable_name": "__DEFAULT_EMISSION__",
            "unit_base": "MtCO2eq",
            "display_units_json": [
                {"code": "MtCO2eq", "label": "MtCO₂eq", "factor": 1.0},
                {"code": "ktCO2eq", "label": "ktCO₂eq", "factor": 1000.0},
            ],
        },
    ]
    conn.execute(
        text(f"""
            INSERT INTO {SCHEMA}.catalog_meta_variable_unit
                (variable_name, unit_base, display_units_json)
            VALUES
                (:variable_name, :unit_base, CAST(:display_units_json AS JSONB))
            ON CONFLICT (variable_name) DO NOTHING
        """),
        [{**r, "display_units_json": _to_jsonb(r["display_units_json"])} for r in rows],
    )
    return len(rows)


def _to_jsonb(value) -> str | None:
    """Serializa a JSON si no es None. Postgres ``CAST(... AS JSONB)`` acepta string."""
    import json
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _seed_missing_dynamic_labels(conn) -> int:
    """Para cada ``technology_name`` / ``fuel_name`` presente en resultados que
    no tenga label en BD, inserta un label heurístico vía ``_dynamic_label``.

    Si no hay resultados aún en ``osemosys_output_param_value``, no hace nada.
    """
    try:
        from app.visualization.labels import _dynamic_label  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo importar _dynamic_label: %s — salta dynamic seeding.", exc)
        return 0

    existing = {
        row[0]
        for row in conn.execute(
            text(f"SELECT code FROM {SCHEMA}.catalog_meta_label")
        ).all()
    }
    added = 0
    for col, category in (("technology_name", "technology"), ("fuel_name", "fuel"), ("emission_name", "emission")):
        rows = conn.execute(
            text(
                f"SELECT DISTINCT {col} FROM {SCHEMA}.osemosys_output_param_value "
                f"WHERE {col} IS NOT NULL"
            )
        ).all()
        codes = {r[0] for r in rows if r[0]}
        missing = [c for c in codes if c not in existing]
        if not missing:
            continue
        payload = [
            {"code": c, "label_es": _dynamic_label(c), "category": category, "sort_order": 0}
            for c in sorted(missing)
        ]
        conn.execute(
            text(f"""
                INSERT INTO {SCHEMA}.catalog_meta_label (code, label_es, category, sort_order)
                VALUES (:code, :label_es, :category, :sort_order)
                ON CONFLICT (code) DO NOTHING
            """),
            payload,
        )
        added += len(payload)
        existing.update(missing)
    return added


def upgrade() -> None:
    conn = op.get_bind()
    try:
        (
            colores_grupos, color_map_pwr, colores_sector, colores_emisiones,
            color_base_familia, mapa_sector, familias_tec,
            display_names, nombres_combustibles, titulos_variables_capacidad,
        ) = _import_dicts()
    except Exception as exc:
        logger.error(
            "No se pudieron importar los dicts de visualización (app.visualization.*): %s. "
            "Abortando la siembra. Corre el script scripts/seed_visualization_catalog.py manualmente.",
            exc,
        )
        return

    n_colors = _seed_colors(
        conn, colores_grupos, color_map_pwr, colores_sector, colores_emisiones, color_base_familia
    )
    n_labels = _seed_labels(
        conn, display_names, nombres_combustibles, titulos_variables_capacidad, mapa_sector
    )
    n_sectors = _seed_sectors(conn, mapa_sector)
    n_families = _seed_tech_families(conn, familias_tec)
    chart_counts = _seed_modules_and_charts(conn)
    n_units = _seed_variable_units(conn)
    n_dynamic = _seed_missing_dynamic_labels(conn)

    logger.info(
        "Seed catalog_meta_*: colors=%d labels=%d sectors=%d families=%d "
        "modules=%d submodules=%d charts=%d subfilters=%d units=%d dynamic_labels=%d",
        n_colors, n_labels, n_sectors, n_families,
        chart_counts["modules"], chart_counts["submodules"],
        chart_counts["charts"], chart_counts["subfilters"],
        n_units, n_dynamic,
    )


def downgrade() -> None:
    """No-op — el seed es aditivo (ON CONFLICT DO NOTHING).

    Si necesitas limpiar el catálogo, hazlo manualmente con TRUNCATE de las
    tablas ``catalog_meta_*`` en un script administrativo. Una migración
    downgrade genérica es peligrosa: borraría ediciones manuales del admin.
    """
