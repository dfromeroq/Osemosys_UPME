"""Procesamiento de resultados post-solve.

Extrae TODAS las variables del modelo abstracto (`model_definition.py:331-556`)
y las deja listas para persistencia. Además calcula variables derivadas
(Dispatch, UnmetDemand, TotalCapacityAnnual, AccumulatedNewCapacity,
ProductionByTechnology, UseByTechnology).

Salida: dict con `dispatch`, `new_capacity`, `unmet_demand`, `annual_emissions`
(capas tipadas legacy para chart_service), `sol` (legacy),
`intermediate_variables` (universal: nombre de variable → lista de entradas
`{index, value}`) y `model_timings`. `VARIABLE_INDEX_NAMES` describe cómo
interpretar cada índice para mapearlo a columnas tipadas en BD.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable

import pandas as pd
import pyomo.environ as pyo

logger = logging.getLogger(__name__)


# ========================================================================
#  Registro de variables del modelo
# ========================================================================

# Índices (en orden) para cada Var declarada en model_definition.create_abstract_model.
# Los nombres coinciden con las dimensiones del modelo (REGION, TECHNOLOGY, FUEL, ...).
# Se usa en `_build_output_rows` para mapear cada posición a una columna tipada.
VARIABLE_INDEX_NAMES: dict[str, tuple[str, ...]] = {
    # Capacity
    "NumberOfNewTechnologyUnits": ("REGION", "TECHNOLOGY", "YEAR"),
    "NewCapacity": ("REGION", "TECHNOLOGY", "YEAR"),
    # Activity
    "RateOfActivity": ("REGION", "TIMESLICE", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"),
    # Costing
    "VariableOperatingCost": ("REGION", "TECHNOLOGY", "TIMESLICE", "YEAR"),
    "SalvageValue": ("REGION", "TECHNOLOGY", "YEAR"),
    "DiscountedSalvageValue": ("REGION", "TECHNOLOGY", "YEAR"),
    "OperatingCost": ("REGION", "TECHNOLOGY", "YEAR"),
    "CapitalInvestment": ("REGION", "TECHNOLOGY", "YEAR"),
    "DiscountedCapitalInvestment": ("REGION", "TECHNOLOGY", "YEAR"),
    "DiscountedOperatingCost": ("REGION", "TECHNOLOGY", "YEAR"),
    "AnnualVariableOperatingCost": ("REGION", "TECHNOLOGY", "YEAR"),
    "AnnualFixedOperatingCost": ("REGION", "TECHNOLOGY", "YEAR"),
    "TotalDiscountedCostByTechnology": ("REGION", "TECHNOLOGY", "YEAR"),
    "TotalDiscountedCost": ("REGION", "YEAR"),
    # Reserve Margin
    "TotalCapacityInReserveMargin": ("REGION", "YEAR"),
    "DemandNeedingReserveMargin": ("REGION", "TIMESLICE", "YEAR"),
    # RE Targets
    "TotalREProductionAnnual": ("REGION", "YEAR"),
    "RETotalProductionOfTargetFuelAnnual": ("REGION", "YEAR"),
    "TotalTechnologyModelPeriodActivity": ("REGION", "TECHNOLOGY"),
    # Emissions
    "AnnualTechnologyEmissionByMode": (
        "REGION", "TECHNOLOGY", "EMISSION", "MODE_OF_OPERATION", "YEAR",
    ),
    "AnnualTechnologyEmission": ("REGION", "TECHNOLOGY", "EMISSION", "YEAR"),
    "AnnualTechnologyEmissionPenaltyByEmission": (
        "REGION", "TECHNOLOGY", "EMISSION", "YEAR",
    ),
    "AnnualTechnologyEmissionsPenalty": ("REGION", "TECHNOLOGY", "YEAR"),
    "DiscountedTechnologyEmissionsPenalty": ("REGION", "TECHNOLOGY", "YEAR"),
    "AnnualEmissions": ("REGION", "EMISSION", "YEAR"),
    "ModelPeriodEmissions": ("REGION", "EMISSION"),
    # Storage
    "NewStorageCapacity": ("REGION", "STORAGE", "YEAR"),
    "SalvageValueStorage": ("REGION", "STORAGE", "YEAR"),
    "StorageLevelYearStart": ("REGION", "STORAGE", "YEAR"),
    "StorageLevelYearFinish": ("REGION", "STORAGE", "YEAR"),
    "RateOfStorageCharge": (
        "REGION", "STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET", "YEAR",
    ),
    "RateOfStorageDischarge": (
        "REGION", "STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET", "YEAR",
    ),
    "NetChargeWithinYear": (
        "REGION", "STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET", "YEAR",
    ),
    "NetChargeWithinDay": (
        "REGION", "STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET", "YEAR",
    ),
    "StorageLevelSeasonStart": ("REGION", "STORAGE", "SEASON", "YEAR"),
    "StorageLevelDayTypeStart": (
        "REGION", "STORAGE", "SEASON", "DAYTYPE", "YEAR",
    ),
    "StorageLevelDayTypeFinish": (
        "REGION", "STORAGE", "SEASON", "DAYTYPE", "YEAR",
    ),
    "StorageLowerLimit": ("REGION", "STORAGE", "YEAR"),
    "StorageUpperLimit": ("REGION", "STORAGE", "YEAR"),
    "AccumulatedNewStorageCapacity": ("REGION", "STORAGE", "YEAR"),
    "CapitalInvestmentStorage": ("REGION", "STORAGE", "YEAR"),
    "DiscountedCapitalInvestmentStorage": ("REGION", "STORAGE", "YEAR"),
    "DiscountedSalvageValueStorage": ("REGION", "STORAGE", "YEAR"),
    "TotalDiscountedStorageCost": ("REGION", "STORAGE", "YEAR"),
    # Disposal / Recovery
    "DisposalCost": ("REGION", "TECHNOLOGY", "YEAR"),
    "DiscountedDisposalCost": ("REGION", "TECHNOLOGY", "YEAR"),
    "RecoveryValue": ("REGION", "TECHNOLOGY", "YEAR"),
    "DiscountedRecoveryValue": ("REGION", "TECHNOLOGY", "YEAR"),
    # Derivadas (no son Pyomo Var pero el pipeline las trata igual)
    "TotalCapacityAnnual": ("REGION", "TECHNOLOGY", "YEAR"),
    "AccumulatedNewCapacity": ("REGION", "TECHNOLOGY", "YEAR"),
    "ProductionByTechnology": ("REGION", "TECHNOLOGY", "FUEL", "TIMESLICE", "YEAR"),
    "UseByTechnology": ("REGION", "TECHNOLOGY", "FUEL", "TIMESLICE", "YEAR"),
    "RateOfProductionByTechnology": (
        "REGION", "TECHNOLOGY", "FUEL", "TIMESLICE", "YEAR",
    ),
    "RateOfUseByTechnology": ("REGION", "TECHNOLOGY", "FUEL", "TIMESLICE", "YEAR"),
}

# Variables que ya se persisten con columnas tipadas dedicadas (pipeline las
# toma de los bloques `dispatch`, `new_capacity`, `unmet_demand`,
# `annual_emissions` del dict de resultados). No se repiten en
# `intermediate_variables` para evitar duplicación.
_LEGACY_TYPED_VARIABLES: frozenset[str] = frozenset(
    {"Dispatch", "NewCapacity", "UnmetDemand", "AnnualEmissions"},
)

# Variables Pyomo declaradas siempre (independientes de has_storage / has_emissions).
_ALWAYS_PYOMO_VARIABLES: tuple[str, ...] = (
    "NumberOfNewTechnologyUnits",
    "RateOfActivity",
    "VariableOperatingCost",
    "SalvageValue",
    "DiscountedSalvageValue",
    "OperatingCost",
    "CapitalInvestment",
    "DiscountedCapitalInvestment",
    "DiscountedOperatingCost",
    "AnnualVariableOperatingCost",
    "AnnualFixedOperatingCost",
    "TotalDiscountedCostByTechnology",
    "TotalDiscountedCost",
    "TotalCapacityInReserveMargin",
    "DemandNeedingReserveMargin",
    "TotalREProductionAnnual",
    "RETotalProductionOfTargetFuelAnnual",
    "TotalTechnologyModelPeriodActivity",
    "DisposalCost",
    "DiscountedDisposalCost",
    "RecoveryValue",
    "DiscountedRecoveryValue",
)

# Variables Pyomo sólo si el escenario define emisiones.
_EMISSION_PYOMO_VARIABLES: tuple[str, ...] = (
    "AnnualTechnologyEmissionByMode",
    "AnnualTechnologyEmission",
    "AnnualTechnologyEmissionPenaltyByEmission",
    "AnnualTechnologyEmissionsPenalty",
    "DiscountedTechnologyEmissionsPenalty",
    "ModelPeriodEmissions",
)

# Variables Pyomo sólo si has_storage.
_STORAGE_PYOMO_VARIABLES: tuple[str, ...] = (
    "NewStorageCapacity",
    "SalvageValueStorage",
    "StorageLevelYearStart",
    "StorageLevelYearFinish",
    "RateOfStorageCharge",
    "RateOfStorageDischarge",
    "NetChargeWithinYear",
    "NetChargeWithinDay",
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
)

# Umbral de poda: valores con magnitud menor no se persisten.
_EPS = 1e-10


def _coerce_year(value) -> int | None:
    """Convierte valores de año (str/int/float) a int de forma robusta."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _coerce_number(value, default: float = 0.0) -> float:
    """Convierte un valor a float; usa default si no es convertible."""
    if value is None:
        return default
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _safe_extract(var_component) -> dict:
    """Extrae valores de un componente Pyomo (Param/Var); sustituye None por 0.0."""
    try:
        model = var_component.model()
        cache = getattr(model, "_safe_extract_cache", None)
        if cache is None:
            cache = {}
            model._safe_extract_cache = cache
        comp_name = var_component.local_name
        if comp_name in cache:
            return cache[comp_name]
    except Exception:
        cache = None
        comp_name = None

    if isinstance(var_component, pyo.Var) and hasattr(var_component, "_data"):
        raw = {}
        for k, v in var_component._data.items():
            val = v.value
            if val is not None and abs(val) >= 1e-10:
                raw[k] = val
        if cache is not None and comp_name:
            cache[comp_name] = raw
        return raw

    raw = var_component.extract_values()
    res = {k: (v if v is not None else 0.0) for k, v in raw.items()}
    
    if cache is not None and comp_name:
        cache[comp_name] = res
    return res


