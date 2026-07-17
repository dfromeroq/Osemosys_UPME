"""Registries Python para funciones no serializables del catálogo de visualización."""

from __future__ import annotations

from typing import Any, Callable

from app.visualization import colors
from app.visualization.configs_legacy import (
    CONFIGS_CON_ALIAS_PWR,
    PWR_TECH_ALIASES,
    _color_h2_verde_azul_gris,
    _map_electrolisis_verde,
    _map_h2_consumo_grupo,
    _map_h2_verde_azul_gris,
)

ColorFn = Callable[..., Any]
FilterFn = Callable[..., Any]

COLOR_FN_REGISTRY: dict[str, ColorFn | None] = {
    "tecnologias": colors.generar_colores_tecnologias,
    "grupo_fijo": colors._color_por_grupo_fijo,
    "electricidad": colors._color_electricidad,
    "sector": colors._color_por_sector,
    "sector_gei": colors._color_por_sector_gei,
    "emision": colors._color_por_emision,
    "electrolisis": colors._color_electrolisis,
    "h2_produccion": colors._color_h2_produccion,
    "h2_consumo": colors._color_h2_consumo,
    "bioenergia": colors._color_bioenergia,
    "gas_produccion": colors._color_gas_produccion,
    "liquidos_import": colors._color_liquidos_import,
    "modo": colors._color_por_modo,
    "ref_import": colors._color_ref_import,
    "h2_verde_azul_gris": _color_h2_verde_azul_gris,
    "none": None,
}

COLOR_FN_NAME_TO_KEY: dict[str, str] = {
    fn.__name__: key for key, fn in COLOR_FN_REGISTRY.items() if fn is not None
}

POST_MAP_REGISTRY: dict[str, Callable[[str], str]] = {
    "electrolisis_verde": _map_electrolisis_verde,
    "h2_verde_azul_gris": _map_h2_verde_azul_gris,
    "h2_consumo_grupo": _map_h2_consumo_grupo,
}

