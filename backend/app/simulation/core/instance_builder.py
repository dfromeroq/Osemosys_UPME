"""Construcción de instancia via DataPortal → CSVs.

Replica la celda 23 del notebook osemosys_notebook_UPME_OPT_YA_20260220:
carga CSVs generados por data_processing usando DataPortal de Pyomo y crea
la instancia concreta.

Los parámetros comentados usan sus valores default del modelo (model_definition.py).
Orden de uso: data_processing.run_data_processing() → build_instance() → solver.solve_model().
"""

from __future__ import annotations

import logging
import os
from time import perf_counter

import pandas as pd
from pyomo.environ import AbstractModel, ConcreteModel, DataPortal

logger = logging.getLogger(__name__)

_USE_PANDAS_DATAPORTAL = os.getenv("OSEMOSYS_FAST_DATAPORTAL", "1") != "0"
_PYOMO_REPORT_TIMING = os.getenv("OSEMOSYS_PYOMO_REPORT_TIMING", "0") == "1"

# Columnas de índice que Pyomo/DataPortal tratan como enteros (paridad con CSV nativo).
# SEASON/DAYTYPE/DAILYTIMEBRACKET son sets ordenados numéricos en OSeMOSYS (p. ej. "1" → 1).
_INT_INDEX_COLS = frozenset({
    "YEAR",
    "MODE_OF_OPERATION",
    "SEASON",
    "DAYTYPE",
    "DAILYTIMEBRACKET",
})


def _csv_has_data(fpath: str) -> bool:
    """True si el CSV existe y tiene al menos una fila de datos."""
    if not os.path.exists(fpath):
        return False
    try:
        if os.path.getsize(fpath) <= 2:
            return False
    except OSError:
        return False
    with open(fpath, encoding="utf-8") as handle:
        handle.readline()
        return bool(handle.readline().strip())


def _coerce_index_value(col: str, text: str) -> object:
    """Alinea tipos de índice con los que produce ``DataPortal.load(filename=...)``."""
    if col in _INT_INDEX_COLS:
        return int(float(text))
    return text


def _load_param_pandas(
    data: DataPortal,
    fpath: str,
    param_name: str,
    index: list[str] | str,
) -> None:
    index_cols = [index] if isinstance(index, str) else list(index)
    df = pd.read_csv(fpath, dtype=str, low_memory=False)
    if df.empty or "VALUE" not in df.columns:
        return

    param_dict: dict[object, float] = {}
    for row in df.itertuples(index=False):
        row_map = dict(zip(df.columns, row))
        key_parts: list[object] = []
        for col in index_cols:
            raw = row_map.get(col)
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                key_parts = []
                break
            text = str(raw).strip()
            if not text or text.lower() == "nan":
                key_parts = []
                break
            key_parts.append(_coerce_index_value(col, text))
        if len(key_parts) != len(index_cols):
            continue
        key: object = key_parts[0] if len(key_parts) == 1 else tuple(key_parts)
        raw_val = row_map.get("VALUE")
        try:
            param_dict[key] = float(raw_val) if raw_val not in (None, "", "nan") else 0.0
        except (TypeError, ValueError):
            param_dict[key] = 0.0

    if not param_dict:
        return
    data.data()[param_name] = param_dict