def _variable_to_dataframe(variable, index_names: list[str] | None = None) -> pd.DataFrame:
    """Convierte variable Pyomo indexada o dict a DataFrame.

    Si variable es dict, las claves son tuplas (índices) y el valor el número.
    """
    rows = []

    if isinstance(variable, dict):
        first_key = next(iter(variable))
        n_indices = len(first_key) if isinstance(first_key, tuple) else 1
        if index_names is None:
            columns = [f"IDX{i+1}" for i in range(n_indices)] + ["VALUE"]
        else:
            columns = list(index_names) + ["VALUE"]

        for k, v in variable.items():
            if n_indices == 1:
                rows.append((k, v))
            else:
                rows.append((*k, v))
    else:
        first_idx = next(iter(variable))
        n_indices = len(first_idx) if isinstance(first_idx, tuple) else 1
        if index_names is None:
            columns = [f"IDX{i+1}" for i in range(n_indices)] + ["VALUE"]
        else:
            columns = list(index_names) + ["VALUE"]

        for idx in variable:
            v = variable[idx].value
            if n_indices == 1:
                rows.append((idx, v))
            else:
                rows.append((*idx, v))

    return pd.DataFrame(rows, columns=columns)


def _index_as_list(key, n_expected: int) -> list:
    """Normaliza la clave de Pyomo a lista. Convierte años a int.

    Los índices con nombre de dimensión `YEAR` se normalizan a int con
    ``_coerce_year`` para consistencia con el resto del pipeline.
    """
    if isinstance(key, tuple):
        parts = list(key)
    else:
        parts = [key]
    if len(parts) != n_expected:
        # Índice inesperado — devolvemos tal cual; el consumidor decide.
        return parts
    return parts


