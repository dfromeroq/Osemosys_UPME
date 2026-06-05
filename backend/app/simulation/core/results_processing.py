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
import os
import threading
import tracemalloc
from collections import defaultdict
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, TypeVar

import numpy as np
import pandas as pd
import pyomo.environ as pyo

logger = logging.getLogger(__name__)

T = TypeVar("T")

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

_ROA_COLUMNS = ("R", "L", "T", "MO", "Y", "ROA")

_TYPED_SOLUTION_VARS: frozenset[str] = frozenset({"NewCapacity", "AnnualEmissions"})

_safe_extract_cache_lock = threading.Lock()


def _profile_enabled() -> bool:
    return os.getenv("OSEMOSYS_PROFILE_RESULTS", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _parallel_enabled() -> bool:
    flag = os.getenv("OSEMOSYS_PARALLEL_RESULTS", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def _resolve_parallel_workers(default: int = 4) -> int:
    env = os.getenv("OSEMOSYS_PARALLEL_WORKERS", "").strip()
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    cpu = os.cpu_count() or default
    return max(1, min(default, max(1, cpu // 4)))


class _ProfileCollector:
    """Acumula tiempos y conteos cuando OSEMOSYS_PROFILE_RESULTS=1."""

    def __init__(self) -> None:
        self.timings: dict[str, float] = {}
        self.counts: dict[str, int] = {}
        self._active = _profile_enabled()
        self._mem_start: int | None = None

    def start_memory(self) -> None:
        if not self._active:
            return
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        self._mem_start = tracemalloc.get_traced_memory()[0]

    def record_memory_peak(self, label: str = "peak_memory_mb") -> None:
        if not self._active or self._mem_start is None:
            return
        current, peak = tracemalloc.get_traced_memory()
        self.timings[label] = round(peak / (1024 * 1024), 3)
        self.timings["delta_memory_mb"] = round((current - self._mem_start) / (1024 * 1024), 3)

    def time_block(self, name: str) -> "_ProfileTimer":
        return _ProfileTimer(self, name)

    def set_count(self, name: str, value: int) -> None:
        if self._active:
            self.counts[name] = value

    def log_summary(self) -> None:
        if not self._active:
            return
        parts = [f"{k}={v:.4f}s" for k, v in sorted(self.timings.items())]
        if self.counts:
            parts.extend(f"{k}={v}" for k, v in sorted(self.counts.items()))
        logger.info("results_processing profile: %s", ", ".join(parts))


class _ProfileTimer:
    def __init__(self, collector: _ProfileCollector, name: str) -> None:
        self._collector = collector
        self._name = name
        self._t0 = 0.0

    def __enter__(self) -> "_ProfileTimer":
        self._t0 = perf_counter()
        return self

    def __exit__(self, *_args: object) -> None:
        if self._collector._active:
            self._collector.timings[self._name] = (
                self._collector.timings.get(self._name, 0.0) + perf_counter() - self._t0
            )


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


def _safe_extract(var_component, *, use_cache: bool = True) -> dict:
    """Extrae valores de un componente Pyomo (Param/Var); sustituye None por 0.0."""
    cache = None
    comp_name = None
    if use_cache:
        try:
            model = var_component.model()
            cache = getattr(model, "_safe_extract_cache", None)
            if cache is None:
                cache = {}
                model._safe_extract_cache = cache
            comp_name = var_component.local_name
            with _safe_extract_cache_lock:
                if comp_name in cache:
                    return cache[comp_name]
        except Exception:
            cache = None
            comp_name = None

    if isinstance(var_component, pyo.Var) and hasattr(var_component, "_data"):
        try:
            raw = {
                k: vv
                for k, v in var_component._data.items()
                if (vv := v._value) is not None and abs(vv) >= _EPS
            }
        except AttributeError:
            raw = {}
            for k, v in var_component._data.items():
                val = v.value
                if val is not None and abs(val) >= _EPS:
                    raw[k] = val
        if cache is not None and comp_name:
            with _safe_extract_cache_lock:
                cache[comp_name] = raw
        return raw

    raw = var_component.extract_values()
    res = {k: (v if v is not None else 0.0) for k, v in raw.items()}

    if cache is not None and comp_name:
        with _safe_extract_cache_lock:
            cache[comp_name] = res
    return res


def _safe_extract_param(instance: pyo.ConcreteModel, param_name: str) -> dict:
    """Extrae un Param del modelo si existe."""
    param = getattr(instance, param_name, None)
    if param is None or not hasattr(param, "extract_values"):
        return {}
    return _safe_extract(param)


# Legacy helper conservado comentado para notebooks/debug futuro.
# No se invoca en el pipeline productivo.
#
# def _variable_to_dataframe(variable, index_names: list[str] | None = None) -> pd.DataFrame:
#     """Convierte variable Pyomo indexada o dict a DataFrame."""
#     rows = []
#     if isinstance(variable, dict):
#         first_key = next(iter(variable))
#         n_indices = len(first_key) if isinstance(first_key, tuple) else 1
#         if index_names is None:
#             columns = [f"IDX{i+1}" for i in range(n_indices)] + ["VALUE"]
#         else:
#             columns = list(index_names) + ["VALUE"]
#         for k, v in variable.items():
#             if n_indices == 1:
#                 rows.append((k, v))
#             else:
#                 rows.append((*k, v))
#     else:
#         first_idx = next(iter(variable))
#         n_indices = len(first_idx) if isinstance(first_idx, tuple) else 1
#         if index_names is None:
#             columns = [f"IDX{i+1}" for i in range(n_indices)] + ["VALUE"]
#         else:
#             columns = list(index_names) + ["VALUE"]
#         for idx in variable:
#             v = variable[idx].value
#             if n_indices == 1:
#                 rows.append((idx, v))
#             else:
#                 rows.append((*idx, v))
#     return pd.DataFrame(rows, columns=columns)


def _index_as_list(key, n_expected: int) -> list:
    """Normaliza la clave de Pyomo a lista."""
    if isinstance(key, tuple):
        parts = list(key)
    else:
        parts = [key]
    if len(parts) != n_expected:
        return parts
    return parts


def _index_ratio_by_rtmoy(
    ratio_data: dict[tuple, float],
) -> dict[tuple, list[tuple[str, float]]]:
    """Pre-indexa OAR/IAR: {(r,t,mo,y) -> [(fuel, value), ...]} para lookup O(1)."""
    idx: dict[tuple, list[tuple[str, float]]] = defaultdict(list)
    for (r, t, f, mo, y), val in ratio_data.items():
        if val > 0:
            idx[(r, t, mo, y)].append((f, val))
    return idx


@dataclass
class RoaAggregates:
    """Agregados derivados de RateOfActivity en un solo pase."""

    roa_raw: dict[tuple, float] = field(default_factory=dict)
    ys_data: dict[tuple, float] = field(default_factory=dict)
    vc_data: dict[tuple, float] = field(default_factory=dict)
    oar_data: dict[tuple, float] = field(default_factory=dict)
    iar_data: dict[tuple, float] = field(default_factory=dict)
    demand_data: dict[tuple, float] = field(default_factory=dict)
    oar_idx: dict[tuple, list[tuple[str, float]]] = field(default_factory=dict)
    iar_idx: dict[tuple, list[tuple[str, float]]] = field(default_factory=dict)
    activity_by_rlty: dict[tuple, float] = field(default_factory=dict)
    cost_by_rlty: dict[tuple, float] = field(default_factory=dict)
    best_fuel: dict[tuple, str] = field(default_factory=dict)
    prod_by_rftly: dict[tuple, float] = field(default_factory=dict)
    use_by_rftly: dict[tuple, float] = field(default_factory=dict)
    prod_by_rfy: dict[tuple, float] = field(default_factory=dict)
    demand_by_rfy: dict[tuple, float] = field(default_factory=dict)


def _roa_dataframe(roa_raw: dict[tuple, float]) -> pd.DataFrame:
    if not roa_raw:
        return pd.DataFrame(columns=list(_ROA_COLUMNS))
    rows = [(*k, v) for k, v in roa_raw.items()]
    return pd.DataFrame(rows, columns=list(_ROA_COLUMNS))


def _ratio_dataframe(
    ratio_data: dict[tuple, float],
    value_col: str,
) -> pd.DataFrame:
    if not ratio_data:
        return pd.DataFrame(columns=["R", "T", "F", "MO", "Y", value_col])
    rows = [
        (r, t, f, mo, y, val)
        for (r, t, f, mo, y), val in ratio_data.items()
        if val > 0
    ]
    if not rows:
        return pd.DataFrame(columns=["R", "T", "F", "MO", "Y", value_col])
    return pd.DataFrame(rows, columns=["R", "T", "F", "MO", "Y", value_col])


def _precompute_roa_aggregates_loop(instance: pyo.ConcreteModel) -> RoaAggregates:
    """Fallback Python puro cuando pandas no aplica o el dataset es muy pequeño."""
    roa_raw = _safe_extract(instance.RateOfActivity)
    ys_data = _safe_extract_param(instance, "YearSplit")
    vc_data = _safe_extract_param(instance, "VariableCost")
    oar_data = _safe_extract_param(instance, "OutputActivityRatio")
    iar_data = _safe_extract_param(instance, "InputActivityRatio")
    demand_data = _safe_extract_param(instance, "Demand")
    oar_idx = _index_ratio_by_rtmoy(oar_data)
    iar_idx = _index_ratio_by_rtmoy(iar_data)

    activity_by_rlty: dict[tuple, float] = defaultdict(float)
    cost_by_rlty: dict[tuple, float] = defaultdict(float)
    prod_by_rftly: dict[tuple, float] = defaultdict(float)
    use_by_rftly: dict[tuple, float] = defaultdict(float)
    prod_by_rfy: dict[tuple, float] = defaultdict(float)

    for (r, l, t, mo, y), roa in roa_raw.items():
        if abs(roa) < _EPS:
            continue
        ys = ys_data.get((l, y), 1.0) if ys_data else 1.0
        act = roa * ys
        activity_by_rlty[(r, l, t, y)] += act
        vc = vc_data.get((r, t, mo, y), 0.0) if vc_data else 0.0
        cost_by_rlty[(r, l, t, y)] += act * vc
        for f, oar_val in oar_idx.get((r, t, mo, y), ()):
            prod = roa * oar_val * ys
            prod_by_rftly[(r, t, f, l, y)] += prod
            prod_by_rfy[(r, f, y)] += prod
        for f, iar_val in iar_idx.get((r, t, mo, y), ()):
            use_by_rftly[(r, t, f, l, y)] += roa * iar_val * ys

    best_fuel: dict[tuple, str] = {}
    for (r, t, f, mo, y), oar_val in oar_data.items():
        if oar_val > 0:
            key = (r, t, y)
            if key not in best_fuel:
                best_fuel[key] = f

    demand_by_rfy: dict[tuple, float] = defaultdict(float)
    for (r, l, f, y), dval in demand_data.items():
        demand_by_rfy[(r, f, y)] += dval

    return RoaAggregates(
        roa_raw=roa_raw,
        ys_data=ys_data,
        vc_data=vc_data,
        oar_data=oar_data,
        iar_data=iar_data,
        demand_data=demand_data,
        oar_idx=oar_idx,
        iar_idx=iar_idx,
        activity_by_rlty=dict(activity_by_rlty),
        cost_by_rlty=dict(cost_by_rlty),
        best_fuel=best_fuel,
        prod_by_rftly=dict(prod_by_rftly),
        use_by_rftly=dict(use_by_rftly),
        prod_by_rfy=dict(prod_by_rfy),
        demand_by_rfy=dict(demand_by_rfy),
    )


def _precompute_roa_aggregates_pd(instance: pyo.ConcreteModel) -> RoaAggregates:
    """Un solo pase vectorizado sobre RateOfActivity y ratios asociados."""
    roa_raw = _safe_extract(instance.RateOfActivity)
    ys_data = _safe_extract_param(instance, "YearSplit")
    vc_data = _safe_extract_param(instance, "VariableCost")
    oar_data = _safe_extract_param(instance, "OutputActivityRatio")
    iar_data = _safe_extract_param(instance, "InputActivityRatio")
    demand_data = _safe_extract_param(instance, "Demand")

    if not roa_raw:
        demand_by_rfy: dict[tuple, float] = defaultdict(float)
        for (r, l, f, y), dval in demand_data.items():
            demand_by_rfy[(r, f, y)] += dval
        return RoaAggregates(
            roa_raw=roa_raw,
            ys_data=ys_data,
            vc_data=vc_data,
            oar_data=oar_data,
            iar_data=iar_data,
            demand_data=demand_data,
            oar_idx=_index_ratio_by_rtmoy(oar_data),
            iar_idx=_index_ratio_by_rtmoy(iar_data),
            demand_by_rfy=dict(demand_by_rfy),
        )

    roa_df = _roa_dataframe(roa_raw)
    if ys_data:
        ys_df = pd.DataFrame(
            [(l, y, v) for (l, y), v in ys_data.items()],
            columns=["L", "Y", "YS"],
        )
        roa_df = roa_df.merge(ys_df, on=["L", "Y"], how="left")
        roa_df["YS"] = roa_df["YS"].fillna(1.0)
    else:
        roa_df["YS"] = 1.0

    if vc_data:
        vc_df = pd.DataFrame(
            [(r, t, mo, y, v) for (r, t, mo, y), v in vc_data.items()],
            columns=["R", "T", "MO", "Y", "VC"],
        )
        roa_df = roa_df.merge(vc_df, on=["R", "T", "MO", "Y"], how="left")
        roa_df["VC"] = roa_df["VC"].fillna(0.0)
    else:
        roa_df["VC"] = 0.0

    roa_df["ACT"] = roa_df["ROA"] * roa_df["YS"]
    roa_df["COST"] = roa_df["ACT"] * roa_df["VC"]

    act_grp = (
        roa_df.groupby(["R", "L", "T", "Y"], sort=False)[["ACT", "COST"]]
        .sum()
        .reset_index()
    )
    indexed = act_grp.set_index(["R", "L", "T", "Y"]).to_dict("index")
    activity_by_rlty = {
        k: float(v["ACT"])
        for k, v in indexed.items()
        if abs(float(v["ACT"])) >= _EPS
    }
    cost_by_rlty = {
        k: float(v["COST"])
        for k, v in indexed.items()
        if abs(float(v["ACT"])) >= _EPS
    }

    best_fuel: dict[tuple, str] = {}
    for (r, t, f, mo, y), oar_val in oar_data.items():
        if oar_val > 0:
            key = (r, t, y)
            if key not in best_fuel:
                best_fuel[key] = f

    prod_by_rftly: dict[tuple, float] = {}
    prod_by_rfy: dict[tuple, float] = {}
    oar_df = _ratio_dataframe(oar_data, "OAR")
    if not oar_df.empty:
        prod_df = roa_df.merge(oar_df, on=["R", "T", "MO", "Y"], how="inner")
        prod_df["PROD"] = prod_df["ROA"] * prod_df["YS"] * prod_df["OAR"]
        prod_rftly = (
            prod_df.groupby(["R", "T", "F", "L", "Y"], sort=False)["PROD"]
            .sum()
            .reset_index()
        )
        prod_by_rftly = {
            (r, t, f, l, y): float(v)
            for r, t, f, l, y, v in prod_rftly.itertuples(index=False, name=None)
            if abs(float(v)) >= _EPS
        }
        prod_rfy = (
            prod_df.groupby(["R", "F", "Y"], sort=False)["PROD"]
            .sum()
            .reset_index()
        )
        prod_by_rfy = {
            (r, f, y): float(v)
            for r, f, y, v in prod_rfy.itertuples(index=False, name=None)
            if abs(float(v)) >= _EPS
        }

    use_by_rftly: dict[tuple, float] = {}
    iar_df = _ratio_dataframe(iar_data, "IAR")
    if not iar_df.empty:
        use_df = roa_df.merge(iar_df, on=["R", "T", "MO", "Y"], how="inner")
        use_df["USE"] = use_df["ROA"] * use_df["YS"] * use_df["IAR"]
        use_rftly = (
            use_df.groupby(["R", "T", "F", "L", "Y"], sort=False)["USE"]
            .sum()
            .reset_index()
        )
        use_by_rftly = {
            (r, t, f, l, y): float(v)
            for r, t, f, l, y, v in use_rftly.itertuples(index=False, name=None)
            if abs(float(v)) >= _EPS
        }

    demand_by_rfy: dict[tuple, float] = defaultdict(float)
    for (r, l, f, y), dval in demand_data.items():
        demand_by_rfy[(r, f, y)] += dval

    return RoaAggregates(
        roa_raw=roa_raw,
        ys_data=ys_data,
        vc_data=vc_data,
        oar_data=oar_data,
        iar_data=iar_data,
        demand_data=demand_data,
        oar_idx=_index_ratio_by_rtmoy(oar_data),
        iar_idx=_index_ratio_by_rtmoy(iar_data),
        activity_by_rlty=activity_by_rlty,
        cost_by_rlty=cost_by_rlty,
        best_fuel=best_fuel,
        prod_by_rftly=prod_by_rftly,
        use_by_rftly=use_by_rftly,
        prod_by_rfy=dict(prod_by_rfy),
        demand_by_rfy=dict(demand_by_rfy),
    )


def _precompute_roa_aggregates(instance: pyo.ConcreteModel) -> RoaAggregates:
    """Punto de entrada: pandas para datasets no triviales, loop para casos mínimos."""
    roa_raw = _safe_extract(instance.RateOfActivity)
    if len(roa_raw) < 32:
        return _precompute_roa_aggregates_loop(instance)
    try:
        return _precompute_roa_aggregates_pd(instance)
    except Exception:
        logger.exception(
            "Fallo precompute pandas; usando fallback Python para RateOfActivity"
        )
        return _precompute_roa_aggregates_loop(instance)


def _format_dispatch_from_aggregates(
    aggregates: RoaAggregates,
    region_id_by_name: dict[str, int],
    technology_id_by_name: dict[str, int],
    timeslice_id_by_name: dict[str, int] | None = None,
) -> list[dict]:
    ts_lookup = timeslice_id_by_name or {}
    results: list[dict] = []
    for (r, l, t, y), total_act in aggregates.activity_by_rlty.items():
        if total_act < _EPS:
            continue
        avg_cost = (
            aggregates.cost_by_rlty.get((r, l, t, y), 0.0) / total_act
            if total_act > 0
            else 0.0
        )
        results.append({
            "region_id": region_id_by_name.get(r, -1),
            "year": _coerce_year(y),
            "technology_name": t,
            "technology_id": technology_id_by_name.get(t, -1),
            "fuel_name": aggregates.best_fuel.get((r, t, y)),
            "timeslice_name": l,
            "timeslice_id": ts_lookup.get(l),
            "dispatch": total_act,
            "cost": avg_cost,
        })
    return results


def _extract_dispatch(
    instance: pyo.ConcreteModel,
    region_id_by_name: dict[str, int],
    technology_id_by_name: dict[str, int],
    timeslice_id_by_name: dict[str, int] | None = None,
    aggregates: RoaAggregates | None = None,
) -> list[dict]:
    """Dispatch por (región, timeslice, tecnología, año)."""
    if aggregates is None:
        aggregates = _precompute_roa_aggregates(instance)
    return _format_dispatch_from_aggregates(
        aggregates,
        region_id_by_name,
        technology_id_by_name,
        timeslice_id_by_name=timeslice_id_by_name,
    )


def _extract_new_capacity(
    instance: pyo.ConcreteModel,
    region_id_by_name: dict[str, int],
    technology_id_by_name: dict[str, int],
) -> list[dict]:
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


def _format_unmet_demand_from_aggregates(
    aggregates: RoaAggregates,
    region_id_by_name: dict[str, int],
) -> list[dict]:
    unmet_by_ry: dict[tuple, float] = defaultdict(float)
    all_keys = set(aggregates.demand_by_rfy.keys()) | set(aggregates.prod_by_rfy.keys())
    for (r, f, y) in all_keys:
        total_demand = aggregates.demand_by_rfy.get((r, f, y), 0.0)
        total_prod = aggregates.prod_by_rfy.get((r, f, y), 0.0)
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


def _compute_unmet_demand(
    instance: pyo.ConcreteModel,
    region_id_by_name: dict[str, int],
    aggregates: RoaAggregates | None = None,
) -> list[dict]:
    if aggregates is None:
        aggregates = _precompute_roa_aggregates(instance)
    return _format_unmet_demand_from_aggregates(aggregates, region_id_by_name)


def _extract_annual_emissions(
    instance: pyo.ConcreteModel,
    region_id_by_name: dict[str, int],
    regions: list,
    years: list,
    emissions: list,
) -> list[dict]:
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


def _format_pyomo_entries_from_raw(
    raw: dict,
    var_name: str,
) -> list[dict]:
    """Formatea un dict crudo de Pyomo al formato canónico `{index, value}`."""
    expected = VARIABLE_INDEX_NAMES.get(var_name)
    n_expected = len(expected) if expected else 0
    entries: list[dict] = []
    for key, value in raw.items():
        if abs(value) < _EPS:
            continue
        idx = _index_as_list(key, n_expected) if n_expected else (
            list(key) if isinstance(key, tuple) else [key]
        )
        if expected:
            idx = [
                _coerce_year(v) if name == "YEAR" else v
                for v, name in zip(idx, expected)
            ]
        entries.append({"index": idx, "value": float(value)})
    return entries


def _extract_pyomo_variable(
    instance: pyo.ConcreteModel,
    var_name: str,
    *,
    use_cache: bool = True,
) -> list[dict]:
    pyo_var = getattr(instance, var_name, None)
    if pyo_var is None:
        return []
    raw = _safe_extract(pyo_var, use_cache=use_cache)
    return _format_pyomo_entries_from_raw(raw, var_name)


def _filter_existing_variables(
    instance: pyo.ConcreteModel,
    var_names: tuple[str, ...] | list[str],
) -> list[str]:
    return [name for name in var_names if getattr(instance, name, None) is not None]


def _extract_pyomo_variables_parallel(
    instance: pyo.ConcreteModel,
    var_names: list[str],
    *,
    max_workers: int | None = None,
    parallel: bool = True,
) -> dict[str, list]:
    if not var_names:
        return {}

    use_parallel = parallel and _parallel_enabled() and len(var_names) > 1
    workers = max_workers or _resolve_parallel_workers(default=6)

    if not use_parallel:
        out: dict[str, list] = {}
        for name in var_names:
            entries = _extract_pyomo_variable(instance, name, use_cache=True)
            if entries:
                out[name] = entries
        return out

    out = {}
    with ThreadPoolExecutor(max_workers=min(workers, len(var_names))) as pool:
        futures = {
            pool.submit(_extract_pyomo_variable, instance, name, use_cache=True): name
            for name in var_names
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                entries = future.result()
                if entries:
                    out[name] = entries
            except Exception:
                logger.exception("Error extrayendo variable intermedia %s", name)
    return out


def _entries_from_prod_use(
    prod_by: dict[tuple, float],
    use_by: dict[tuple, float],
) -> tuple[list[dict], list[dict]]:
    prod_entries = [
        {"index": [r, t, f, l, _coerce_year(y)], "value": float(v)}
        for (r, t, f, l, y), v in prod_by.items()
        if abs(v) >= _EPS
    ]
    use_entries = [
        {"index": [r, t, f, l, _coerce_year(y)], "value": float(v)}
        for (r, t, f, l, y), v in use_by.items()
        if abs(v) >= _EPS
    ]
    return prod_entries, use_entries


def _compute_capacity_derivatives(
    instance: pyo.ConcreteModel,
    regions: list,
    technologies: list,
    years: list,
) -> tuple[list[dict], list[dict]]:
    nc_raw = _safe_extract(instance.NewCapacity)
    ol_data = _safe_extract_param(instance, "OperationalLife")
    rc_data = _safe_extract_param(instance, "ResidualCapacity")

    year_pairs = []
    for y in years:
        y_num = _coerce_year(y)
        if y_num is not None:
            year_pairs.append((y, int(y_num)))

    tca_entries: list[dict] = []
    anc_entries: list[dict] = []
    if not year_pairs:
        return tca_entries, anc_entries

    sorted_pairs = sorted(year_pairs, key=lambda p: p[1])
    y_originals = [yo for yo, _ in sorted_pairs]
    y_nums = np.fromiter((yn for _, yn in sorted_pairs), dtype=np.int64, count=len(sorted_pairs))

    for r in regions:
        for t in technologies:
            ol = int(_coerce_number(ol_data.get((r, t), 1), default=1.0))
            if ol <= 0:
                ol = 1
            nc_vec = np.fromiter(
                (nc_raw.get((r, t, yo), 0.0) for yo in y_originals),
                dtype=np.float64,
                count=len(y_originals),
            )
            res_vec = np.fromiter(
                (rc_data.get((r, t, yo), 0.0) for yo in y_originals),
                dtype=np.float64,
                count=len(y_originals),
            )
            if not nc_vec.any() and not res_vec.any():
                continue
            cumsum = np.concatenate(([0.0], np.cumsum(nc_vec)))
            lower_bounds = y_nums - ol + 1
            j_indices = np.searchsorted(y_nums, lower_bounds, side="left")
            upper_bounds = np.arange(1, len(y_nums) + 1)
            accs = cumsum[upper_bounds] - cumsum[j_indices]
            totals = accs + res_vec

            for i, y_num in enumerate(y_nums.tolist()):
                acc = float(accs[i])
                total = float(totals[i])
                if abs(total) >= _EPS:
                    tca_entries.append({"index": [r, t, int(y_num)], "value": total})
                if abs(acc) >= _EPS:
                    anc_entries.append({"index": [r, t, int(y_num)], "value": acc})

    return tca_entries, anc_entries


def _intermediate_var_names(
    instance: pyo.ConcreteModel,
    emissions: list,
    has_storage: bool,
) -> list[str]:
    var_names: list[str] = list(_filter_existing_variables(instance, _ALWAYS_PYOMO_VARIABLES))
    if emissions:
        var_names.extend(_filter_existing_variables(instance, _EMISSION_PYOMO_VARIABLES))
    if has_storage:
        var_names.extend(_filter_existing_variables(instance, _STORAGE_PYOMO_VARIABLES))
    return var_names


def vars_to_load_from_solution(
    instance: pyo.ConcreteModel,
    *,
    emissions: list | None = None,
    has_storage: bool | None = None,
) -> frozenset[str]:
    """Nombres de Var que process_results leerá; usado para mapeo selectivo HiGHS."""
    if emissions is None:
        emission_set = getattr(instance, "EMISSION", None)
        emissions = list(emission_set) if emission_set is not None else []
    if has_storage is None:
        storage_set = getattr(instance, "STORAGE", None)
        has_storage = bool(storage_set is not None and len(list(storage_set)) > 0)

    names = set(_TYPED_SOLUTION_VARS)
    names.update(_intermediate_var_names(instance, emissions, has_storage))
    if getattr(instance, "OBJ", None) is not None:
        names.add("OBJ")
    return frozenset(names)


def _collect_intermediate_parts(
    instance: pyo.ConcreteModel,
    regions: list,
    technologies: list,
    years: list,
    emissions: list,
    has_storage: bool,
    aggregates: RoaAggregates | None = None,
    *,
    parallel: bool = True,
) -> tuple[dict[str, list], list[dict], list[dict], list[dict], list[dict]]:
    """Extrae variables Pyomo, derivadas de capacidad y prod/use en bloques reutilizables."""
    var_names = _intermediate_var_names(instance, emissions, has_storage)
    if aggregates is not None and aggregates.roa_raw:
        var_names = [name for name in var_names if name != "RateOfActivity"]

    pyomo_out: dict[str, list] = {}
    tca_entries: list[dict] = []
    anc_entries: list[dict] = []

    run_parallel = parallel and _parallel_enabled() and len(var_names) > 0
    if run_parallel:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_pyomo = pool.submit(
                _extract_pyomo_variables_parallel,
                instance,
                var_names,
                parallel=True,
            )
            fut_cap = pool.submit(
                _compute_capacity_derivatives,
                instance,
                regions,
                technologies,
                years,
            )
            pyomo_out = fut_pyomo.result()
            tca_entries, anc_entries = fut_cap.result()
    else:
        pyomo_out = _extract_pyomo_variables_parallel(
            instance,
            var_names,
            parallel=False,
        )
        tca_entries, anc_entries = _compute_capacity_derivatives(
            instance, regions, technologies, years,
        )

    if aggregates is None:
        aggregates = _precompute_roa_aggregates(instance)

    if aggregates.roa_raw:
        roa_entries = _format_pyomo_entries_from_raw(
            aggregates.roa_raw,
            "RateOfActivity",
        )
        if roa_entries:
            pyomo_out["RateOfActivity"] = roa_entries

    prod_entries, use_entries = _entries_from_prod_use(
        aggregates.prod_by_rftly,
        aggregates.use_by_rftly,
    )
    return pyomo_out, tca_entries, anc_entries, prod_entries, use_entries


def _iter_intermediate_entries(
    pyomo_out: dict[str, list],
    tca_entries: list[dict],
    anc_entries: list[dict],
    prod_entries: list[dict],
    use_entries: list[dict],
) -> Iterator[tuple[str, dict]]:
    """Yield (variable_name, entry) sin materializar el dict completo."""
    for var_name, entries in pyomo_out.items():
        for entry in entries:
            yield var_name, entry
    for entry in tca_entries:
        yield "TotalCapacityAnnual", entry
    for entry in anc_entries:
        yield "AccumulatedNewCapacity", entry
    for entry in prod_entries:
        yield "ProductionByTechnology", entry
        # Mismo contenido que ProductionByTechnology; se persiste por contrato OSeMOSYS.
        yield "RateOfProductionByTechnology", entry
    for entry in use_entries:
        yield "UseByTechnology", entry
        yield "RateOfUseByTechnology", entry


def _materialize_intermediate_dict(
    pyomo_out: dict[str, list],
    tca_entries: list[dict],
    anc_entries: list[dict],
    prod_entries: list[dict],
    use_entries: list[dict],
) -> dict[str, list]:
    out: dict[str, list] = dict(pyomo_out)
    if tca_entries:
        out["TotalCapacityAnnual"] = tca_entries
    if anc_entries:
        out["AccumulatedNewCapacity"] = anc_entries
    if prod_entries:
        out["ProductionByTechnology"] = prod_entries
        out["RateOfProductionByTechnology"] = prod_entries
    if use_entries:
        out["UseByTechnology"] = use_entries
        out["RateOfUseByTechnology"] = use_entries
    return out


def _compute_intermediate_variables(
    instance: pyo.ConcreteModel,
    regions: list,
    technologies: list,
    years: list,
    emissions: list,
    has_storage: bool,
    aggregates: RoaAggregates | None = None,
    *,
    parallel: bool = True,
) -> dict[str, list]:
    parts = _collect_intermediate_parts(
        instance,
        regions,
        technologies,
        years,
        emissions,
        has_storage,
        aggregates=aggregates,
        parallel=parallel,
    )
    return _materialize_intermediate_dict(*parts)


def _run_parallel_map(
    tasks: list[tuple[str, Callable[[], T]]],
    *,
    max_workers: int | None = None,
    parallel: bool = True,
) -> dict[str, T]:
    if not tasks:
        return {}
    if not parallel or not _parallel_enabled() or len(tasks) == 1:
        return {name: fn() for name, fn in tasks}

    workers = max_workers or _resolve_parallel_workers(default=4)
    results: dict[str, T] = {}
    with ThreadPoolExecutor(max_workers=min(workers, len(tasks))) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks}
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()
    return results


def _attach_region_names(rows: list[dict], region_name_by_id: dict[int, str]) -> None:
    for row in rows:
        row["region_name"] = region_name_by_id.get(row["region_id"], "")


def _build_sol_dict(
    dispatch: list[dict],
    new_capacity: list[dict],
    unmet: list[dict],
    annual_emissions: list[dict],
    region_name_by_id: dict[int, str],
) -> dict[str, list]:
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
    return sol


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
    parallel: bool = True,
    materialize_intermediate: bool = True,
    on_stage: Callable[[str, float], None] | None = None,
) -> dict:
    """Construye el dict de resultados compatible con el pipeline.

    Parameters
    ----------
    materialize_intermediate : bool
        Si True (default), ``intermediate_variables`` es un dict completo (export/API).
        Si False, se expone ``_intermediate_entry_iter`` para consumo streaming en
        pipeline y ``intermediate_variables`` queda vacío (ahorra RAM duplicada).
    """
    profile = _ProfileCollector()
    profile.start_memory()
    timings: dict[str, float] = {}

    normalized_years: list[int] = []
    for y in years:
        y_num = _coerce_year(y)
        if y_num is not None:
            normalized_years.append(y_num)

    if on_stage:
        on_stage("process_results_precompute", 89.3)
    t_precompute = perf_counter()
    with profile.time_block("precompute_roa_aggregates_seconds"):
        aggregates = _precompute_roa_aggregates(instance)
    timings["process_results_precompute_seconds"] = perf_counter() - t_precompute
    profile.set_count("roa_entries", len(aggregates.roa_raw))

    if on_stage:
        on_stage("process_results_typed", 89.6)
    t_typed = perf_counter()
    parallel_tasks = [
        (
            "dispatch",
            lambda: _format_dispatch_from_aggregates(
                aggregates,
                region_id_by_name,
                technology_id_by_name,
                timeslice_id_by_name=timeslice_id_by_name,
            ),
        ),
        (
            "new_capacity",
            lambda: _extract_new_capacity(
                instance, region_id_by_name, technology_id_by_name,
            ),
        ),
        (
            "unmet",
            lambda: _format_unmet_demand_from_aggregates(
                aggregates, region_id_by_name,
            ),
        ),
        (
            "annual_emissions",
            lambda: _extract_annual_emissions(
                instance,
                region_id_by_name,
                regions,
                normalized_years,
                emissions,
            ),
        ),
    ]

    if parallel and _parallel_enabled():
        with profile.time_block("extract_typed_parallel_seconds"):
            typed = _run_parallel_map(parallel_tasks, max_workers=4, parallel=True)
    else:
        typed = _run_parallel_map(parallel_tasks, max_workers=4, parallel=False)

    dispatch = typed["dispatch"]
    new_capacity = typed["new_capacity"]
    unmet = typed["unmet"]
    annual_emissions = typed["annual_emissions"]
    profile.set_count("dispatch_rows", len(dispatch))
    profile.set_count("new_capacity_rows", len(new_capacity))

    _attach_region_names(dispatch, region_name_by_id)
    _attach_region_names(new_capacity, region_name_by_id)
    _attach_region_names(unmet, region_name_by_id)
    _attach_region_names(annual_emissions, region_name_by_id)

    total_dispatch = sum(row["dispatch"] for row in dispatch)
    total_unmet = sum(row["unmet_demand"] for row in unmet)

    sad_data = _safe_extract_param(instance, "SpecifiedAnnualDemand")
    aad_data = _safe_extract_param(instance, "AccumulatedAnnualDemand")
    total_demand = sum(sad_data.values()) + sum(aad_data.values())

    coverage_ratio = 1.0
    if total_demand > 0:
        coverage_ratio = max(0.0, min(1.0, (total_demand - total_unmet) / total_demand))

    sol = _build_sol_dict(
        dispatch, new_capacity, unmet, annual_emissions, region_name_by_id,
    )
    timings["process_results_typed_seconds"] = perf_counter() - t_typed
    timings["extract_results_seconds"] = (
        timings["process_results_precompute_seconds"] + timings["process_results_typed_seconds"]
    )

    if on_stage:
        on_stage("process_results_intermediate", 91.0)
    t_intermediate = perf_counter()
    intermediate_variables: dict[str, list] = {}
    intermediate_entry_iter = None
    pyomo_out: dict[str, list] = {}

    with profile.time_block("intermediate_vars_seconds"):
        intermediate_parts = _collect_intermediate_parts(
            instance,
            regions,
            technologies,
            normalized_years,
            emissions,
            has_storage,
            aggregates=aggregates,
            parallel=parallel,
        )
        pyomo_out, tca_entries, anc_entries, prod_entries, use_entries = intermediate_parts
        if materialize_intermediate:
            intermediate_variables = _materialize_intermediate_dict(
                pyomo_out, tca_entries, anc_entries, prod_entries, use_entries,
            )
            intermediate_entry_iter = None
        else:
            intermediate_variables = {}
            intermediate_entry_iter = _iter_intermediate_entries(
                pyomo_out, tca_entries, anc_entries, prod_entries, use_entries,
            )
    timings["process_results_intermediate_seconds"] = perf_counter() - t_intermediate
    timings["intermediate_vars_seconds"] = timings["process_results_intermediate_seconds"]
    profile.set_count(
        "intermediate_var_names",
        len(intermediate_variables) if materialize_intermediate else len(pyomo_out),
    )
    if materialize_intermediate:
        profile.set_count(
            "intermediate_var_rows",
            sum(len(v) for v in intermediate_variables.values()),
        )
    else:
        profile.set_count("intermediate_var_rows", -1)

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

    profile.record_memory_peak()
    profile.log_summary()
    timings.update(profile.timings)

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
    if intermediate_entry_iter is not None:
        result["_intermediate_entry_iter"] = intermediate_entry_iter
    if solver_result.get("infeasibility_diagnostics"):
        result["infeasibility_diagnostics"] = solver_result["infeasibility_diagnostics"]
    return result
