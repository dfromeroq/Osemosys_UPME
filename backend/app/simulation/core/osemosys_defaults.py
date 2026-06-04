"""Valores por defecto canónicos de parámetros OSeMOSYS.

Única fuente de verdad para los defaults del modelo. Replica los defaults
declarados en ``Param(..., default=...)`` dentro de
:mod:`app.simulation.core.model_definition`.

Este módulo es **puro** (sin dependencias pesadas) a propósito, para poder
importarse tanto desde el servicio de importación oficial como desde el
análisis de infactibilidad sin arrastrar cadenas de imports costosos
(openpyxl, sqlalchemy, etc.).
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar, Token

# Claves normalizadas (minúsculas + solo alfanuméricos). Usar siempre el
# mismo esquema de normalización al consultar.
OSEMOSYS_PARAM_DEFAULTS: dict[str, float] = {
    "yearsplit": 0.0,
    "discountrate": 0.05,
    "discountrateidv": 0.05,
    "operationallife": 1.0,
    "depreciationmethod": 1.0,
    "accumulatedannualdemand": 0.0,
    "specifiedannualdemand": 0.0,
    "specifieddemandprofile": 0.0,
    "capacitytoactivityunit": 1.0,
    "capacityfactor": 1.0,
    "availabilityfactor": 1.0,
    "residualcapacity": 0.0,
    "inputactivityratio": 0.0,
    "outputactivityratio": 0.0,
    "capitalcost": 0.000001,
    "variablecost": 0.000001,
    "fixedcost": 0.0,
    "capacityofonetechnologyunit": 0.0,
    "totalannualmaxcapacity": 9999999.0,
    "totalannualmincapacity": 0.0,
    "totalannualmaxcapacityinvestment": 9999999.0,
    "totalannualmincapacityinvestment": 0.0,
    "totaltechnologyannualactivityupperlimit": 9999999.0,
    "totaltechnologyannualactivitylowerlimit": 0.0,
    "totaltechnologymodelperiodactivityupperlimit": 9999999.0,
    "totaltechnologymodelperiodactivitylowerlimit": 0.0,
    "reservemargintagtechnology": 0.0,
    "reservemargintagfuel": 0.0,
    "reservemargin": 1.0,
    "retagtechnology": 0.0,
    "retagfuel": 0.0,
    "reminproductiontarget": 0.0,
    "emissionactivityratio": 0.0,
    "emissionspenalty": 0.0,
    "annualexogenousemission": 0.0,
    "annualemissionlimit": 9999999.0,
    "modelperiodexogenousemission": 0.0,
    "modelperiodemissionlimit": 9999999.0,
    "inputtonewcapacityratio": 0.0,
    "inputtototalcapacityratio": 0.0,
    "technologyactivitybymodelowerlimit": 0.0,
    "technologyactivitybymodeupperlimit": 0.0,
    "technologyactivitydecreasebymodelimit": 0.0,
    "technologyactivityincreasebymodelimit": 0.0,
    "emissiontoactivitychangeratio": 0.0,
    "udcmultipliertotalcapacity": 0.0,
    "udcmultipliernewcapacity": 0.0,
    "udcmultiplieractivity": 0.0,
    "udcconstant": 0.0,
    "udctag": 2.0,
    "daysplit": 0.00137,
    "conversionls": 0.0,
    "conversionld": 0.0,
    "conversionlh": 0.0,
    "daysindaytype": 7.0,
    "technologytostorage": 0.0,
    "technologyfromstorage": 0.0,
    "storagelevelstart": 0.0000001,
    "storagemaxchargerate": 9999999.0,
    "storagemaxdischargerate": 9999999.0,
    "minstoragecharge": 0.0,
    "operationallifestorage": 0.0,
    "capitalcoststorage": 0.0,
    "residualstoragecapacity": 0.0,
    "disposalcostpercapacity": 0.0,
    "recoveryvaluepercapacity": 0.0,
}


def _normalize_param_name(name: str | None) -> str:
    """Normaliza un nombre de parámetro al esquema de claves de ``OSEMOSYS_PARAM_DEFAULTS``.

    Regla: minúsculas + solo alfanuméricos (elimina espacios, guiones bajos,
    cualquier caracter no alfanumérico).
    """
    if not name:
        return ""
    return "".join(ch for ch in name.strip().lower() if ch.isalnum())


_defaults_context: ContextVar[dict[str, float] | None] = ContextVar(
    "osemosys_runtime_defaults",
    default=None,
)


def set_defaults_context(defaults_map: Mapping[str, float] | None) -> Token:
    """Fija el mapa de defaults de la corrida actual (p. ej. versión del job)."""
    if defaults_map is None:
        return _defaults_context.set(None)
    return _defaults_context.set({str(k): float(v) for k, v in defaults_map.items()})


def reset_defaults_context(token: Token) -> None:
    _defaults_context.reset(token)


def get_param_default(
    name: str | None,
    *,
    defaults_map: Mapping[str, float] | None = None,
) -> float:
    """Devuelve el default OSeMOSYS por nombre (runtime, contexto o fallback código)."""
    key = _normalize_param_name(name)
    if defaults_map is not None:
        return float(defaults_map.get(key, OSEMOSYS_PARAM_DEFAULTS.get(key, 0.0)))
    ctx = _defaults_context.get()
    if ctx is not None:
        return float(ctx.get(key, OSEMOSYS_PARAM_DEFAULTS.get(key, 0.0)))
    return OSEMOSYS_PARAM_DEFAULTS.get(key, 0.0)


def has_known_default(name: str | None) -> bool:
    """``True`` si el parámetro está en el catálogo de defaults (distingue 0 real de 0 fallback)."""
    return _normalize_param_name(name) in OSEMOSYS_PARAM_DEFAULTS