# ========================================================================
#  Extracción de resultados principales
# ========================================================================

def _extract_dispatch(
    instance: pyo.ConcreteModel,
    region_id_by_name: dict[str, int],
    technology_id_by_name: dict[str, int],
    timeslice_id_by_name: dict[str, int] | None = None,
) -> list[dict]:
    """Dispatch por (región, timeslice, tecnología, año).

    Usa RateOfActivity × YearSplit para actividad por timeslice. Preserva la
    dimensión TIMESLICE en la salida (una fila por (r, l, t, y) con dispatch
    distinto de cero); el frontend agrega por año cuando corresponde.
    Asigna coste variable medio y el fuel 'principal' (OutputActivityRatio > 0)
    por (r, t, y).
    """
    roa_raw = _safe_extract(instance.RateOfActivity)

    ys_param = getattr(instance, "YearSplit", None)
    ys_data: dict = {}
    if ys_param is not None:
        ys_data = _safe_extract(ys_param) if hasattr(ys_param, "extract_values") else {}

    oar_param = getattr(instance, "OutputActivityRatio", None)
    oar_data: dict = {}
    if oar_param is not None:
        oar_data = _safe_extract(oar_param) if hasattr(oar_param, "extract_values") else {}

    vc_param = getattr(instance, "VariableCost", None)
    vc_data: dict = {}
    if vc_param is not None:
        vc_data = _safe_extract(vc_param) if hasattr(vc_param, "extract_values") else {}

    activity_by_rlty: dict[tuple, float] = defaultdict(float)
    cost_by_rlty: dict[tuple, float] = defaultdict(float)

    for (r, l, t, mo, y), roa in roa_raw.items():
        if abs(roa) < _EPS:
            continue
        ys = ys_data.get((l, y), 1.0) if ys_data else 1.0
        act = roa * ys
        activity_by_rlty[(r, l, t, y)] += act
        vc = vc_data.get((r, t, mo, y), 0.0) if vc_data else 0.0
        cost_by_rlty[(r, l, t, y)] += act * vc

    best_fuel: dict[tuple, str] = {}
    for (r, t, f, mo, y), oar_val in oar_data.items():
        if oar_val > 0:
            key = (r, t, y)
            if key not in best_fuel:
                best_fuel[key] = f

    ts_lookup = timeslice_id_by_name or {}
    results = []
    for (r, l, t, y), total_act in activity_by_rlty.items():
        if total_act < _EPS:
            continue
        avg_cost = cost_by_rlty[(r, l, t, y)] / total_act if total_act > 0 else 0.0
        results.append({
            "region_id": region_id_by_name.get(r, -1),
            "year": _coerce_year(y),
            "technology_name": t,
            "technology_id": technology_id_by_name.get(t, -1),
            "fuel_name": best_fuel.get((r, t, y)),
            "timeslice_name": l,
            "timeslice_id": ts_lookup.get(l),
            "dispatch": total_act,
            "cost": avg_cost,
        })
    return results