def build_instance(
    model: AbstractModel,
    csv_dir: str,
    *,
    has_storage: bool = False,
    has_udc: bool = True,
    timings_out: dict[str, float] | None = None,
) -> ConcreteModel:
    """Carga CSVs via DataPortal y crea instancia concreta."""
    data = DataPortal()
    p = csv_dir
    load_timings: dict[str, float] = {}

    def _load_set(filename: str, set_name: str) -> None:
        fpath = os.path.join(p, filename)
        if not _csv_has_data(fpath):
            if os.path.exists(fpath):
                logger.debug("Skipping empty set CSV: %s", filename)
            return
        t0 = perf_counter()
        # Sets siempre vía CSV nativo de Pyomo: garantiza tipos idénticos a params.
        data.load(filename=fpath, set=set_name)
        load_timings[f"load_set_{set_name}"] = perf_counter() - t0

    def _load_param(filename: str, param_name: str, index: list[str] | str) -> None:
        fpath = os.path.join(p, filename)
        if not _csv_has_data(fpath):
            if os.path.exists(fpath):
                logger.debug("Skipping empty param CSV: %s", filename)
            return
        t0 = perf_counter()
        try:
            if _USE_PANDAS_DATAPORTAL:
                _load_param_pandas(data, fpath, param_name, index)
            else:
                data.load(filename=fpath, param=param_name, index=index)
        except Exception:
            logger.warning("Fallback DataPortal param load for %s", filename, exc_info=True)
            data.load(filename=fpath, param=param_name, index=index)
        load_timings[f"load_param_{param_name}"] = perf_counter() - t0

    # ==========================
    # CARGA DE SETS (orden compatible con el modelo abstracto)
    # ==========================

    _load_set("EMISSION.csv", "EMISSION")
    _load_set("FUEL.csv", "FUEL")
    _load_set("TIMESLICE.csv", "TIMESLICE")
    _load_set("MODE_OF_OPERATION.csv", "MODE_OF_OPERATION")
    _load_set("TECHNOLOGY.csv", "TECHNOLOGY")
    _load_set("YEAR.csv", "YEAR")
    _load_set("REGION.csv", "REGION")

    if has_storage:
        _load_set("STORAGE.csv", "STORAGE")
        _load_set("SEASON.csv", "SEASON")
        _load_set("DAYTYPE.csv", "DAYTYPE")
        _load_set("DAILYTIMEBRACKET.csv", "DAILYTIMEBRACKET")

    # ==========================
    # CARGA DE PARÁMETROS
    # ==========================

    _load_param("YearSplit.csv", "YearSplit", ["TIMESLICE", "YEAR"])
    _load_param("DiscountRate.csv", "DiscountRate", ["REGION"])
    _load_param("DepreciationMethod.csv", "DepreciationMethod", ["REGION"])
    _load_param("CapacityToActivityUnit.csv", "CapacityToActivityUnit", ["REGION", "TECHNOLOGY"])
    _load_param(
        "CapacityOfOneTechnologyUnit.csv", "CapacityOfOneTechnologyUnit",
        ["REGION", "TECHNOLOGY", "YEAR"],
    )
    _load_param("OperationalLife.csv", "OperationalLife", ["REGION", "TECHNOLOGY"])
    _load_param(
        "TotalAnnualMaxCapacityInvestment.csv", "TotalAnnualMaxCapacityInvestment",
        ["REGION", "TECHNOLOGY", "YEAR"],
    )
    _load_param(
        "TotalAnnualMinCapacityInvestment.csv", "TotalAnnualMinCapacityInvestment",
        ["REGION", "TECHNOLOGY", "YEAR"],
    )
    _load_param(
        "TotalTechnologyAnnualActivityLowerLimit.csv", "TotalTechnologyAnnualActivityLowerLimit",
        ["REGION", "TECHNOLOGY", "YEAR"],
    )
    _load_param(
        "TotalTechnologyAnnualActivityUpperLimit.csv", "TotalTechnologyAnnualActivityUpperLimit",
        ["REGION", "TECHNOLOGY", "YEAR"],
    )
    _load_param(
        "TotalTechnologyModelPeriodActivityLowerLimit.csv",
        "TotalTechnologyModelPeriodActivityLowerLimit", ["REGION", "TECHNOLOGY"],
    )
    _load_param(
        "TotalTechnologyModelPeriodActivityUpperLimit.csv",
        "TotalTechnologyModelPeriodActivityUpperLimit", ["REGION", "TECHNOLOGY"],
    )
    _load_param(
        "CapacityFactor.csv", "CapacityFactor",
        ["REGION", "TECHNOLOGY", "TIMESLICE", "YEAR"],
    )
    _load_param("AvailabilityFactor.csv", "AvailabilityFactor", ["REGION", "TECHNOLOGY", "YEAR"])
    _load_param("ResidualCapacity.csv", "ResidualCapacity", ["REGION", "TECHNOLOGY", "YEAR"])
    _load_param("CapitalCost.csv", "CapitalCost", ["REGION", "TECHNOLOGY", "YEAR"])
    _load_param("FixedCost.csv", "FixedCost", ["REGION", "TECHNOLOGY", "YEAR"])
    _load_param(
        "VariableCost.csv", "VariableCost",
        ["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"],
    )
    _load_param(
        "EmissionActivityRatio.csv", "EmissionActivityRatio",
        ["REGION", "TECHNOLOGY", "EMISSION", "MODE_OF_OPERATION", "YEAR"],
    )
    _load_param("EmissionsPenalty.csv", "EmissionsPenalty", ["REGION", "EMISSION", "YEAR"])
    _load_param(
        "ModelPeriodEmissionLimit.csv", "ModelPeriodEmissionLimit", ["REGION", "EMISSION"],
    )
    _load_param(
        "ModelPeriodExogenousEmission.csv", "ModelPeriodExogenousEmission", ["REGION", "EMISSION"],
    )
    _load_param(
        "AnnualExogenousEmission.csv", "AnnualExogenousEmission",
        ["REGION", "EMISSION", "YEAR"],
    )
    _load_param(
        "AnnualEmissionLimit.csv", "AnnualEmissionLimit", ["REGION", "EMISSION", "YEAR"],
    )
    _load_param(
        "InputActivityRatio.csv", "InputActivityRatio",
        ["REGION", "TECHNOLOGY", "FUEL", "MODE_OF_OPERATION", "YEAR"],
    )
    _load_param(
        "OutputActivityRatio.csv", "OutputActivityRatio",
        ["REGION", "TECHNOLOGY", "FUEL", "MODE_OF_OPERATION", "YEAR"],
    )
    _load_param("ReserveMarginTagFuel.csv", "ReserveMarginTagFuel", ["REGION", "FUEL", "YEAR"])
    _load_param("RETagTechnology.csv", "RETagTechnology", ["REGION", "TECHNOLOGY", "YEAR"])
    _load_param("RETagFuel.csv", "RETagFuel", ["REGION", "FUEL", "YEAR"])
    _load_param("REMinProductionTarget.csv", "REMinProductionTarget", ["REGION", "YEAR"])
    _load_param(
        "ReserveMarginTagTechnology.csv", "ReserveMarginTagTechnology",
        ["REGION", "TECHNOLOGY", "YEAR"],
    )
    _load_param("ReserveMargin.csv", "ReserveMargin", ["REGION", "YEAR"])
    _load_param(
        "AccumulatedAnnualDemand.csv", "AccumulatedAnnualDemand", ["REGION", "FUEL", "YEAR"],
    )
    _load_param(
        "SpecifiedAnnualDemand.csv", "SpecifiedAnnualDemand", ["REGION", "FUEL", "YEAR"],
    )
    _load_param(
        "SpecifiedDemandProfile.csv", "SpecifiedDemandProfile",
        ["REGION", "FUEL", "TIMESLICE", "YEAR"],
    )
    _load_param(
        "TotalAnnualMaxCapacity.csv", "TotalAnnualMaxCapacity",
        ["REGION", "TECHNOLOGY", "YEAR"],
    )
    _load_param(
        "TotalAnnualMinCapacity.csv", "TotalAnnualMinCapacity",
        ["REGION", "TECHNOLOGY", "YEAR"],
    )

    if has_storage:
        _load_param("DaySplit.csv", "DaySplit", ["DAILYTIMEBRACKET", "YEAR"])
        _load_param("Conversionls.csv", "Conversionls", ["TIMESLICE", "SEASON"])
        _load_param("Conversionld.csv", "Conversionld", ["TIMESLICE", "DAYTYPE"])
        _load_param("Conversionlh.csv", "Conversionlh", ["TIMESLICE", "DAILYTIMEBRACKET"])
        _load_param("DaysInDayType.csv", "DaysInDayType", ["SEASON", "DAYTYPE", "YEAR"])
        _load_param(
            "TechnologyToStorage.csv", "TechnologyToStorage",
            ["REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION"],
        )
        _load_param(
            "TechnologyFromStorage.csv", "TechnologyFromStorage",
            ["REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION"],
        )
        _load_param("StorageLevelStart.csv", "StorageLevelStart", ["REGION", "STORAGE"])
        _load_param("StorageMaxChargeRate.csv", "StorageMaxChargeRate", ["REGION", "STORAGE"])
        _load_param(
            "StorageMaxDischargeRate.csv", "StorageMaxDischargeRate", ["REGION", "STORAGE"],
        )
        _load_param("MinStorageCharge.csv", "MinStorageCharge", ["REGION", "STORAGE", "YEAR"])
        _load_param("OperationalLifeStorage.csv", "OperationalLifeStorage", ["REGION", "STORAGE"])
        _load_param(
            "CapitalCostStorage.csv", "CapitalCostStorage", ["REGION", "STORAGE", "YEAR"],
        )
        _load_param(
            "ResidualStorageCapacity.csv", "ResidualStorageCapacity",
            ["REGION", "STORAGE", "YEAR"],
        )

    if has_udc:
        _load_set("UDC.csv", "UDC")
        _load_param(
            "UDCMultiplierTotalCapacity.csv", "UDCMultiplierTotalCapacity",
            ["REGION", "TECHNOLOGY", "UDC", "YEAR"],
        )
        _load_param(
            "UDCMultiplierNewCapacity.csv", "UDCMultiplierNewCapacity",
            ["REGION", "TECHNOLOGY", "UDC", "YEAR"],
        )
        _load_param(
            "UDCMultiplierActivity.csv", "UDCMultiplierActivity",
            ["REGION", "TECHNOLOGY", "UDC", "YEAR"],
        )
        _load_param("UDCConstant.csv", "UDCConstant", ["REGION", "UDC", "YEAR"])
        _load_param("UDCTag.csv", "UDCTag", ["REGION", "UDC"])

    logger.info("Creando instancia del modelo...")
    t_create = perf_counter()
    # El timing por componente de Pyomo intenta ``len(Any)`` y falla al
    # formatear Params sparse. Los timings estructurados propios siguen activos.
    instance = model.create_instance(data, report_timing=_PYOMO_REPORT_TIMING)
    load_timings["create_instance_pyomo_seconds"] = perf_counter() - t_create
    if load_timings:
        top = sorted(load_timings.items(), key=lambda kv: kv[1], reverse=True)[:5]
        logger.info(
            "DataPortal timings (top 5): %s",
            ", ".join(f"{k}={v:.2f}s" for k, v in top),
        )
    logger.info("Instancia creada exitosamente")

    if timings_out is not None:
        timings_out.update(load_timings)

    return instance
