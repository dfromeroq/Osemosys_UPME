"""Facade runtime del catálogo de visualización (BD obligatoria)."""

from __future__ import annotations

from typing import Any

from app.visualization.catalog_reader import (
    get_configs,
    get_nombres_combustibles,
    get_titulos_variables_capacidad,
)
from app.visualization.configs_registry import (
    CONFIGS_CON_ALIAS_PWR,
    FILTER_FN_SPECS,
    POST_MAP_REGISTRY,
    PWR_TECH_ALIASES,
)
from app.visualization.configs_legacy import (
    _map_electrolisis_verde,
    _map_h2_consumo_grupo,
    _map_h2_verde_azul_gris,
)


class _ConfigsView:
    def __getitem__(self, key: str) -> dict[str, Any]:
        return get_configs()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return get_configs().get(key, default)

    def __contains__(self, key: object) -> bool:
        return key in get_configs()

    def keys(self):
        return get_configs().keys()

    def values(self):
        return get_configs().values()

    def items(self):
        return get_configs().items()

    def __iter__(self):
        return iter(get_configs())

    def __len__(self) -> int:
        return len(get_configs())


CONFIGS = _ConfigsView()


class _LazyDictView:
    def __init__(self, loader):
        self._loader = loader

    def __getitem__(self, key: str) -> Any:
        return self._loader()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._loader().get(key, default)

    def __contains__(self, key: object) -> bool:
        return key in self._loader()

    def keys(self):
        return self._loader().keys()

    def values(self):
        return self._loader().values()

    def items(self):
        return self._loader().items()

    def __iter__(self):
        return iter(self._loader())

    def __len__(self) -> int:
        return len(self._loader())


NOMBRES_COMBUSTIBLES = _LazyDictView(get_nombres_combustibles)
TITULOS_VARIABLES_CAPACIDAD = _LazyDictView(get_titulos_variables_capacidad)


def _tech_list(code: str) -> list[str]:
    from app.visualization.catalog_cache import get_catalog_cache

    return list(get_catalog_cache().filter_resolver.tech(code))


def _filtro_for(tipo: str):
    cfg = get_configs().get(tipo) or {}
    return cfg.get("filtro")


def _filtro_recursos_crudo(df, **kw):
    fn = _filtro_for("recursos_crudo")
    return fn(df, **kw) if fn else df.iloc[0:0]


def _filtro_recursos_gas(df, **kw):
    fn = _filtro_for("recursos_gas")
    return fn(df, **kw) if fn else df.iloc[0:0]


def _filtro_recursos_carbon(df, **kw):
    fn = _filtro_for("recursos_carbon")
    return fn(df, **kw) if fn else df.iloc[0:0]


_LAZY_TECH_LISTS = {
    "TECNOLOGIAS_EXPORTACION_CARBON": "TECNOLOGIAS_EXPORTACION_CARBON",
    "TECNOLOGIAS_INDUSTRIALES": "TECNOLOGIAS_INDUSTRIALES",
    "TECNOLOGIAS_RESIDENCIALES": "TECNOLOGIAS_RESIDENCIALES",
    "TECNOLOGIAS_TRANSPORTE": "TECNOLOGIAS_TRANSPORTE",
    "TECNOLOGIAS_TRANSPORTE_CARRETERA": "TECNOLOGIAS_TRANSPORTE_CARRETERA",
    "TECNOLOGIAS_TERCIARIO": "TECNOLOGIAS_TERCIARIO",
    "TEC_RES_URB": "TEC_RES_URB",
    "TEC_RES_RUR": "TEC_RES_RUR",
    "TEC_RES_ZNI": "TEC_RES_ZNI",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_TECH_LISTS:
        return _tech_list(_LAZY_TECH_LISTS[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CONFIGS",
    "CONFIGS_CON_ALIAS_PWR",
    "FILTER_FN_SPECS",
    "NOMBRES_COMBUSTIBLES",
    "POST_MAP_REGISTRY",
    "PWR_TECH_ALIASES",
    "TITULOS_VARIABLES_CAPACIDAD",
    "TECNOLOGIAS_EXPORTACION_CARBON",
    "TECNOLOGIAS_INDUSTRIALES",
    "TECNOLOGIAS_RESIDENCIALES",
    "TECNOLOGIAS_TERCIARIO",
    "TECNOLOGIAS_TRANSPORTE",
    "TECNOLOGIAS_TRANSPORTE_CARRETERA",
    "TEC_RES_RUR",
    "TEC_RES_URB",
    "TEC_RES_ZNI",
    "_filtro_recursos_carbon",
    "_filtro_recursos_crudo",
    "_filtro_recursos_gas",
    "_map_electrolisis_verde",
    "_map_h2_consumo_grupo",
    "_map_h2_verde_azul_gris",
]