def _extract_new_capacity(
    instance: pyo.ConcreteModel,
    region_id_by_name: dict[str, int],
    technology_id_by_name: dict[str, int],
) -> list[dict]:
    """Lista de dicts con region_id, technology_id, year, new_capacity, technology_name."""
    nc_raw = _safe_extract(instance.NewCapacity)
    return [
        {
            "region_id": region_id_by_name.get(k[0], -1),
            "technology_id": technology_id_by_name.get(k[1], -1),
            "year": _coerce_year(k[2]),
            "new_capacity": v,
            "technology_name": k[1],
        }
        for k, v in nc_raw.items()
    ]


def _index_ratio_by_rtmoy(
    ratio_data: dict[tuple, float],
) -> dict[tuple, list[tuple[str, float]]]:
    """Pre-indexa OAR/IAR: {(r,t,mo,y) -> [(fuel, value), ...]} para lookup O(1)."""
    idx: dict[tuple, list[tuple[str, float]]] = defaultdict(list)
    for (r, t, f, mo, y), val in ratio_data.items():
        if val > 0:
            idx[(r, t, mo, y)].append((f, val))
    return idx


def _compute_unmet_demand(
    instance: pyo.ConcreteModel,
    region_id_by_name: dict[str, int],
) -> list[dict]:
    """Demanda insatisfecha = max(0, Demand - Production) por (r, fuel, y).

    Producción por fuel viene de RateOfActivity × OutputActivityRatio × YearSplit;
    demanda de Demand (param). Se agrega por (r, y) para el listado final.
    """
    roa_raw = _safe_extract(instance.RateOfActivity)

    ys_param = getattr(instance, "YearSplit", None)
    ys_data = _safe_extract(ys_param) if ys_param and hasattr(ys_param, "extract_values") else {}

    oar_param = getattr(instance, "OutputActivityRatio", None)
    oar_data = _safe_extract(oar_param) if oar_param and hasattr(oar_param, "extract_values") else {}
    oar_idx = _index_ratio_by_rtmoy(oar_data)

    demand_param = getattr(instance, "Demand", None)
    demand_data = _safe_extract(demand_param) if demand_param and hasattr(demand_param, "extract_values") else {}

    prod_by_rfy: dict[tuple, float] = defaultdict(float)
    for (r, l, t, mo, y), roa in roa_raw.items():
        if abs(roa) < _EPS:
            continue
        ys = ys_data.get((l, y), 1.0)
        for f, oar_val in oar_idx.get((r, t, mo, y), ()):
            prod_by_rfy[(r, f, y)] += roa * oar_val * ys

    demand_by_rfy: dict[tuple, float] = defaultdict(float)
    for (r, l, f, y), dval in demand_data.items():
        demand_by_rfy[(r, f, y)] += dval

    unmet_by_ry: dict[tuple, float] = defaultdict(float)
    for (r, f, y), total_demand in demand_by_rfy.items():
        total_prod = prod_by_rfy.get((r, f, y), 0.0)
        gap = max(0.0, total_demand - total_prod)
        unmet_by_ry[(r, y)] += gap

    return [
        {
            "region_id": region_id_by_name.get(r, -1),
            "year": _coerce_year(y),
            "unmet_demand": v,
        }
        for (r, y), v in sorted(unmet_by_ry.items())
    ]