# Mapeo nombre función filtro legacy → especificación de filtro en BD.
FILTER_FN_SPECS: dict[str, dict[str, Any]] = {
    "_filtro_gas_consumo": {"group": "TECNOLOGIAS_GAS_CONSUMO"},
    "_filtro_gas_produccion": {"group": "TECNOLOGIAS_GAS_PRODUCCION"},
    "_filtro_gas_flujos": {"group": "TECNOLOGIAS_GAS_FLUJOS"},
    "_filtro_ref_total": {"group": "TECNOLOGIAS_REFINERIAS"},
    "_filtro_ref_import": {"group": "TECNOLOGIAS_REFINERIAS_IMPORTACIONES"},
    "_filtro_ref_cartagena": {"group": "TECNOLOGIAS_REFINERIAS_CARTAGENA"},
    "_filtro_ref_barrancabermeja": {"group": "TECNOLOGIAS_REFINERIAS_BARRANCABERMEJA"},
    "_filtro_ref_ambas": {
        "kind": "ref_ambas",
        "tech_group": "TECNOLOGIAS_REFINERIAS_BAR_CAR",
        "fuel_con_crudo": "COMBUSTIBLES_REFINERIA_CON_CRUDO",
        "fuel_sin_crudo": "COMBUSTIBLES_REFINERIA_SIN_CRUDO",
    },
    "_filtro_liquidos_produccion_importacion": {"group": "TECNOLOGIAS_LIQUIDOS_PRODUCCION_IMPORTACION"},
    "_filtro_export_liquidos": {"group": "TECNOLOGIAS_EXPORTACION_LIQUIDOS"},
    "_filtro_import_liquidos": {"group": "TECNOLOGIAS_IMPORTACION_LIQIDOS"},
    "_filtro_crudo_flujos": {"group": "TECNOLOGIAS_IMPORTACION_EXPORTACION_CRUDO"},
    "_filtro_exp_carbon": {"group": "TECNOLOGIAS_EXPORTACION_CARBON"},
    "_filtro_ref_produccion_importaciones": {"group": "TECNOLOGIAS_REFINERIAS_IMPORTACIONES_LIQUIDOS"},
    "_filtro_residencial": {
        "kind": "sector_sub_loc",
        "root_group": "TECNOLOGIAS_RESIDENCIALES",
        "subfiltros_dict": "SUBFILTROS_RESIDENCIALES",
        "loc_groups": {"URB": "TEC_RES_URB", "RUR": "TEC_RES_RUR", "ZNI": "TEC_RES_ZNI"},
    },
    "_filtro_industrial": {
        "kind": "sector_sub",
        "root_group": "TECNOLOGIAS_INDUSTRIALES",
        "subfiltros_dict": "SUBFILTROS_INDUSTRIALES",
    },
    "_filtro_transporte": {
        "kind": "sector_sub",
        "root_group": "TECNOLOGIAS_TRANSPORTE",
        "subfiltros_dict": "SUBFILTROS_TRANSPORTE",
    },
    "_filtro_transporte_por_modo": {"group": "TECNOLOGIAS_TRANSPORTE_POR_MODO"},
    "_filtro_terciario": {
        "kind": "sector_sub",
        "root_group": "TECNOLOGIAS_TERCIARIO",
        "subfiltros_dict": "SUBFILTROS_TERCIARIO",
    },
    "_filtro_otros": {"kind": "startswith", "require_sub_filtro": True},
    "_filtro_pwr": {"group": "TECNOLOGIAS_PWR"},
    "_filtro_pwr_liquidos": {"group": "TECNOLOGIAS_PWR_LIQUIDOS"},
    "_filtro_pwr_termica": {"group": "TECNOLOGIAS_PWR_TERMICAS"},
    "_filtro_construccion": {"group": "TECNOLOGIAS_CONSTRUCCION"},
    "_filtro_agroforestal": {"group": "TECNOLOGIAS_AGROFORESTAL"},
    "_filtro_mineria": {"group": "TECNOLOGIAS_MINERIA"},
    "_filtro_coquerias": {"group": "TECNOLOGIAS_COQUERIAS"},
    "_filtro_solidos_import": {"group": "TECNOLOGIAS_IMPORTACION_SOLIDOS"},
    "_filtro_solidos_flujos": {"group": "TECNOLOGIAS_IMPORTACION_EXPORTACION_SOLIDOS"},
    "_filtro_solidos_extraccion": {"group": "TECNOLOGIAS_EXTRACCION_SOLIDOS"},
    "_filtro_extraccion_min": {"group": "TECNOLOGIAS_EXTRACCION_MINERIA"},
    "_filtro_saf_produccion": {"group": "TECNOLOGIAS_PRODUCCION_SAF"},
    "_filtro_h2": {
        "kind": "fuel_exclude_tech",
        "fuel_group": "COMBUSTIBLES_H2",
        "exclude_tech_group": "TECNOLOGIAS_H2_EXCLUIR",
    },
    "_filtro_electrolisis_verde": {"group": "TECNOLOGIAS_ELECTROLISIS_VERDE"},
    "_filtro_h2_verde_azul_gris": {"group": "TECNOLOGIAS_H2_PRODUCCION_VERDE_AZUL_GRIS"},
    "_filtro_ups_refinacion": {"group": "TECNOLOGIAS_UPSTREAM_REFINACION"},
    "_filtro_min_hidrocarburos": {"group": "TECNOLOGIAS_MINERIA_HIDROCARBUROS"},
    "_filtro_min_carbon": {"group": "TECNOLOGIAS_MINERIA_CARBON"},
    "_filtro_oferta_bioenergia": {"group": "TECNOLOGIAS_OFERTA_BIOENERGIA"},
    "_filtro_gei": {"group": "COMBUSTIBLES_GEI"},
    "_filtro_contaminantes": {"group": "FUELS_CONTAMINANTES", "entity": "FUEL"},
    "_filtro_demanda_por_combustible": {
        "kind": "demand_fuel",
        "tech_group": "TECNOLOGIAS_DEMANDA_TODOS",
        "valid_fuels": "FUEL_VALIDOS_DEMANDA",
    },
    "_filtro_consumo_liquidos": {
        "kind": "tech_and_fuel",
        "tech_group": "TECNOLOGIAS_DEMANDA_TODOS",
        "fuel_group": "FUELS_LIQUIDOS",
    },
    "_filtro_liquidos_total": {
        "kind": "tech_and_fuel",
        "tech_groups": ["TECNOLOGIAS_DEMANDA_TODOS", "TECNOLOGIAS_PWR_LIQUIDOS"],
        "fuel_group": "FUELS_LIQUIDOS",
    },
    "_filtro_demanda_exportaciones_liquidos": {
        "kind": "tech_and_fuel",
        "tech_group": "TECNOLOGIAS_DEMANDA_EXPORTACION_LIQUIDOS_TODOS",
        "fuel_group": "FUELS_LIQUIDOS",
    },
    "_filtro_min_oil": {"group": "TECNOLOGIAS_PETROLEO_CRUDO"},
    "_filtro_imp_oil": {"group": "TECNOLOGIAS_IMPORTACION_PETROLEO_CRUDO"},
    "_filtro_exp_oil": {"group": "TECNOLOGIAS_EXPORTACION_PETROLEO"},
    "_filtro_recursos_crudo": {"group": "TECNOLOGIAS_RECURSOS_CRUDO"},
    "_filtro_recursos_gas": {"group": "TECNOLOGIAS_RECURSOS_GAS"},
    "_filtro_recursos_carbon": {
        "kind": "recursos_carbon",
        "tech_group": "TECNOLOGIAS_FILTRO_RECURSOS_CARBON",
        "fuel_group": "COMBUSTIBLES_FILTRO_RECURSOS_CARBON",
        "exclude_tech_group": "TECNOLOGIAS_EXCLUIR_COMBUSTIBLE_COA_RECURSOS_CARBON",
    },
}

__all__ = [
    "COLOR_FN_REGISTRY",
    "COLOR_FN_NAME_TO_KEY",
    "CONFIGS_CON_ALIAS_PWR",
    "FILTER_FN_SPECS",
    "POST_MAP_REGISTRY",
    "PWR_TECH_ALIASES",
]
