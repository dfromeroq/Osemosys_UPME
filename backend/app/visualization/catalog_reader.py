"""Lector del catálogo de visualización desde cache BD."""

from __future__ import annotations

from typing import Any

from app.visualization.catalog_cache import get_catalog_cache, warm_catalog_cache
from app.visualization.configs_registry import CONFIGS_CON_ALIAS_PWR, PWR_TECH_ALIASES


def get_configs() -> dict[str, Any]:
    return get_catalog_cache().configs


def get_menu() -> list[dict[str, Any]]:
    return get_catalog_cache().menu


def get_labels() -> dict[str, str]:
    return get_catalog_cache().labels


def get_colores_grupos() -> dict[str, str]:
    return get_catalog_cache().colores_grupos


def get_colores_sector() -> dict[str, str]:
    return get_catalog_cache().colores_sector


def get_colores_emisiones() -> dict[str, str]:
    return get_catalog_cache().colores_emisiones


def get_mapa_sector() -> dict[str, str]:
    return get_catalog_cache().mapa_sector


def get_familias_tec() -> dict[str, list[str]]:
    return get_catalog_cache().familias_tec


def get_color_map_pwr() -> dict[str, str]:
    return get_catalog_cache().color_map_pwr


def get_nombres_combustibles() -> dict[str, str]:
    return get_catalog_cache().nombres_combustibles


def get_titulos_variables_capacidad() -> dict[str, str]:
    return get_catalog_cache().titulos_variables_capacidad


def get_configs_comparacion() -> dict[str, Any]:
    return get_catalog_cache().configs_comparacion


def get_data_explorer_filters(tipo: str) -> dict[str, Any] | None:
    meta = get_catalog_cache().chart_catalog_meta.get(tipo)
    if meta and meta.get("data_explorer_filters"):
        return meta["data_explorer_filters"]
    return None


__all__ = [
    "CONFIGS_CON_ALIAS_PWR",
    "PWR_TECH_ALIASES",
    "get_configs",
    "get_menu",
    "get_labels",
    "get_colores_grupos",
    "get_colores_sector",
    "get_colores_emisiones",
    "get_mapa_sector",
    "get_familias_tec",
    "get_color_map_pwr",
    "get_nombres_combustibles",
    "get_titulos_variables_capacidad",
    "get_configs_comparacion",
    "get_data_explorer_filters",
    "warm_catalog_cache",
]