def _extract_annual_emissions(
    instance: pyo.ConcreteModel,
    region_id_by_name: dict[str, int],
    regions: list,
    years: list,
    emissions: list,
) -> list[dict]:
    """Extrae AnnualEmissions por (región, año); si no hay emisiones, devuelve 0.0 por (r,y)."""
    if not emissions:
        return [
            {
                "region_id": region_id_by_name.get(r, -1),
                "year": _coerce_year(y),
                "annual_emissions": 0.0,
            }
            for r in regions for y in years
        ]

    ae_raw = _safe_extract(instance.AnnualEmissions)
    totals: dict[tuple, float] = defaultdict(float)
    for (r, e, y), v in ae_raw.items():
        totals[(r, y)] += v

    return [
        {
            "region_id": region_id_by_name.get(r, -1),
            "year": _coerce_year(y),
            "annual_emissions": totals.get((r, y), 0.0),
        }
        for r in regions for y in years
    ]


# ========================================================================
#  Variables intermedias
# ========================================================================

def _extract_pyomo_variable(
    instance: pyo.ConcreteModel,
    var_name: str,
) -> list[dict]:
    """Extrae una Var Pyomo arbitraria al formato canónico `{index, value}`.

    Aplica poda por |value| > _EPS. La longitud del índice se deduce del
    registry ``VARIABLE_INDEX_NAMES``; si no hay registro, se usa la tupla
    natural.
    """
    pyo_var = getattr(instance, var_name, None)
    if pyo_var is None:
        return []
    raw = _safe_extract(pyo_var)
    expected = VARIABLE_INDEX_NAMES.get(var_name)
    n_expected = len(expected) if expected else 0
    entries: list[dict] = []
    for key, value in raw.items():
        if abs(value) < _EPS:
            continue
        idx = _index_as_list(key, n_expected) if n_expected else (
            list(key) if isinstance(key, tuple) else [key]
        )
        # Normalizar año a int cuando el registry indica posición YEAR.
        if expected:
            idx = [
                _coerce_year(v) if name == "YEAR" else v
                for v, name in zip(idx, expected)
            ]
        entries.append({"index": idx, "value": float(value)})
    return entries


def _compute_intermediate_variables(
    instance: pyo.ConcreteModel,
    regions: list,
    technologies: list,
    years: list,
    emissions: list,
    has_storage: bool,
) -> dict[str, list]:
    """Registry-driven extraction of ALL model variables except the 4 typed ones.

    Para cada variable en ``VARIABLE_INDEX_NAMES`` con contraparte Pyomo se
    extrae tal cual. Adicionalmente se computan las derivadas
    ``TotalCapacityAnnual``, ``AccumulatedNewCapacity``,
    ``ProductionByTechnology``, ``UseByTechnology`` y sus alias
    ``RateOfProductionByTechnology`` / ``RateOfUseByTechnology``.
    """
    out: dict[str, list] = {}

    # ---- 1. Variables Pyomo (siempre) --------------------------------------
    for var_name in _ALWAYS_PYOMO_VARIABLES:
        entries = _extract_pyomo_variable(instance, var_name)
        if entries:
            out[var_name] = entries

    # ---- 2. Variables Pyomo condicionales: emisiones -----------------------
    if emissions:
        for var_name in _EMISSION_PYOMO_VARIABLES:
            entries = _extract_pyomo_variable(instance, var_name)
            if entries:
                out[var_name] = entries

    # ---- 3. Variables Pyomo condicionales: storage -------------------------
    if has_storage:
        for var_name in _STORAGE_PYOMO_VARIABLES:
            entries = _extract_pyomo_variable(instance, var_name)
            if entries:
                out[var_name] = entries

    # ---- 4. Derivadas ------------------------------------------------------
    nc_raw = _safe_extract(instance.NewCapacity)

    ol_param = getattr(instance, "OperationalLife", None)
    ol_data = _safe_extract(ol_param) if ol_param and hasattr(ol_param, "extract_values") else {}

    rc_param = getattr(instance, "ResidualCapacity", None)
    rc_data = _safe_extract(rc_param) if rc_param and hasattr(rc_param, "extract_values") else {}

    year_pairs = []
    for y in years:
        y_num = _coerce_year(y)
        if y_num is None:
            continue
        year_pairs.append((y, int(y_num)))

    tca_entries: list[dict] = []
    anc_entries: list[dict] = []
    for r in regions:
        for t in technologies:
            ol = int(_coerce_number(ol_data.get((r, t), 1), default=1.0))
            if ol <= 0:
                ol = 1
            for y, y_num in year_pairs:
                acc = sum(
                    nc_raw.get((r, t, yy), 0.0)
                    for yy, yy_num in year_pairs
                    if 0 <= (int(y_num) - int(yy_num)) < ol
                )
                res = rc_data.get((r, t, y), 0.0)
                total = acc + res
                if abs(total) >= _EPS:
                    tca_entries.append({"index": [r, t, y_num], "value": float(total)})
                if abs(acc) >= _EPS:
                    anc_entries.append({"index": [r, t, y_num], "value": float(acc)})
    if tca_entries:
        out["TotalCapacityAnnual"] = tca_entries
    if anc_entries:
        out["AccumulatedNewCapacity"] = anc_entries

    # ProductionByTechnology / UseByTechnology (por timeslice).
    roa_raw = _safe_extract(instance.RateOfActivity)

    ys_param = getattr(instance, "YearSplit", None)
    ys_data = _safe_extract(ys_param) if ys_param and hasattr(ys_param, "extract_values") else {}

    oar_param = getattr(instance, "OutputActivityRatio", None)
    oar_data = _safe_extract(oar_param) if oar_param and hasattr(oar_param, "extract_values") else {}
    oar_idx = _index_ratio_by_rtmoy(oar_data)

    iar_param = getattr(instance, "InputActivityRatio", None)
    iar_data = _safe_extract(iar_param) if iar_param and hasattr(iar_param, "extract_values") else {}
    iar_idx = _index_ratio_by_rtmoy(iar_data)

    prod_by: dict[tuple, float] = defaultdict(float)
    use_by: dict[tuple, float] = defaultdict(float)
    for (r, l, t, mo, y), roa in roa_raw.items():
        if abs(roa) < _EPS:
            continue
        ys = ys_data.get((l, y), 1.0)
        for f, oar_val in oar_idx.get((r, t, mo, y), ()):
            prod_by[(r, t, f, l, y)] += roa * oar_val * ys
        for f, iar_val in iar_idx.get((r, t, mo, y), ()):
            use_by[(r, t, f, l, y)] += roa * iar_val * ys

    prod_entries = [
        {"index": [r, t, f, l, _coerce_year(y)], "value": float(v)}
        for (r, t, f, l, y), v in prod_by.items() if abs(v) >= _EPS
    ]
    use_entries = [
        {"index": [r, t, f, l, _coerce_year(y)], "value": float(v)}
        for (r, t, f, l, y), v in use_by.items() if abs(v) >= _EPS
    ]
    if prod_entries:
        out["ProductionByTechnology"] = prod_entries
        out["RateOfProductionByTechnology"] = prod_entries
    if use_entries:
        out["UseByTechnology"] = use_entries
        out["RateOfUseByTechnology"] = use_entries

    return out


# ========================================================================
#  Pipeline principal de resultados
# ========================================================================

def process_results(
    instance: pyo.ConcreteModel,
    solver_result: dict,
    *,
    regions: list,
    technologies: list,
    years: list,
    emissions: list,
    has_storage: bool,
    region_id_by_name: dict[str, int],
    technology_id_by_name: dict[str, int],
    region_name_by_id: dict[int, str],
    fuel_id_by_name: dict[str, int] | None = None,
    emission_id_by_name: dict[str, int] | None = None,
    timeslice_id_by_name: dict[str, int] | None = None,
    mode_of_operation_id_by_name: dict[str, int] | None = None,
    season_id_by_name: dict[str, int] | None = None,
    daytype_id_by_name: dict[str, int] | None = None,
    dailytimebracket_id_by_name: dict[str, int] | None = None,
    storage_id_by_name: dict[str, int] | None = None,
) -> dict:
    """Construye el dict de resultados compatible con el pipeline.

    Retorna la misma estructura que antes (dispatch, new_capacity,
    unmet_demand, annual_emissions, sol, intermediate_variables,
    model_timings) pero ``intermediate_variables`` contiene ahora todas las
    variables del modelo extraíbles.
    """
    from time import perf_counter
    timings: dict[str, float] = {}

    t = perf_counter()
    normalized_years = []
    for y in years:
        y_num = _coerce_year(y)
        if y_num is not None:
            normalized_years.append(y_num)

    dispatch = _extract_dispatch(
        instance,
        region_id_by_name,
        technology_id_by_name,
        timeslice_id_by_name=timeslice_id_by_name,
    )
    new_capacity = _extract_new_capacity(instance, region_id_by_name, technology_id_by_name)
    unmet = _compute_unmet_demand(instance, region_id_by_name)
    annual_emissions = _extract_annual_emissions(
        instance, region_id_by_name, regions, normalized_years, emissions,
    )
    timings["extract_results_seconds"] = perf_counter() - t

    for row in dispatch:
        row["region_name"] = region_name_by_id.get(row["region_id"], "")
    for row in new_capacity:
        row["region_name"] = region_name_by_id.get(row["region_id"], "")
    for row in unmet:
        row["region_name"] = region_name_by_id.get(row["region_id"], "")
    for row in annual_emissions:
        row["region_name"] = region_name_by_id.get(row["region_id"], "")

    t = perf_counter()
    total_dispatch = sum(row["dispatch"] for row in dispatch)
    total_unmet = sum(row["unmet_demand"] for row in unmet)

    sad_param = getattr(instance, "SpecifiedAnnualDemand", None)
    sad_data = _safe_extract(sad_param) if sad_param and hasattr(sad_param, "extract_values") else {}
    aad_param = getattr(instance, "AccumulatedAnnualDemand", None)
    aad_data = _safe_extract(aad_param) if aad_param and hasattr(aad_param, "extract_values") else {}
    total_demand = sum(sad_data.values()) + sum(aad_data.values())

    coverage_ratio = 1.0
    if total_demand > 0:
        coverage_ratio = max(0.0, min(1.0, (total_demand - total_unmet) / total_demand))

    sol: dict[str, list] = {
        "RateOfActivity": [],
        "NewCapacity": [],
        "UnmetDemand": [],
        "AnnualEmissions": [],
    }
    for row in dispatch:
        sol["RateOfActivity"].append({
            "index": [
                region_name_by_id.get(row["region_id"], ""),
                row.get("technology_name", ""),
                row.get("fuel_name", ""),
                row["year"],
            ],
            "value": row["dispatch"],
        })
    for row in new_capacity:
        sol["NewCapacity"].append({
            "index": [
                region_name_by_id.get(row["region_id"], ""),
                row.get("technology_name", ""),
                row["year"],
            ],
            "value": row["new_capacity"],
        })
    for row in unmet:
        sol["UnmetDemand"].append({
            "index": [region_name_by_id.get(row["region_id"], ""), row["year"]],
            "value": row["unmet_demand"],
        })
    for row in annual_emissions:
        sol["AnnualEmissions"].append({
            "index": [region_name_by_id.get(row["region_id"], ""), row["year"]],
            "value": row["annual_emissions"],
        })

    intermediate_variables = _compute_intermediate_variables(
        instance, regions, technologies, normalized_years, emissions, has_storage,
    )
    timings["intermediate_vars_seconds"] = perf_counter() - t

    # Lookups usados por el pipeline para persistir columnas tipadas de
    # intermediate_variables. Se incluyen aquí para evitar que el pipeline
    # tenga que volver a cargar catálogos. Todos son dict[str, int].
    lookups = {
        "REGION": dict(region_id_by_name),
        "TECHNOLOGY": dict(technology_id_by_name),
        "FUEL": dict(fuel_id_by_name or {}),
        "EMISSION": dict(emission_id_by_name or {}),
        "TIMESLICE": dict(timeslice_id_by_name or {}),
        "MODE_OF_OPERATION": dict(mode_of_operation_id_by_name or {}),
        "SEASON": dict(season_id_by_name or {}),
        "DAYTYPE": dict(daytype_id_by_name or {}),
        "DAILYTIMEBRACKET": dict(dailytimebracket_id_by_name or {}),
        "STORAGE": dict(storage_id_by_name or {}),
    }

    result = {
        "objective_value": solver_result["objective_value"],
        "solver_name": solver_result["solver_name"],
        "solver_status": solver_result["solver_status"],
        "coverage_ratio": coverage_ratio,
        "reserve_margin_dual": solver_result.get("reserve_margin_dual"),
        "total_demand": total_demand,
        "total_dispatch": total_dispatch,
        "total_unmet": total_unmet,
        "dispatch": dispatch,
        "unmet_demand": unmet,
        "new_capacity": new_capacity,
        "annual_emissions": annual_emissions,
        "sol": sol,
        "intermediate_variables": intermediate_variables,
        "model_timings": timings,
        "dimension_lookups": lookups,
    }
    if solver_result.get("infeasibility_diagnostics"):
        result["infeasibility_diagnostics"] = solver_result["infeasibility_diagnostics"]
    return result
