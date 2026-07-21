"""Análisis reutilizable de infactibilidades para OSeMOSYS.

Complementa el diagnóstico básico de :func:`app.simulation.core.solver._run_infeasibility_diagnostics`
agregando:

    * Un **mapa estático** que asocia cada tipo de restricción (prefijo del nombre
      Pyomo, ej. ``EnergyBalanceEachTS5``) con los parámetros OSeMOSYS que la alimentan.
    * Un **parser** de nombres Pyomo para extraer los índices de cada violación
      (ej. ``EnergyBalanceEachTS5[COL,L1,ELECTRICITY,2030]`` →
      ``{"REGION":"COL","TIMESLICE":"L1","FUEL":"ELECTRICITY","YEAR":"2030"}``).
    * Un **lector de CSVs** que recupera los valores actuales de los parámetros
      relevantes para cada índice violado.
    * Un **intento de IIS** (Irreducible Inconsistent Subsystem) vía ``highspy``
      cuando el solver es HiGHS. Para GLPK se ejecuta ``glpsol --nopresol`` y se
      parsean las restricciones violadas en la solución forzada (heurístico, no IIS
      verdadero, pero suficiente para alimentar el mapeo constraint→parámetro).

El módulo no tiene efectos secundarios sobre el pipeline productivo: se expone
como API pública y lo consume ``backend/run_local_csv.py``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# =====================================================================
# Mapa estático: prefijo de restricción → parámetros OSeMOSYS relacionados
# =====================================================================


@dataclass(frozen=True)
class ParamSpec:
    """Describe un parámetro OSeMOSYS y cómo derivar sus índices desde la restricción."""

    name: str
    #: Columnas índice del CSV del parámetro (en orden).
    index_names: tuple[str, ...]
    #: Para cada ``index_names[i]``, nombre del índice de la restricción del que
    #: se toma el valor. ``None`` significa "no filtrar por ese índice" (se
    #: devuelven todas las filas coincidentes en los demás índices).
    derive_from: tuple[str | None, ...]


@dataclass(frozen=True)
class ConstraintSpec:
    """Describe un tipo de restricción OSeMOSYS (indexación + parámetros relacionados)."""

    index_names: tuple[str, ...]
    parameters: tuple[ParamSpec, ...]
    description: str = ""


def _ps(name: str, idx: tuple[str, ...], derive: tuple[str | None, ...]) -> ParamSpec:
    return ParamSpec(name=name, index_names=idx, derive_from=derive)


# Indexaciones frecuentes reutilizadas abajo.
_REG_TECH_YEAR = ("REGION", "TECHNOLOGY", "YEAR")
_REG_TECH_MODE_YEAR = ("REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR")
_REG_TECH_FUEL_MODE_YEAR = ("REGION", "TECHNOLOGY", "FUEL", "MODE_OF_OPERATION", "YEAR")
_REG_TECH_EMIS_MODE_YEAR = (
    "REGION",
    "TECHNOLOGY",
    "EMISSION",
    "MODE_OF_OPERATION",
    "YEAR",
)
_STORAGE_YEAR = ("REGION", "STORAGE", "YEAR")
_STORAGE_FLOW = (
    "REGION",
    "STORAGE",
    "SEASON",
    "DAYTYPE",
    "DAILYTIMEBRACKET",
    "YEAR",
)
_STORAGE_RATE = (*_STORAGE_FLOW, "TECHNOLOGY", "MODE_OF_OPERATION")
_STORAGE_YEAR_SPEC = ConstraintSpec(
    index_names=_STORAGE_YEAR,
    parameters=(
        _ps("MinStorageCharge", _STORAGE_YEAR, _STORAGE_YEAR),
        _ps("ResidualStorageCapacity", _STORAGE_YEAR, _STORAGE_YEAR),
        _ps("CapitalCostStorage", _STORAGE_YEAR, _STORAGE_YEAR),
        _ps("OperationalLifeStorage", ("REGION", "STORAGE"), ("REGION", "STORAGE")),
        _ps("StorageLevelStart", ("REGION", "STORAGE"), ("REGION", "STORAGE")),
    ),
    description="Capacidad, nivel o inversión anual de almacenamiento.",
)
_STORAGE_FLOW_SPEC = ConstraintSpec(
    index_names=_STORAGE_FLOW,
    parameters=(
        _ps("MinStorageCharge", _STORAGE_YEAR, ("REGION", "STORAGE", "YEAR")),
        _ps("StorageMaxChargeRate", ("REGION", "STORAGE"), ("REGION", "STORAGE")),
        _ps("StorageMaxDischargeRate", ("REGION", "STORAGE"), ("REGION", "STORAGE")),
        _ps("DaySplit", ("DAILYTIMEBRACKET", "YEAR"), ("DAILYTIMEBRACKET", "YEAR")),
        _ps("DaysInDayType", ("SEASON", "DAYTYPE", "YEAR"), ("SEASON", "DAYTYPE", "YEAR")),
    ),
    description="Flujo o límites operativos del almacenamiento.",
)
_STORAGE_RATE_SPEC = ConstraintSpec(
    index_names=_STORAGE_RATE,
    parameters=(
        _ps("TechnologyToStorage", ("REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION"), ("REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION")),
        _ps("TechnologyFromStorage", ("REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION"), ("REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION")),
        _ps("Conversionls", ("TIMESLICE", "SEASON"), (None, "SEASON")),
        _ps("Conversionld", ("TIMESLICE", "DAYTYPE"), (None, "DAYTYPE")),
        _ps("Conversionlh", ("TIMESLICE", "DAILYTIMEBRACKET"), (None, "DAILYTIMEBRACKET")),
    ),
    description="Conversión entre actividad tecnológica y carga/descarga de storage.",
)


CONSTRAINT_PARAM_MAP: dict[str, ConstraintSpec] = {
    "EnergyBalanceEachTS5": ConstraintSpec(
        index_names=("REGION", "TIMESLICE", "FUEL", "YEAR"),
        parameters=(
            _ps(
                "SpecifiedAnnualDemand",
                ("REGION", "FUEL", "YEAR"),
                ("REGION", "FUEL", "YEAR"),
            ),
            _ps(
                "SpecifiedDemandProfile",
                ("REGION", "FUEL", "TIMESLICE", "YEAR"),
                ("REGION", "FUEL", "TIMESLICE", "YEAR"),
            ),
            _ps(
                "YearSplit",
                ("TIMESLICE", "YEAR"),
                ("TIMESLICE", "YEAR"),
            ),
            _ps(
                "InputActivityRatio",
                _REG_TECH_FUEL_MODE_YEAR,
                ("REGION", None, "FUEL", None, "YEAR"),
            ),
            _ps(
                "OutputActivityRatio",
                _REG_TECH_FUEL_MODE_YEAR,
                ("REGION", None, "FUEL", None, "YEAR"),
            ),
        ),
        description="Balance energético por timeslice (demanda específica vs producción).",
    ),
    "EnergyBalanceEachYear4": ConstraintSpec(
        index_names=("REGION", "FUEL", "YEAR"),
        parameters=(
            _ps(
                "AccumulatedAnnualDemand",
                ("REGION", "FUEL", "YEAR"),
                ("REGION", "FUEL", "YEAR"),
            ),
            _ps(
                "YearSplit",
                ("TIMESLICE", "YEAR"),
                (None, "YEAR"),
            ),
            _ps(
                "InputActivityRatio",
                _REG_TECH_FUEL_MODE_YEAR,
                ("REGION", None, "FUEL", None, "YEAR"),
            ),
            _ps(
                "OutputActivityRatio",
                _REG_TECH_FUEL_MODE_YEAR,
                ("REGION", None, "FUEL", None, "YEAR"),
            ),
        ),
        description="Balance energético anual (demanda acumulada anual).",
    ),
    "ConstraintCapacity": ConstraintSpec(
        index_names=("REGION", "TIMESLICE", "TECHNOLOGY", "YEAR"),
        parameters=(
            _ps(
                "CapacityFactor",
                ("REGION", "TECHNOLOGY", "TIMESLICE", "YEAR"),
                ("REGION", "TECHNOLOGY", "TIMESLICE", "YEAR"),
            ),
            _ps(
                "CapacityToActivityUnit",
                ("REGION", "TECHNOLOGY"),
                ("REGION", "TECHNOLOGY"),
            ),
            _ps(
                "ResidualCapacity",
                _REG_TECH_YEAR,
                ("REGION", "TECHNOLOGY", "YEAR"),
            ),
            _ps(
                "OperationalLife",
                ("REGION", "TECHNOLOGY"),
                ("REGION", "TECHNOLOGY"),
            ),
            _ps(
                "AvailabilityFactor",
                _REG_TECH_YEAR,
                ("REGION", "TECHNOLOGY", "YEAR"),
            ),
        ),
        description="Capacidad instalada alcanza la actividad requerida en el timeslice.",
    ),
    "TotalNewCapacity_2": ConstraintSpec(
        index_names=_REG_TECH_YEAR,
        parameters=(
            _ps("CapacityOfOneTechnologyUnit", _REG_TECH_YEAR, _REG_TECH_YEAR),
        ),
        description="Vincula unidades enteras de tecnología con nueva capacidad.",
    ),
    "PlannedMaintenance": ConstraintSpec(
        index_names=_REG_TECH_YEAR,
        parameters=(
            _ps("CapacityFactor", ("REGION", "TECHNOLOGY", "TIMESLICE", "YEAR"), ("REGION", "TECHNOLOGY", None, "YEAR")),
            _ps("AvailabilityFactor", _REG_TECH_YEAR, _REG_TECH_YEAR),
            _ps("ResidualCapacity", _REG_TECH_YEAR, _REG_TECH_YEAR),
            _ps("CapacityToActivityUnit", ("REGION", "TECHNOLOGY"), ("REGION", "TECHNOLOGY")),
            _ps("OperationalLife", ("REGION", "TECHNOLOGY"), ("REGION", "TECHNOLOGY")),
            _ps("YearSplit", ("TIMESLICE", "YEAR"), (None, "YEAR")),
        ),
        description="Actividad anual permitida después de mantenimiento/disponibilidad.",
    ),
    "TotalAnnualMaxCapacityConstraint": ConstraintSpec(
        index_names=_REG_TECH_YEAR,
        parameters=(
            _ps("TotalAnnualMaxCapacity", _REG_TECH_YEAR, _REG_TECH_YEAR),
            _ps("ResidualCapacity", _REG_TECH_YEAR, _REG_TECH_YEAR),
            _ps("OperationalLife", ("REGION", "TECHNOLOGY"), ("REGION", "TECHNOLOGY")),
        ),
        description="Límite superior de capacidad total anual por tecnología.",
    ),
    "TotalAnnualMinCapacityConstraint": ConstraintSpec(
        index_names=_REG_TECH_YEAR,
        parameters=(
            _ps("TotalAnnualMinCapacity", _REG_TECH_YEAR, _REG_TECH_YEAR),
            _ps("ResidualCapacity", _REG_TECH_YEAR, _REG_TECH_YEAR),
            _ps("OperationalLife", ("REGION", "TECHNOLOGY"), ("REGION", "TECHNOLOGY")),
        ),
        description="Límite inferior de capacidad total anual por tecnología.",
    ),
    "TotalAnnualMaxNewCapacityConstraint": ConstraintSpec(
        index_names=_REG_TECH_YEAR,
        parameters=(
            _ps(
                "TotalAnnualMaxCapacityInvestment",
                _REG_TECH_YEAR,
                _REG_TECH_YEAR,
            ),
        ),
        description="Límite superior de nueva capacidad anual.",
    ),
    "TotalAnnualMinNewCapacityConstraint": ConstraintSpec(
        index_names=_REG_TECH_YEAR,
        parameters=(
            _ps(
                "TotalAnnualMinCapacityInvestment",
                _REG_TECH_YEAR,
                _REG_TECH_YEAR,
            ),
        ),
        description="Límite inferior de nueva capacidad anual.",
    ),
    "TotalAnnualTechnologyActivityUpperlimit": ConstraintSpec(
        index_names=_REG_TECH_YEAR,
        parameters=(
            _ps(
                "TotalTechnologyAnnualActivityUpperLimit",
                _REG_TECH_YEAR,
                _REG_TECH_YEAR,
            ),
        ),
        description="Límite superior de actividad anual por tecnología.",
    ),
    "TotalAnnualTechnologyActivityLowerlimit": ConstraintSpec(
        index_names=_REG_TECH_YEAR,
        parameters=(
            _ps(
                "TotalTechnologyAnnualActivityLowerLimit",
                _REG_TECH_YEAR,
                _REG_TECH_YEAR,
            ),
        ),
        description="Límite inferior de actividad anual por tecnología.",
    ),
    "TotalModelHorizonTechnologyActivityUpperLimit": ConstraintSpec(
        index_names=("REGION", "TECHNOLOGY"),
        parameters=(
            _ps(
                "TotalTechnologyModelPeriodActivityUpperLimit",
                ("REGION", "TECHNOLOGY"),
                ("REGION", "TECHNOLOGY"),
            ),
        ),
        description="Límite superior de actividad acumulada en el período del modelo.",
    ),
    "TotalModelHorizonTechnologyActivityLowerLimit": ConstraintSpec(
        index_names=("REGION", "TECHNOLOGY"),
        parameters=(
            _ps(
                "TotalTechnologyModelPeriodActivityLowerLimit",
                ("REGION", "TECHNOLOGY"),
                ("REGION", "TECHNOLOGY"),
            ),
        ),
        description="Límite inferior de actividad acumulada en el período del modelo.",
    ),
    "AnnualEmissionProductionByMode": ConstraintSpec(
        index_names=_REG_TECH_EMIS_MODE_YEAR,
        parameters=(
            _ps("EmissionActivityRatio", _REG_TECH_EMIS_MODE_YEAR, _REG_TECH_EMIS_MODE_YEAR),
            _ps("YearSplit", ("TIMESLICE", "YEAR"), (None, "YEAR")),
        ),
        description="Contabilidad de emisiones por tecnología y modo.",
    ),
    "AnnualEmissionProduction": ConstraintSpec(
        index_names=("REGION", "TECHNOLOGY", "EMISSION", "YEAR"),
        parameters=(
            _ps("EmissionActivityRatio", _REG_TECH_EMIS_MODE_YEAR, ("REGION", "TECHNOLOGY", "EMISSION", None, "YEAR")),
        ),
        description="Agregación de emisiones de todos los modos.",
    ),
    "EmissionsAccounting1": ConstraintSpec(
        index_names=("REGION", "EMISSION", "YEAR"),
        parameters=(
            _ps("EmissionActivityRatio", _REG_TECH_EMIS_MODE_YEAR, ("REGION", None, "EMISSION", None, "YEAR")),
            _ps("AnnualExogenousEmission", ("REGION", "EMISSION", "YEAR"), ("REGION", "EMISSION", "YEAR")),
        ),
        description="Agregación anual de emisiones por región.",
    ),
    "EmissionsAccounting2": ConstraintSpec(
        index_names=("REGION", "EMISSION"),
        parameters=(
            _ps("ModelPeriodExogenousEmission", ("REGION", "EMISSION"), ("REGION", "EMISSION")),
            _ps("EmissionActivityRatio", _REG_TECH_EMIS_MODE_YEAR, ("REGION", None, "EMISSION", None, None)),
        ),
        description="Contabilidad de emisiones del horizonte completo.",
    ),
    "AnnualEmissionsLimit": ConstraintSpec(
        index_names=("REGION", "EMISSION", "YEAR"),
        parameters=(
            _ps(
                "AnnualEmissionLimit",
                ("REGION", "EMISSION", "YEAR"),
                ("REGION", "EMISSION", "YEAR"),
            ),
            _ps(
                "AnnualExogenousEmission",
                ("REGION", "EMISSION", "YEAR"),
                ("REGION", "EMISSION", "YEAR"),
            ),
            _ps(
                "EmissionActivityRatio",
                _REG_TECH_EMIS_MODE_YEAR,
                ("REGION", None, "EMISSION", None, "YEAR"),
            ),
        ),
        description="Límite de emisiones anuales por región/emisión.",
    ),
    "ModelPeriodEmissionsLimit": ConstraintSpec(
        index_names=("REGION", "EMISSION"),
        parameters=(
            _ps(
                "ModelPeriodEmissionLimit",
                ("REGION", "EMISSION"),
                ("REGION", "EMISSION"),
            ),
            _ps(
                "ModelPeriodExogenousEmission",
                ("REGION", "EMISSION"),
                ("REGION", "EMISSION"),
            ),
        ),
        description="Límite de emisiones del período completo del modelo.",
    ),
    "ReserveMargin_TechnologiesIncluded": ConstraintSpec(
        index_names=("REGION", "YEAR"),
        parameters=(
            _ps("ReserveMarginTagTechnology", _REG_TECH_YEAR, ("REGION", None, "YEAR")),
            _ps("ResidualCapacity", _REG_TECH_YEAR, ("REGION", None, "YEAR")),
            _ps("CapacityToActivityUnit", ("REGION", "TECHNOLOGY"), ("REGION", None)),
            _ps("OperationalLife", ("REGION", "TECHNOLOGY"), ("REGION", None)),
        ),
        description="Capacidad total elegible para margen de reserva.",
    ),
    "ReserveMargin_FuelsIncluded": ConstraintSpec(
        index_names=("REGION", "TIMESLICE", "YEAR"),
        parameters=(
            _ps("ReserveMarginTagFuel", ("REGION", "FUEL", "YEAR"), ("REGION", None, "YEAR")),
            _ps("OutputActivityRatio", _REG_TECH_FUEL_MODE_YEAR, ("REGION", None, None, None, "YEAR")),
        ),
        description="Demanda de fuels incluida en el margen de reserva.",
    ),
    "ReserveMarginConstraint": ConstraintSpec(
        index_names=("REGION", "TIMESLICE", "YEAR"),
        parameters=(
            _ps("ReserveMargin", ("REGION", "YEAR"), ("REGION", "YEAR")),
            _ps(
                "ReserveMarginTagTechnology",
                _REG_TECH_YEAR,
                ("REGION", None, "YEAR"),
            ),
            _ps(
                "ReserveMarginTagFuel",
                ("REGION", "FUEL", "YEAR"),
                ("REGION", None, "YEAR"),
            ),
        ),
        description="Margen de reserva mínimo de capacidad por timeslice.",
    ),
    "LU1_TechnologyActivityByModeUL": ConstraintSpec(
        index_names=_REG_TECH_MODE_YEAR,
        parameters=(
            _ps(
                "TechnologyActivityByModeUpperLimit",
                _REG_TECH_MODE_YEAR,
                _REG_TECH_MODE_YEAR,
            ),
        ),
        description="Límite superior de actividad por modo.",
    ),
    "LU2_TechnologyActivityByModeLL": ConstraintSpec(
        index_names=_REG_TECH_MODE_YEAR,
        parameters=(
            _ps(
                "TechnologyActivityByModeLowerLimit",
                _REG_TECH_MODE_YEAR,
                _REG_TECH_MODE_YEAR,
            ),
        ),
        description="Límite inferior de actividad por modo.",
    ),
    "LU3_TechnologyActivityIncreaseByMode": ConstraintSpec(
        index_names=(
            "REGION",
            "TECHNOLOGY",
            "MODE_OF_OPERATION",
            "YEAR",
            "PREVIOUS_YEAR",
        ),
        parameters=(
            _ps(
                "TechnologyActivityIncreaseByModeLimit",
                _REG_TECH_MODE_YEAR,
                (
                    "REGION",
                    "TECHNOLOGY",
                    "MODE_OF_OPERATION",
                    "PREVIOUS_YEAR",
                ),
            ),
        ),
        description="Límite al aumento anual de actividad por modo.",
    ),
    "LU4_TechnologyActivityDecreaseByMode": ConstraintSpec(
        index_names=(
            "REGION",
            "TECHNOLOGY",
            "MODE_OF_OPERATION",
            "YEAR",
            "PREVIOUS_YEAR",
        ),
        parameters=(
            _ps(
                "TechnologyActivityDecreaseByModeLimit",
                _REG_TECH_MODE_YEAR,
                (
                    "REGION",
                    "TECHNOLOGY",
                    "MODE_OF_OPERATION",
                    "PREVIOUS_YEAR",
                ),
            ),
        ),
        description="Límite al decremento anual de actividad por modo.",
    ),
    "UDC1_UserDefinedConstraintInequality": ConstraintSpec(
        index_names=("REGION", "UDC", "YEAR"),
        parameters=(
            _ps(
                "UDCMultiplierTotalCapacity",
                ("REGION", "TECHNOLOGY", "UDC", "YEAR"),
                ("REGION", None, "UDC", "YEAR"),
            ),
            _ps(
                "UDCMultiplierNewCapacity",
                ("REGION", "TECHNOLOGY", "UDC", "YEAR"),
                ("REGION", None, "UDC", "YEAR"),
            ),
            _ps(
                "UDCMultiplierActivity",
                ("REGION", "TECHNOLOGY", "UDC", "YEAR"),
                ("REGION", None, "UDC", "YEAR"),
            ),
            _ps(
                "UDCConstant",
                ("REGION", "UDC", "YEAR"),
                ("REGION", "UDC", "YEAR"),
            ),
            _ps("UDCTag", ("REGION", "UDC"), ("REGION", "UDC")),
        ),
        description="User-Defined Constraint (desigualdad).",
    ),
    "UDC2_UserDefinedConstraintEquality": ConstraintSpec(
        index_names=("REGION", "UDC", "YEAR"),
        parameters=(
            _ps(
                "UDCMultiplierTotalCapacity",
                ("REGION", "TECHNOLOGY", "UDC", "YEAR"),
                ("REGION", None, "UDC", "YEAR"),
            ),
            _ps(
                "UDCMultiplierNewCapacity",
                ("REGION", "TECHNOLOGY", "UDC", "YEAR"),
                ("REGION", None, "UDC", "YEAR"),
            ),
            _ps(
                "UDCMultiplierActivity",
                ("REGION", "TECHNOLOGY", "UDC", "YEAR"),
                ("REGION", None, "UDC", "YEAR"),
            ),
            _ps(
                "UDCConstant",
                ("REGION", "UDC", "YEAR"),
                ("REGION", "UDC", "YEAR"),
            ),
            _ps("UDCTag", ("REGION", "UDC"), ("REGION", "UDC")),
        ),
        description="User-Defined Constraint (igualdad).",
    ),
    "RateOfStorageCharge_constraint": _STORAGE_RATE_SPEC,
    "RateOfStorageDischarge_constraint": _STORAGE_RATE_SPEC,
    "NetChargeWithinYear_constraint": _STORAGE_FLOW_SPEC,
    "NetChargeWithinDay_constraint": _STORAGE_FLOW_SPEC,
    "StorageLevelYearStart_constraint": _STORAGE_YEAR_SPEC,
    "StorageLevelYearFinish_constraint": _STORAGE_YEAR_SPEC,
    "StorageLevelSeasonStart_constraint": ConstraintSpec(
        index_names=("REGION", "STORAGE", "SEASON", "YEAR"),
        parameters=_STORAGE_YEAR_SPEC.parameters,
        description="Nivel de storage al inicio de cada estación.",
    ),
    "StorageLevelDayTypeStart_constraint": ConstraintSpec(
        index_names=("REGION", "STORAGE", "SEASON", "DAYTYPE", "YEAR"),
        parameters=_STORAGE_FLOW_SPEC.parameters,
        description="Nivel de storage al inicio de cada tipo de día.",
    ),
    "StorageLevelDayTypeFinish_constraint": ConstraintSpec(
        index_names=("REGION", "STORAGE", "SEASON", "DAYTYPE", "YEAR"),
        parameters=_STORAGE_FLOW_SPEC.parameters,
        description="Nivel de storage al final de cada tipo de día.",
    ),
    "LowerLimit_1TimeBracket1InstanceOfDayType1week_constraint": _STORAGE_FLOW_SPEC,
    "LowerLimit_EndDaylyTimeBracketLastInstanceOfDayType1Week_constraint": _STORAGE_FLOW_SPEC,
    "LowerLimit_EndDaylyTimeBracketLastInstanceOfDayTypeLastWeek_constraint": _STORAGE_FLOW_SPEC,
    "LowerLimit_1TimeBracket1InstanceOfDayTypeLastweek_constraint": _STORAGE_FLOW_SPEC,
    "UpperLimit_1TimeBracket1InstanceOfDayType1week_constraint": _STORAGE_FLOW_SPEC,
    "UpperLimit_EndDaylyTimeBracketLastInstanceOfDayType1Week_constraint": _STORAGE_FLOW_SPEC,
    "UpperLimit_EndDaylyTimeBracketLastInstanceOfDayTypeLastWeek_constraint": _STORAGE_FLOW_SPEC,
    "UpperLimit_1TimeBracket1InstanceOfDayTypeLastweek_constraint": _STORAGE_FLOW_SPEC,
    "MaxChargeConstraint_constraint": _STORAGE_FLOW_SPEC,
    "MaxDischargeConstraint_constraint": _STORAGE_FLOW_SPEC,
    "StorageUpperLimit_constraint": _STORAGE_YEAR_SPEC,
    "StorageLowerLimit_constraint": _STORAGE_YEAR_SPEC,
    "TotalNewStorage_constraint": _STORAGE_YEAR_SPEC,
}


# =====================================================================
# Parser de nombres Pyomo
# =====================================================================


_NAME_RE = re.compile(r"^([A-Za-z_][\w]*)\[(.*)\]$")
_CANON_RE = re.compile(r"[^A-Za-z0-9]+")

# Nombre "LP" tal como lo escribe Pyomo o lo devuelve HiGHS después de leer el
# LP. Captura el tipo (antes del paréntesis/corchete) y los índices (dentro).
# - Acepta prefijos CPLEX-LP ``c_e_``/``c_l_``/``c_u_`` (equality/lower/upper).
# - Acepta forma Pyomo con corchetes y comas: ``Name[a,b,c]``.
# - Acepta forma LP con paréntesis y guiones bajos: ``Name(a_b_c)_`` (trailing ``_`` opcional).
_LP_NAME_RE = re.compile(r"^(?:c_[elu]_)?([A-Za-z_][\w]*)[\(\[]([^)\]]*)[\)\]]_?$")


def _parse_lp_or_pyomo_name(name: str) -> tuple[str, list[str]] | None:
    """Devuelve ``(type, tokens)`` para nombres Pyomo o LP.

    Ejemplos:
        >>> _parse_lp_or_pyomo_name('EnergyBalanceEachYear4[RE1,TERMPW,2022]')
        ('EnergyBalanceEachYear4', ['RE1', 'TERMPW', '2022'])
        >>> _parse_lp_or_pyomo_name('c_u_EnergyBalanceEachYear4(RE1_TERMPW_2022)_')
        ('EnergyBalanceEachYear4', ['RE1', 'TERMPW', '2022'])
        >>> _parse_lp_or_pyomo_name('NewCapacity(RE1_DEMAGFDSL_2022)')
        ('NewCapacity', ['RE1', 'DEMAGFDSL', '2022'])
    """
    m = _LP_NAME_RE.match((name or "").strip())
    if not m:
        return None
    type_ = m.group(1)
    inner = m.group(2) or ""
    if "," in inner:
        tokens = [t.strip() for t in inner.split(",") if t.strip()]
    else:
        tokens = [t.strip() for t in inner.split("_") if t.strip()]
    return type_, tokens


_YEAR_MIN, _YEAR_MAX = 1900, 2200


def _extract_region_tech_year(
    tokens: list[str],
) -> tuple[str | None, str | None, int | None]:
    """Heurística OSeMOSYS: primer token = REGION, último token 4-dígitos = YEAR,
    lo del medio (puede contener ``_``) = TECH/FUEL.

    Técnicas con guión bajo en el código (ej. ``DEMINDBAGFUR_LOW``) se manejan
    correctamente porque se reúnen los tokens intermedios con ``_``.
    """
    if not tokens:
        return None, None, None
    year: int | None = None
    last = tokens[-1]
    if last.isdigit() and len(last) == 4 and _YEAR_MIN <= int(last) <= _YEAR_MAX:
        year = int(last)
        rest = tokens[:-1]
    else:
        rest = tokens
    region = rest[0] if rest else None
    middle = rest[1:] if len(rest) > 1 else []
    tech_or_fuel = "_".join(middle) if middle else None
    return region, tech_or_fuel, year


def _build_overview(
    iis: IISReport,
    analyses: list["ConstraintAnalysis"],
) -> InfeasibilityOverview:
    """Deduplica años, tipos de restricción/variable y tecnologías/combustibles.

    Las restricciones se leen preferentemente de ``analyses`` (ya trae los índices
    parseados desde el mapa estático); las variables siempre vienen de
    ``iis.variable_names`` en formato LP y se parsean aquí.
    """
    from collections import Counter

    years: set[int] = set()
    ctypes: Counter = Counter()
    vtypes: Counter = Counter()
    techs: Counter = Counter()

    # Restricciones: si analyses trae la tabla IIS ya mapeada, úsala.
    if analyses:
        for a in analyses:
            ctypes[a.constraint_type or "?"] += 1
            idx = a.indices or {}
            y_raw = idx.get("YEAR")
            if y_raw is not None:
                try:
                    y = int(str(y_raw))
                    if _YEAR_MIN <= y <= _YEAR_MAX:
                        years.add(y)
                except (TypeError, ValueError):
                    pass
            tf = idx.get("TECHNOLOGY") or idx.get("FUEL") or idx.get("EMISSION")
            if tf:
                techs[str(tf)] += 1
    else:
        # Fallback: parsear directamente nombres del IIS.
        for name in iis.constraint_names:
            parsed = _parse_lp_or_pyomo_name(name)
            if not parsed:
                continue
            t, tokens = parsed
            ctypes[t] += 1
            _, tf, y = _extract_region_tech_year(tokens)
            if tf:
                techs[tf] += 1
            if y is not None:
                years.add(y)

    # Variables: siempre vienen del IIS en formato LP.
    for name in iis.variable_names:
        parsed = _parse_lp_or_pyomo_name(name)
        if not parsed:
            continue
        t, tokens = parsed
        vtypes[t] += 1
        _, tf, y = _extract_region_tech_year(tokens)
        if tf:
            techs[tf] += 1
        if y is not None:
            years.add(y)

    return InfeasibilityOverview(
        years=sorted(years),
        constraint_types=dict(ctypes),
        variable_types=dict(vtypes),
        techs_or_fuels=dict(techs),
        total_constraints=len(iis.constraint_names) or sum(ctypes.values()),
        total_variables=len(iis.variable_names),
    )


_LP_CON_PREFIX_RE = re.compile(r"^c_[elu]_", re.IGNORECASE)


def _canon_name(name: str) -> str:
    """Canoniza un nombre de restricción/variable para hacer matching robusto.

    Pyomo usa ``Name[i,j]``; al escribir LP con ``symbolic_solver_labels=True`` el
    writer transforma a ``Name(i_j)_`` (paréntesis, guiones bajos y a veces un
    sufijo ``_``). CPLEX-LP antepone además ``c_e_``/``c_l_``/``c_u_`` a las
    restricciones. Antes de reducir a alfanuméricos eliminamos ese prefijo para
    que el match entre el nombre Pyomo y el del LP sea estable.
    """
    stripped = _LP_CON_PREFIX_RE.sub("", name or "")
    return _CANON_RE.sub("", stripped).lower()


def parse_constraint_name(qualified_name: str) -> tuple[str, list[str]]:
    """Extrae ``(prefix, tokens)`` de un nombre Pyomo.

    Ejemplos
    --------
    >>> parse_constraint_name("EnergyBalanceEachTS5[COL,L1,ELEC,2030]")
    ('EnergyBalanceEachTS5', ['COL', 'L1', 'ELEC', '2030'])
    >>> parse_constraint_name("DiscountedCost_constraint")
    ('DiscountedCost_constraint', [])
    """
    m = _NAME_RE.match(qualified_name)
    if not m:
        return qualified_name, []
    prefix = m.group(1)
    raw = m.group(2)
    # Pyomo separa índices por ","; los tokens no suelen contener comas.
    tokens = [t.strip() for t in raw.split(",")]
    return prefix, tokens


def _fallback_indices(tokens: list[str]) -> dict[str, str]:
    """Detección posicional de índices para tipos de restricción sin mapeo estático.

    Heurística: detecta YEAR (4 dígitos 2000–2200), luego asigna REGION al
    primer token restante y TECHNOLOGY al segundo.
    """
    result: dict[str, str] = {}
    remaining = list(tokens)
    for i, t in enumerate(remaining):
        if re.match(r"^\d{4}$", t) and 2000 <= int(t) <= 2200:
            result["YEAR"] = t
            remaining.pop(i)
            break
    if remaining:
        result["REGION"] = remaining.pop(0)
    if remaining:
        result["TECHNOLOGY"] = remaining.pop(0)
    if remaining:
        result["OTHER"] = ",".join(remaining)
    return result


def constraint_indices(prefix: str, tokens: list[str]) -> dict[str, str]:
    """Mapea tokens a los nombres de índice de la restricción según el mapa estático.

    Si el ``prefix`` no está registrado o la cantidad de tokens no coincide,
    usa detección posicional genérica (YEAR, REGION, TECHNOLOGY).
    """
    spec = CONSTRAINT_PARAM_MAP.get(prefix)
    if spec is not None and len(tokens) == len(spec.index_names):
        return dict(zip(spec.index_names, tokens))
    return _fallback_indices(tokens)


# =====================================================================
# Lector de CSVs
# =====================================================================


@lru_cache(maxsize=128)
def _load_param_csv_cached(csv_dir: str, param: str) -> pd.DataFrame | None:
    """Carga ``<csv_dir>/<param>.csv`` con cache. Devuelve ``None`` si no existe."""
    path = Path(csv_dir) / f"{param}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # pragma: no cover - logs y degradación
        logger.warning("No se pudo leer %s: %s", path, exc)
        return None
    return df


def clear_csv_cache() -> None:
    """Limpia la caché interna de CSVs (útil entre corridas distintas)."""
    _load_param_csv_cached.cache_clear()


def load_param_values(csv_dir: Path | str, param: str) -> pd.DataFrame | None:
    """Carga el CSV de un parámetro (con cache)."""
    return _load_param_csv_cached(str(Path(csv_dir)), param)


# =====================================================================
# Extracción de valores relevantes
# =====================================================================


@dataclass
class ParamHit:
    param: str
    indices: dict[str, str]
    value: float | None
    is_default: bool
    #: Valor por defecto canónico del modelo OSeMOSYS (si se conoce).
    default_value: float | None = None
    #: Diferencia absoluta valor - default.
    diff_abs: float | None = None
    #: Score normalizado 0-100 de desviación del default. Ver `_deviation_score`.
    deviation_score: float | None = None


def _deviation_score(value: float | None, default: float | None) -> float | None:
    """Normaliza la desviación entre valor y default a un score 0-100.

    Casos:
      * ``value`` o ``default`` None → None (no evaluable).
      * Iguales → 0.
      * default == 0 y value ≠ 0 → 100 (máxima desviación relativa conceptual).
      * En otro caso: ``|v-d| / max(|d|, |v|, 1e-12) * 100``.

    Diseño:
      * Simétrico en v y d para valores del mismo signo.
      * Siempre acotado en [0, 100].
      * No necesita histogramas globales ni tamaños de rango por parámetro.
    """
    if value is None or default is None:
        return None
    try:
        v = float(value)
        d = float(default)
    except (TypeError, ValueError):
        return None
    if v == d:
        return 0.0
    if d == 0.0 and v != 0.0:
        return 100.0
    denom = max(abs(d), abs(v), 1e-12)
    rel = abs(v - d) / denom
    # Clamp por robustez.
    rel = min(max(rel, 0.0), 1.0)
    return round(rel * 100.0, 2)


def _filter_param(
    df: pd.DataFrame,
    spec: ParamSpec,
    constraint_indices_map: dict[str, str],
) -> pd.DataFrame:
    """Aplica los filtros que podamos derivar de los índices de la restricción."""
    filtered = df
    for col_name, derive_key in zip(spec.index_names, spec.derive_from):
        if derive_key is None:
            continue
        key_val = constraint_indices_map.get(derive_key)
        if key_val is None or col_name not in filtered.columns:
            continue
        # CSVs de OSeMOSYS usan strings en columnas de índice; forzamos comparación textual.
        filtered = filtered[filtered[col_name].astype(str) == str(key_val)]
        if filtered.empty:
            break
    return filtered


def _resolve_default(param_name: str) -> float | None:
    """Devuelve el default canónico OSeMOSYS para ``param_name``, o ``None``.

    Reutiliza la fuente única de verdad en
    :mod:`app.simulation.core.osemosys_defaults` (módulo puro sin dependencias
    pesadas). Distingue "default definido = 0" de "sin default conocido"
    mediante :func:`has_known_default`.
    """
    try:
        from app.simulation.core.osemosys_defaults import (  # noqa: WPS433
            get_param_default,
            has_known_default,
        )
    except Exception:
        return None
    if not has_known_default(param_name):
        return None
    try:
        return get_param_default(param_name)
    except Exception:
        return None


def _enrich_hit(hit: ParamHit) -> ParamHit:
    """Completa ``default_value``, ``diff_abs`` y ``deviation_score`` en sitio."""
    hit.default_value = _resolve_default(hit.param)
    if hit.value is not None and hit.default_value is not None:
        try:
            hit.diff_abs = float(hit.value) - float(hit.default_value)
        except Exception:
            hit.diff_abs = None
    hit.deviation_score = _deviation_score(hit.value, hit.default_value)
    return hit


def values_for_constraint(
    csv_dir: Path | str,
    prefix: str,
    indices: dict[str, str],
    *,
    max_rows_per_param: int = 25,
) -> list[ParamHit]:
    """Devuelve las filas relevantes de cada parámetro asociado a la restricción.

    Si el parámetro no existe como CSV o no quedan filas tras el filtro,
    emite una sola fila marcada ``is_default=True`` y ``value=None``, como señal
    de que probablemente está usando el valor default de OSeMOSYS. En todos los
    casos se añade ``default_value``, ``diff_abs`` y ``deviation_score`` cuando
    se pueden computar (ver :func:`_deviation_score`).
    """
    spec = CONSTRAINT_PARAM_MAP.get(prefix)
    if spec is None:
        return []

    hits: list[ParamHit] = []
    for param_spec in spec.parameters:
        df = load_param_values(csv_dir, param_spec.name)
        if df is None:
            hits.append(
                _enrich_hit(
                    ParamHit(
                        param=param_spec.name,
                        indices={},
                        value=None,
                        is_default=True,
                    )
                )
            )
            continue

        filtered = _filter_param(df, param_spec, indices)
        if filtered.empty:
            hits.append(
                _enrich_hit(
                    ParamHit(
                        param=param_spec.name,
                        indices={},
                        value=None,
                        is_default=True,
                    )
                )
            )
            continue

        # El valor suele llamarse "VALUE"; si no existe, tomamos la última columna.
        value_col = "VALUE" if "VALUE" in filtered.columns else filtered.columns[-1]
        rows = filtered.head(max_rows_per_param)
        for _, row in rows.iterrows():
            row_indices = {
                col: str(row[col])
                for col in param_spec.index_names
                if col in filtered.columns
            }
            try:
                val = float(row[value_col])
            except Exception:
                val = None
            hits.append(
                _enrich_hit(
                    ParamHit(
                        param=param_spec.name,
                        indices=row_indices,
                        value=val,
                        is_default=False,
                    )
                )
            )
    return hits


# =====================================================================
# IIS / diagnóstico de infactibilidad (HiGHS IIS · GLPK --nopresol)
# =====================================================================


@dataclass
class IISReport:
    available: bool
    method: str | None
    constraint_names: list[str] = field(default_factory=list)
    variable_names: list[str] = field(default_factory=list)
    #: Conflictos por cota de variable reportados por Gurobi (`IISLB` / `IISUB`)
    #: o HiGHS (`HighsIis.col_bound_`). Una cota ``boxed`` de HiGHS genera
    #: dos entradas, una LB y otra UB.
    #: Cada entry: ``{"name": "<varname>", "side": "LB" | "UB"}``.
    bound_conflicts: list[dict[str, str]] = field(default_factory=list)
    #: Ruta absoluta al ``.ilp`` generado por Gurobi (``Model.write``). ``None``
    #: cuando el solver no es Gurobi o no se pudo escribir.
    ilp_path: str | None = None
    unavailable_reason: str | None = None
    irreducible: bool = False
    timed_out: bool = False
    elapsed_seconds: float | None = None
    time_limit_seconds: float | None = None
    glpk_violations: list[dict] = field(default_factory=list)


_LP_BOUND_TYPE: dict[str, str] = {"c_u_": "upper", "c_l_": "lower", "c_e_": "equality"}


def _parse_glpk_violations(output_path: Path) -> list[dict]:
    """Parsea el archivo de solución de glpsol buscando restricciones violadas.

    GLPK escribe nombres LP largos en una línea y sus estadísticas en la
    siguiente cuando el nombre supera el ancho de columna.  Detecta prefijos
    ``c_u_`` (upper), ``c_l_`` (lower) y ``c_e_`` (equality) que Pyomo genera
    con ``symbolic_solver_labels=True``.  Tolerancia: 0.01 (igual que la guía
    de diagnóstico manual).

    Retorna lista de dicts ``{lp_name, act, bound, bound_type, diff_abs}``
    ordenada de mayor a menor ``diff_abs``, limitada a 200 entradas.
    """
    _TOL = 0.01

    with output_path.open("r", errors="replace") as f:
        lines = f.readlines()

    details: list[dict] = []
    seen: set[str] = set()

    for i in range(len(lines) - 1):
        line1 = lines[i]
        line2 = lines[i + 1]

        if "c_u_" not in line1 and "c_l_" not in line1 and "c_e_" not in line1:
            continue

        name_match = re.search(r"(c_[ule]_\S+)", line1)
        if not name_match:
            continue

        name = name_match.group(1).rstrip("_:")
        bound_type = next(
            (bt for pfx, bt in _LP_BOUND_TYPE.items() if pfx in name), "lower"
        )

        parts = line2.split()
        if len(parts) < 3:
            continue

        try:
            act = float(parts[1])
            bound = float(parts[2])
        except (ValueError, IndexError):
            continue

        if bound_type == "upper":
            is_violated = act > bound + _TOL
            diff_abs = max(0.0, act - bound)
        else:
            is_violated = act < bound - _TOL
            diff_abs = max(0.0, bound - act)

        if is_violated and name not in seen:
            details.append(
                {
                    "lp_name": name,
                    "act": act,
                    "bound": bound,
                    "bound_type": bound_type,
                    "diff_abs": diff_abs,
                }
            )
            seen.add(name)

    details.sort(key=lambda d: -d["diff_abs"])
    return details[:200]


def _try_violations_glpk(
    lp_path: Path,
    *,
    timeout_seconds: int = 1500,
) -> IISReport:
    """Diagnostica infactibilidades con GLPK usando ``glpsol --nopresol``.

    No produce un IIS verdadero: ejecuta el simplex completo sobre el LP
    (saltando el preprocesamiento) y reporta las restricciones cuya actividad
    viola sus cotas en la solución degenerada.  Esto es suficiente para
    alimentar ``CONSTRAINT_PARAM_MAP`` y generar param-hits con deviation scores.

    Puede tardar de segundos a ~15 min según el tamaño del modelo.
    """
    output_path = lp_path.parent / (lp_path.stem + "_glpk_violations.txt")

    try:
        subprocess.run(
            ["glpsol", "--lp", str(lp_path), "--nopresol", "-o", str(output_path)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return IISReport(
            available=False,
            method=None,
            unavailable_reason="glpsol no encontrado en PATH; instala GLPK para usar este diagnóstico.",
        )
    except subprocess.TimeoutExpired:
        return IISReport(
            available=False,
            method="glpk_nopresol",
            unavailable_reason=f"glpsol --nopresol excedió el timeout de {timeout_seconds}s ({timeout_seconds // 60} min).",
        )
    except Exception as exc:
        return IISReport(
            available=False,
            method=None,
            unavailable_reason=f"Error al ejecutar glpsol: {exc!r}",
        )

    try:
        details = _parse_glpk_violations(output_path)
    except Exception as exc:
        return IISReport(
            available=False,
            method=None,
            unavailable_reason=f"Error al parsear salida de GLPK: {exc!r}",
        )
    finally:
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass

    if not details:
        return IISReport(
            available=False,
            method="glpk_nopresol",
            unavailable_reason="GLPK --nopresol no reportó restricciones violadas.",
        )

    return IISReport(
        available=True,
        method="glpk_nopresol",
        constraint_names=[d["lp_name"] for d in details],
        variable_names=[],
        glpk_violations=details,
    )


def _try_import_highspy() -> tuple[Any | None, str | None]:
    try:
        import highspy  # type: ignore

        return highspy, None
    except Exception as exc:  # pragma: no cover - depende del entorno
        return None, f"highspy no disponible: {exc!r}"


@dataclass
class DualRayRow:
    name: str
    weight: float
    selected_side: str
    constraint_type: str
    indices: dict[str, str]


@dataclass
class PrimalRayVariable:
    name: str
    direction: float


@dataclass
class DualRayReport:
    available: bool
    certificate_type: str = "dual_ray"
    method: str | None = None
    validated: bool = False
    certificate_margin: float | None = None
    rows: list[DualRayRow] = field(default_factory=list)
    variables: list[PrimalRayVariable] = field(default_factory=list)
    unavailable_reason: str | None = None


@dataclass
class RelaxationEntry:
    name: str
    constraint_type: str
    indices: dict[str, str]
    side: str
    activity: float
    bound: float
    slack: float
    normalized_slack: float
    penalty: float
    weighted_cost: float
    suggested_change: str


@dataclass
class FeasibilityRelaxationReport:
    available: bool
    method: str | None = None
    objective: float | None = None
    solution_value_valid: bool = False
    normalization: str = "row_scale_v1"
    relaxations: list[RelaxationEntry] = field(default_factory=list)
    elapsed_seconds: float | None = None
    time_limit_seconds: float | None = None
    unavailable_reason: str | None = None


def _highs_status_is_ok(highspy: Any, status: Any) -> bool:
    return status == getattr(highspy.HighsStatus, "kOk", None)


def _diagnostic_time_limit_seconds(env_name: str, default: float = 300.0) -> float:
    """Lee un límite positivo de fase diagnóstica sin aceptar valores inválidos."""
    try:
        value = float(os.getenv(env_name, str(default)))
    except (TypeError, ValueError):
        value = default
    return value if value > 0 else default


def _map_lp_row_name(name: str, pyomo_by_canon: dict[str, str]) -> tuple[str, str, dict[str, str]]:
    pyomo_name = pyomo_by_canon.get(_canon_name(name), name)
    prefix, tokens = parse_constraint_name(pyomo_name)
    if not tokens:
        parsed = _parse_lp_or_pyomo_name(name)
        if parsed:
            prefix, tokens = parsed
    return pyomo_name, prefix, constraint_indices(prefix, tokens)


def _validate_dual_ray_certificate(lp: Any, ray: list[float]) -> tuple[bool, float | None]:
    """Valida la contradicción Farkas usando filas y bounds de columnas.

    Para cada multiplicador positivo usa el lower de la fila y para cada
    multiplicador negativo usa el upper. La combinación exige ``c'x >= beta``;
    si el máximo posible de ``c'x`` bajo bounds de columnas es menor que beta,
    existe una contradicción certificada.
    """
    import math

    row_lower = list(lp.row_lower_ or [])
    row_upper = list(lp.row_upper_ or [])
    beta = 0.0
    for idx, weight in enumerate(ray):
        if abs(weight) <= 1e-12:
            continue
        bound = row_lower[idx] if weight > 0 else row_upper[idx]
        if not math.isfinite(float(bound)):
            return False, None
        beta += weight * float(bound)

    matrix = lp.a_matrix_
    num_cols = int(getattr(matrix, "num_col_", len(lp.col_names_)))
    coefficients = [0.0] * num_cols
    starts = list(getattr(matrix, "start_", []) or [])
    indices = list(getattr(matrix, "index_", []) or [])
    values = list(getattr(matrix, "value_", []) or [])
    matrix_format = int(getattr(matrix, "format_", 1))
    if matrix_format == 1:  # column-wise: indices are row indices
        for col in range(num_cols):
            start = starts[col]
            end = starts[col + 1] if col + 1 < len(starts) else len(indices)
            coefficients[col] = sum(
                float(values[pos]) * ray[int(indices[pos])]
                for pos in range(start, end)
            )
    else:  # row-wise
        for row in range(len(ray)):
            start = starts[row]
            end = starts[row + 1] if row + 1 < len(starts) else len(indices)
            for pos in range(start, end):
                coefficients[int(indices[pos])] += float(values[pos]) * ray[row]

    col_lower = list(lp.col_lower_ or [])
    col_upper = list(lp.col_upper_ or [])
    max_lhs = 0.0
    for col, coefficient in enumerate(coefficients):
        if abs(coefficient) <= 1e-10:
            continue
        bound = col_upper[col] if coefficient > 0 else col_lower[col]
        if not math.isfinite(float(bound)):
            return False, None
        max_lhs += coefficient * float(bound)
    margin = beta - max_lhs
    tolerance = 1e-7 * max(1.0, abs(beta), abs(max_lhs))
    return margin > tolerance, margin


def try_compute_dual_ray(
    instance: Any | None,
    solver_name: str,
    *,
    lp_path: Path | None,
) -> DualRayReport:
    """Obtiene y valida un certificado Farkas para un LP HiGHS infactible."""
    if str(solver_name or "").lower() != "highs":
        return DualRayReport(
            available=False,
            unavailable_reason="Dual ray implementado únicamente para HiGHS.",
        )
    if lp_path is None or not Path(lp_path).exists():
        return DualRayReport(available=False, unavailable_reason="No hay LP para calcular dual ray.")
    highspy, err = _try_import_highspy()
    if highspy is None:
        return DualRayReport(available=False, unavailable_reason=err)

    try:
        highs = highspy.Highs()
        highs.setOptionValue("output_flag", False)
        # El solve previo a getDualRay también debe estar acotado: el presupuesto
        # de IIS no lo protege y una ruta simplex regional puede ser muy lenta.
        time_limit = _diagnostic_time_limit_seconds(
            "OSEMOSYS_DUAL_RAY_TIME_LIMIT_SECONDS"
        )
        # HiGHS sólo expone un Farkas ray cuando la certificación se obtiene
        # desde simplex; `choose` puede seleccionar IPM y dejar has_ray=False.
        highs.setOptionValue("solver", "simplex")
        highs.setOptionValue("time_limit", time_limit)
        read_status = highs.readModel(str(lp_path))
        if read_status == getattr(highspy.HighsStatus, "kError", None):
            return DualRayReport(available=False, unavailable_reason=f"readModel falló: {read_status}")
        run_status = highs.run()
        if not _highs_status_is_ok(highspy, run_status):
            return DualRayReport(available=False, unavailable_reason=f"run falló: {run_status}")
        if highs.getModelStatus() != getattr(highspy.HighsModelStatus, "kInfeasible", None):
            return DualRayReport(
                available=False,
                unavailable_reason=f"HiGHS no certificó infactibilidad: {highs.getModelStatus()}.",
            )
        ray_status, has_ray, raw_ray = highs.getDualRay()
        if not _highs_status_is_ok(highspy, ray_status) or not has_ray:
            return DualRayReport(
                available=False,
                unavailable_reason=f"HiGHS no produjo dual ray: status={ray_status}.",
            )
        ray = [float(value) for value in raw_ray]
        lp = highs.getLp()
        validated, margin = _validate_dual_ray_certificate(lp, ray)
        row_names = list(lp.row_names_ or [])
        pyomo_by_canon = _pyomo_names_by_canon(instance)
        rows: list[DualRayRow] = []
        for idx, weight in enumerate(ray):
            if abs(weight) <= 1e-10 or idx >= len(row_names):
                continue
            name, prefix, indices_map = _map_lp_row_name(row_names[idx], pyomo_by_canon)
            rows.append(
                DualRayRow(
                    name=name,
                    weight=weight,
                    selected_side="LB" if weight > 0 else "UB",
                    constraint_type=prefix,
                    indices=indices_map,
                )
            )
        rows.sort(key=lambda row: -abs(row.weight))
        return DualRayReport(
            available=True,
            method="highs.getDualRay",
            validated=validated,
            certificate_margin=margin,
            rows=rows[:200],
            unavailable_reason=(
                None
                if validated
                else "HiGHS entregó un ray, pero la validación independiente con bounds no fue concluyente."
            ),
        )
    except Exception as exc:
        logger.exception("Falló el cálculo del dual ray")
        return DualRayReport(available=False, unavailable_reason=f"Dual ray falló: {exc!r}")


def _validate_primal_ray(lp: Any, direction: list[float]) -> tuple[bool, float | None]:
    """Valida dirección de recesión y mejora del objetivo de un primal ray."""
    import math

    tolerance = 1e-8
    matrix = lp.a_matrix_
    starts = list(getattr(matrix, "start_", []) or [])
    indices = list(getattr(matrix, "index_", []) or [])
    values = list(getattr(matrix, "value_", []) or [])
    row_direction = [0.0] * len(lp.row_names_)
    matrix_format = int(getattr(matrix, "format_", 1))
    if matrix_format == 1:
        for col, col_direction in enumerate(direction):
            if abs(col_direction) <= tolerance:
                continue
            start = starts[col]
            end = starts[col + 1] if col + 1 < len(starts) else len(indices)
            for pos in range(start, end):
                row_direction[int(indices[pos])] += float(values[pos]) * col_direction
    else:
        for row in range(len(row_direction)):
            start = starts[row]
            end = starts[row + 1] if row + 1 < len(starts) else len(indices)
            row_direction[row] = sum(
                float(values[pos]) * direction[int(indices[pos])]
                for pos in range(start, end)
            )

    for idx, delta in enumerate(row_direction):
        has_lower = math.isfinite(float(lp.row_lower_[idx]))
        has_upper = math.isfinite(float(lp.row_upper_[idx]))
        if has_lower and has_upper and abs(delta) > tolerance:
            return False, None
        if has_lower and not has_upper and delta < -tolerance:
            return False, None
        if has_upper and not has_lower and delta > tolerance:
            return False, None

    for idx, delta in enumerate(direction):
        has_lower = math.isfinite(float(lp.col_lower_[idx]))
        has_upper = math.isfinite(float(lp.col_upper_[idx]))
        if has_lower and has_upper and abs(delta) > tolerance:
            return False, None
        if has_lower and not has_upper and delta < -tolerance:
            return False, None
        if has_upper and not has_lower and delta > tolerance:
            return False, None

    objective_direction = sum(
        float(cost) * delta for cost, delta in zip(lp.col_cost_, direction)
    )
    # ObjSense: 1=minimize, -1=maximize. Mejora si sense*c'd < 0.
    signed_improvement = -float(int(lp.sense_)) * objective_direction
    return signed_improvement > tolerance, signed_improvement


def try_compute_primal_ray(
    solver_name: str,
    *,
    lp_path: Path | None,
) -> DualRayReport:
    """Obtiene una dirección de no acotación para un LP HiGHS."""
    if str(solver_name or "").lower() != "highs":
        return DualRayReport(
            available=False,
            certificate_type="primal_ray",
            unavailable_reason="Primal ray implementado únicamente para HiGHS.",
        )
    if lp_path is None or not Path(lp_path).exists():
        return DualRayReport(
            available=False,
            certificate_type="primal_ray",
            unavailable_reason="No hay LP para calcular primal ray.",
        )
    highspy, err = _try_import_highspy()
    if highspy is None:
        return DualRayReport(
            available=False,
            certificate_type="primal_ray",
            unavailable_reason=err,
        )
    try:
        highs = highspy.Highs()
        highs.setOptionValue("output_flag", False)
        highs.setOptionValue(
            "time_limit",
            _diagnostic_time_limit_seconds("OSEMOSYS_PRIMAL_RAY_TIME_LIMIT_SECONDS"),
        )
        read_status = highs.readModel(str(lp_path))
        if read_status == getattr(highspy.HighsStatus, "kError", None):
            return DualRayReport(
                available=False,
                certificate_type="primal_ray",
                unavailable_reason=f"readModel falló: {read_status}",
            )
        run_status = highs.run()
        if not _highs_status_is_ok(highspy, run_status):
            return DualRayReport(
                available=False,
                certificate_type="primal_ray",
                unavailable_reason=f"run falló: {run_status}",
            )
        if highs.getModelStatus() != getattr(highspy.HighsModelStatus, "kUnbounded", None):
            return DualRayReport(
                available=False,
                certificate_type="primal_ray",
                unavailable_reason=f"HiGHS no certificó no acotación: {highs.getModelStatus()}.",
            )
        ray_status, has_ray, raw_ray = highs.getPrimalRay()
        if not _highs_status_is_ok(highspy, ray_status) or not has_ray:
            return DualRayReport(
                available=False,
                certificate_type="primal_ray",
                unavailable_reason=f"HiGHS no produjo primal ray: status={ray_status}.",
            )
        lp = highs.getLp()
        direction = [float(value) for value in raw_ray]
        validated, improvement = _validate_primal_ray(lp, direction)
        names = list(lp.col_names_ or [])
        variables = [
            PrimalRayVariable(name=names[index], direction=float(value))
            for index, value in enumerate(direction)
            if index < len(names) and abs(float(value)) > 1e-10
        ]
        variables.sort(key=lambda variable: -abs(variable.direction))
        return DualRayReport(
            available=bool(variables),
            certificate_type="primal_ray",
            method="highs.getPrimalRay",
            validated=validated,
            certificate_margin=improvement,
            variables=variables[:200],
            unavailable_reason=(
                None
                if variables and validated
                else "El primal ray quedó vacío o no superó la validación algebraica."
            ),
        )
    except Exception as exc:
        logger.exception("Falló el cálculo del primal ray")
        return DualRayReport(
            available=False,
            certificate_type="primal_ray",
            unavailable_reason=f"Primal ray falló: {exc!r}",
        )


_RELAXATION_RIGID_FAMILIES = {
    "ConstraintCapacity",
    "PlannedMaintenance",
    "TotalNewCapacity_2",
    "AnnualEmissionProductionByMode",
    "AnnualEmissionProduction",
    "EmissionsAccounting1",
    "EmissionsAccounting2",
    "ReserveMargin_TechnologiesIncluded",
    "ReserveMargin_FuelsIncluded",
    "TotalModelHorizonTechnologyActivity",
    "RateOfStorageCharge_constraint",
    "RateOfStorageDischarge_constraint",
    "NetChargeWithinYear_constraint",
    "NetChargeWithinDay_constraint",
}
_RELAXATION_PROTECTED_FAMILIES = {
    "EnergyBalanceEachTS5",
    "EnergyBalanceEachYear4",
}


def _relaxation_family_weight(prefix: str) -> float:
    """Política v1: ecuaciones físicas/contables rígidas y demanda protegida."""
    if prefix in _RELAXATION_RIGID_FAMILIES:
        return 1_000_000.0
    if prefix in _RELAXATION_PROTECTED_FAMILIES:
        return 100.0
    if prefix in CONSTRAINT_PARAM_MAP:
        return 1.0
    return 1_000_000.0


def try_feasibility_relaxation(
    instance: Any | None,
    solver_name: str,
    *,
    lp_path: Path | None,
) -> FeasibilityRelaxationReport:
    """Cuantifica slacks mínimos sobre una copia HiGHS separada del LP."""
    if str(solver_name or "").lower() != "highs":
        return FeasibilityRelaxationReport(
            available=False,
            unavailable_reason="Feasibility relaxation implementada únicamente para HiGHS.",
        )
    if lp_path is None or not Path(lp_path).exists():
        return FeasibilityRelaxationReport(available=False, unavailable_reason="No hay LP para relajar.")
    highspy, err = _try_import_highspy()
    if highspy is None:
        return FeasibilityRelaxationReport(available=False, unavailable_reason=err)

    import math
    import numpy as np

    try:
        time_limit = float(os.getenv("OSEMOSYS_RELAXATION_TIME_LIMIT_SECONDS", "300"))
    except (TypeError, ValueError):
        time_limit = 300.0
    if time_limit <= 0:
        time_limit = 300.0

    try:
        highs = highspy.Highs()
        highs.setOptionValue("output_flag", False)
        highs.setOptionValue("time_limit", time_limit)
        read_status = highs.readModel(str(lp_path))
        if read_status == getattr(highspy.HighsStatus, "kError", None):
            return FeasibilityRelaxationReport(available=False, unavailable_reason=f"readModel falló: {read_status}")
        lp = highs.getLp()
        row_names = list(lp.row_names_ or [])
        row_lower = [float(value) for value in lp.row_lower_]
        row_upper = [float(value) for value in lp.row_upper_]
        pyomo_by_canon = _pyomo_names_by_canon(instance)

        scales: list[float] = []
        penalties: list[float] = []
        for name, lower, upper in zip(row_names, row_lower, row_upper):
            finite_bounds = [abs(value) for value in (lower, upper) if math.isfinite(value)]
            scale = max([1.0, *finite_bounds])
            _, prefix, _ = _map_lp_row_name(name, pyomo_by_canon)
            family_weight = _relaxation_family_weight(prefix)
            scales.append(scale)
            penalties.append(family_weight / scale)

        started = perf_counter()
        relax_status = highs.feasibilityRelaxation(
            1_000_000.0,
            1_000_000.0,
            1.0,
            None,
            None,
            np.asarray(penalties, dtype=float),
        )
        elapsed = perf_counter() - started
        solution = highs.getSolution()
        if not _highs_status_is_ok(highspy, relax_status) or not bool(solution.value_valid):
            return FeasibilityRelaxationReport(
                available=False,
                method="highs.feasibilityRelaxation",
                solution_value_valid=bool(solution.value_valid),
                elapsed_seconds=elapsed,
                time_limit_seconds=time_limit,
                unavailable_reason=f"Relajación sin solución válida: status={relax_status}.",
            )

        entries: list[RelaxationEntry] = []
        for idx, activity_raw in enumerate(solution.row_value):
            activity = float(activity_raw)
            lower = row_lower[idx]
            upper = row_upper[idx]
            side = ""
            bound = 0.0
            slack = 0.0
            suggestion = ""
            if math.isfinite(lower) and activity < lower - 1e-8:
                side, bound, slack = "LB", lower, lower - activity
                suggestion = f"Reducir el límite inferior al menos en {slack:.6g}."
            elif math.isfinite(upper) and activity > upper + 1e-8:
                side, bound, slack = "UB", upper, activity - upper
                suggestion = f"Aumentar el límite superior al menos en {slack:.6g}."
            if slack <= 0:
                continue
            name, prefix, indices_map = _map_lp_row_name(row_names[idx], pyomo_by_canon)
            normalized = slack / scales[idx]
            entries.append(
                RelaxationEntry(
                    name=name,
                    constraint_type=prefix,
                    indices=indices_map,
                    side=side,
                    activity=activity,
                    bound=bound,
                    slack=slack,
                    normalized_slack=normalized,
                    penalty=penalties[idx],
                    weighted_cost=slack * penalties[idx],
                    suggested_change=suggestion,
                )
            )
        entries.sort(key=lambda entry: (-entry.weighted_cost, -entry.normalized_slack))
        return FeasibilityRelaxationReport(
            available=bool(entries),
            method="highs.feasibilityRelaxation",
            objective=float(highs.getInfo().objective_function_value),
            solution_value_valid=True,
            relaxations=entries[:200],
            elapsed_seconds=elapsed,
            time_limit_seconds=time_limit,
            unavailable_reason=(None if entries else "La relajación no produjo slacks de filas; revisa conflictos directos de bounds."),
        )
    except Exception as exc:
        logger.exception("Falló feasibility relaxation")
        return FeasibilityRelaxationReport(
            available=False,
            method="highs.feasibilityRelaxation",
            time_limit_seconds=time_limit,
            unavailable_reason=f"Relajación falló: {exc!r}",
        )


def _try_import_gurobipy() -> tuple[Any | None, str | None]:
    try:
        import gurobipy  # type: ignore

        return gurobipy, None
    except Exception as exc:  # pragma: no cover - depende del entorno
        return None, f"gurobipy no disponible: {exc!r}"


def _release_gurobi(model: Any | None) -> None:
    """Libera el modelo y el environment default de gurobipy.

    Replica el patrón usado en :func:`solver._release_solver`: con licencia
    Single-Use mantener el ``Env`` vivo bloquea futuros solves; con WLS no
    bloquea pero igual liberamos por higiene.
    """
    if model is not None:
        try:
            model.dispose()
        except Exception:  # pragma: no cover
            logger.debug("Error disposing gurobi model", exc_info=True)
    try:
        import gurobipy as gp

        dispose_default = getattr(gp, "disposeDefaultEnv", None)
        if callable(dispose_default):
            dispose_default()
    except Exception:  # pragma: no cover
        pass


def _try_compute_iis_gurobi(
    lp_path: Path,
    *,
    ilp_out: Path | None = None,
) -> IISReport:
    """Calcula el IIS de un LP infactible usando ``gurobipy.Model.computeIIS``.

    Gurobi entrega un IIS minimal (``Model.IISMinimal == 1``) y diferencia
    conflictos de ``IISLB`` / ``IISUB`` por variable, además de las
    restricciones (``IISConstr``) y constraints generalizadas (``IISGenConstr``).
    Si se pasa ``ilp_out``, se escribe el subsistema como archivo ``.ilp``
    reproducible en cualquier herramienta LP.
    """
    gp, err = _try_import_gurobipy()
    if gp is None:
        return IISReport(available=False, method=None, unavailable_reason=err)

    GRB = getattr(gp, "GRB", None)
    if GRB is None:  # pragma: no cover
        return IISReport(
            available=False,
            method=None,
            unavailable_reason="gurobipy.GRB no disponible.",
        )

    model: Any | None = None
    try:
        try:
            model = gp.read(str(lp_path))
        except Exception as exc:
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=f"Gurobi no pudo leer el LP: {exc!r}",
            )

        # Silenciar logs y aplicar threads configurados (BD o env var).
        try:
            model.setParam("OutputFlag", 0)
        except Exception:  # pragma: no cover
            pass
        try:
            from app.core.config import get_settings  # noqa: WPS433
            from app.simulation.core.solver import (  # noqa: WPS433
                _effective_solver_threads,
                _resolve_solver_threads,
            )

            configured = _resolve_solver_threads(get_settings())
            threads = _effective_solver_threads(configured)
            if threads > 0:
                model.setParam("Threads", threads)
        except Exception:
            logger.debug(
                "No se pudo aplicar Threads al modelo Gurobi del IIS",
                exc_info=True,
            )

        try:
            model.optimize()
        except Exception as exc:
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=f"Gurobi optimize() falló: {exc!r}",
            )

        if model.status != GRB.INFEASIBLE:
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=(
                    f"Gurobi reporta status={model.status}; el modelo no es "
                    "infactible o terminó por otro motivo."
                ),
            )

        try:
            model.computeIIS()
        except Exception as exc:
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=f"Gurobi computeIIS() falló: {exc!r}",
            )

        constraint_names: list[str] = []
        try:
            for c in model.getConstrs():
                if int(getattr(c, "IISConstr", 0) or 0) == 1:
                    constraint_names.append(c.ConstrName)
        except Exception:  # pragma: no cover
            logger.debug("Error leyendo IISConstr", exc_info=True)

        # Constraints generalizadas (indicators, etc.).
        try:
            for gc in model.getGenConstrs():
                if int(getattr(gc, "IISGenConstr", 0) or 0) == 1:
                    constraint_names.append(gc.GenConstrName)
        except Exception:  # pragma: no cover
            pass

        bound_conflicts: list[dict[str, str]] = []
        variable_names: list[str] = []
        seen_vars: set[str] = set()
        try:
            for v in model.getVars():
                in_lb = int(getattr(v, "IISLB", 0) or 0) == 1
                in_ub = int(getattr(v, "IISUB", 0) or 0) == 1
                if in_lb:
                    bound_conflicts.append({"name": v.VarName, "side": "LB"})
                if in_ub:
                    bound_conflicts.append({"name": v.VarName, "side": "UB"})
                if (in_lb or in_ub) and v.VarName not in seen_vars:
                    variable_names.append(v.VarName)
                    seen_vars.add(v.VarName)
        except Exception:  # pragma: no cover
            logger.debug("Error leyendo IISLB/IISUB", exc_info=True)

        ilp_path_str: str | None = None
        if ilp_out is not None:
            try:
                ilp_out.parent.mkdir(parents=True, exist_ok=True)
                model.write(str(ilp_out))
                ilp_path_str = str(ilp_out)
            except Exception:
                logger.exception("No se pudo escribir el .ilp en %s", ilp_out)

        if not constraint_names and not variable_names:
            return IISReport(
                available=False,
                method="gurobi.computeIIS",
                unavailable_reason=(
                    "Gurobi ejecutó computeIIS pero el resultado quedó vacío. "
                    "Verifica que el LP realmente sea infactible."
                ),
                ilp_path=ilp_path_str,
            )

        return IISReport(
            available=True,
            method="gurobi.computeIIS",
            constraint_names=constraint_names,
            variable_names=variable_names,
            bound_conflicts=bound_conflicts,
            ilp_path=ilp_path_str,
            irreducible=bool(getattr(model, "IISMinimal", 0)),
        )
    finally:
        _release_gurobi(model)


def try_compute_iis(
    instance: Any | None,
    solver_name: str,
    *,
    lp_path: Path | None = None,
    ilp_out: Path | None = None,
) -> IISReport:
    """Intenta calcular un IIS o un análisis equivalente según el solver.

    Estrategia según solver:

    * ``gurobi``: usa ``Model.computeIIS()`` (vía gurobipy) sobre el ``.lp``
      ya escrito durante el solve. Si ``ilp_out`` se provee, persiste el
      ``.ilp`` allí.
    * ``highs``: ruta legacy con ``highspy`` — escribe LP simbólico, lo carga
      en ``highspy.Highs``, llama ``run()`` + ``getIis()``.
    * ``glpk``: ejecuta ``glpsol --nopresol`` para forzar el simplex completo
      y parsea las restricciones cuya actividad viola sus cotas. No es un IIS
      verdadero pero alimenta ``CONSTRAINT_PARAM_MAP`` con la misma interfaz.
    * Cualquier otro solver → ``IISReport(available=False, ...)``.

    En cualquier fallo devuelve ``IISReport(available=False, ...)`` con el motivo.
    """
    sn = (solver_name or "").lower()

    if sn == "gurobi":
        if lp_path is None or not Path(lp_path).exists():
            # Intentar exportar el LP a partir de la instancia Pyomo si
            # fue provista. Replica la misma lógica del path HiGHS.
            if instance is None:
                return IISReport(
                    available=False,
                    method=None,
                    unavailable_reason=(
                        "No hay LP ni instancia Pyomo para computar IIS con Gurobi."
                    ),
                )
            try:
                from app.simulation.core.solver import write_lp_file  # noqa: WPS433
            except Exception as exc:
                return IISReport(
                    available=False,
                    method=None,
                    unavailable_reason=f"No se pudo importar write_lp_file: {exc!r}",
                )
            tmp_dir = Path("tmp/infeasibility-reports")
            tmp_dir.mkdir(parents=True, exist_ok=True)
            lp_path = tmp_dir / "iis_input.lp"
            try:
                write_lp_file(instance, lp_path)
            except Exception as exc:  # pragma: no cover
                return IISReport(
                    available=False,
                    method=None,
                    unavailable_reason=f"No se pudo exportar LP para IIS: {exc!r}",
                )
        return _try_compute_iis_gurobi(Path(lp_path), ilp_out=ilp_out)

    if sn == "glpk":
        if instance is None:
            return IISReport(
                available=False,
                method=None,
                unavailable_reason="No se dispone de la instancia Pyomo para GLPK --nopresol.",
            )
        if lp_path is None or not Path(lp_path).exists():
            try:
                from app.simulation.core.solver import write_lp_file  # noqa: WPS433
            except Exception as exc:
                return IISReport(
                    available=False,
                    method=None,
                    unavailable_reason=f"No se pudo importar write_lp_file: {exc!r}",
                )
            try:
                tmp_dir = Path("tmp/infeasibility-reports")
                tmp_dir.mkdir(parents=True, exist_ok=True)
                lp_path = tmp_dir / "iis_input.lp"
                write_lp_file(instance, lp_path)
            except Exception as exc:
                return IISReport(
                    available=False,
                    method=None,
                    unavailable_reason=f"No se pudo exportar LP para diagnóstico GLPK: {exc!r}",
                )
        return _try_violations_glpk(lp_path)

    if sn != "highs":
        return IISReport(
            available=False,
            method=None,
            unavailable_reason=(
                f"IIS no soportado para el solver '{solver_name}'. "
                "Usa HiGHS, Gurobi o GLPK."
            ),
        )
    if instance is None and (lp_path is None or not Path(lp_path).exists()):
        return IISReport(
            available=False,
            method=None,
            unavailable_reason=(
                "No se dispone de instancia Pyomo ni de un LP existente para "
                "computar IIS."
            ),
        )

    highspy, err = _try_import_highspy()
    if highspy is None:
        return IISReport(available=False, method=None, unavailable_reason=err)

    # 3) Garantizar un LP con nombres simbólicos. Solo importamos write_lp_file
    # si necesitamos crearlo — evita depender de pyomo en contextos de test puros.
    if lp_path is None or not Path(lp_path).exists():
        try:
            from app.simulation.core.solver import write_lp_file  # noqa: WPS433
        except Exception as exc:
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=f"No se pudo importar write_lp_file: {exc!r}",
            )
        try:
            tmp_dir = Path("tmp/infeasibility-reports")
            tmp_dir.mkdir(parents=True, exist_ok=True)
            lp_path = tmp_dir / "iis_input.lp"
            write_lp_file(instance, lp_path)
        except Exception as exc:  # pragma: no cover
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=f"No se pudo exportar LP para IIS: {exc!r}",
            )

    try:
        h = highspy.Highs()
        if hasattr(h, "silent"):
            h.silent()
        elif hasattr(h, "setOptionValue"):
            try:
                h.setOptionValue("output_flag", False)
            except Exception:
                pass
        # En highspy 1.15.1, strategy=2 obtiene un subsystem de conflicto pero
        # puede conservar varios conflictos independientes. Strategy=4 es la
        # estrategia irreducible real (IisStrategy.kIisStrategyIrreducible).
        iis_strategy = getattr(
            getattr(highspy, "IisStrategy", None),
            "kIisStrategyIrreducible",
            4,
        )
        option_status = h.setOptionValue("iis_strategy", iis_strategy)
        if option_status == getattr(highspy.HighsStatus, "kError", None):
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=(
                    "HiGHS rechazó iis_strategy=irreducible; no se puede "
                    "garantizar que el subsystem sea un IIS."
                ),
            )

        try:
            iis_time_limit = float(
                os.getenv("OSEMOSYS_IIS_TIME_LIMIT_SECONDS", "300")
            )
        except (TypeError, ValueError):
            iis_time_limit = 300.0
        if iis_time_limit <= 0:
            iis_time_limit = 300.0
        time_option_status = h.setOptionValue("iis_time_limit", iis_time_limit)
        if time_option_status == getattr(highspy.HighsStatus, "kError", None):
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=(
                    "HiGHS rechazó el límite de tiempo del IIS "
                    f"({iis_time_limit}s)."
                ),
                time_limit_seconds=iis_time_limit,
            )
        # `iis_time_limit` sólo acota la búsqueda del IIS. El solve requerido
        # para certificar infactibilidad necesita su propio límite.
        solve_time_status = h.setOptionValue("time_limit", iis_time_limit)
        if solve_time_status == getattr(highspy.HighsStatus, "kError", None):
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=(
                    "HiGHS rechazó el límite de solve previo al IIS "
                    f"({iis_time_limit}s)."
                ),
                time_limit_seconds=iis_time_limit,
            )

        read_status = h.readModel(str(lp_path))
        if read_status == getattr(highspy.HighsStatus, "kError", None):
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=f"HiGHS no pudo leer el LP: {read_status}",
            )
        run_status = h.run()
        if run_status == getattr(highspy.HighsStatus, "kError", None):
            return IISReport(
                available=False,
                method=None,
                unavailable_reason=f"HiGHS falló al resolver el LP: {run_status}",
            )
        model_status = h.getModelStatus()
        infeasible_status = getattr(highspy.HighsModelStatus, "kInfeasible", None)
        if model_status != infeasible_status:
            timed_out = model_status == getattr(
                highspy.HighsModelStatus, "kTimeLimit", None
            )
            return IISReport(
                available=False,
                method="highs.solve_before_iis",
                unavailable_reason=(
                    "No se ejecutó IIS porque HiGHS no certificó infactibilidad: "
                    f"model_status={model_status}."
                ),
                timed_out=timed_out,
                time_limit_seconds=iis_time_limit,
            )
    except Exception as exc:  # pragma: no cover
        return IISReport(
            available=False,
            method=None,
            unavailable_reason=f"HiGHS no pudo cargar/ejecutar el LP: {exc!r}",
        )

    # Obtener nombres de filas/columnas para mapear índices del IIS.
    row_names: list[str] = []
    col_names: list[str] = []
    try:
        lp = h.getLp()
        row_names = list(getattr(lp, "row_names_", []) or [])
        col_names = list(getattr(lp, "col_names_", []) or [])
    except Exception:
        pass

    # Probar distintos nombres de método (cambian según versión de highspy).
    attempted: list[str] = []
    for method_name in ("getIis", "getIIS", "run_iis", "runIIS"):
        fn = getattr(h, method_name, None)
        if fn is None:
            continue
        attempted.append(method_name)
        iis_started = perf_counter()
        try:
            raw = fn()
        except Exception as exc:  # pragma: no cover
            logger.info("IIS vía %s falló: %s", method_name, exc)
            continue
        iis_elapsed = perf_counter() - iis_started
        logger.info(
            "HiGHS IIS vía %s terminó en %.3fs (límite %.1fs)",
            method_name,
            iis_elapsed,
            iis_time_limit,
        )
        cons, vars_, bound_conflicts = _parse_iis_payload_details(
            raw,
            row_names=row_names,
            col_names=col_names,
        )
        call_status = raw[0] if isinstance(raw, tuple) and raw else None
        has_explicit_status = str(call_status).startswith("HighsStatus.")
        if (
            has_explicit_status
            and call_status != getattr(highspy.HighsStatus, "kOk", None)
        ):
            return IISReport(
                available=False,
                method=f"highs.{method_name}.partial",
                constraint_names=cons,
                variable_names=vars_,
                bound_conflicts=bound_conflicts,
                unavailable_reason=(
                    "HiGHS no certificó un IIS irreducible: "
                    f"getIis_status={call_status}. El subsystem parcial no debe "
                    "presentarse como IIS."
                ),
                timed_out=(
                    iis_elapsed >= max(0.0, iis_time_limit * 0.95)
                    or call_status == getattr(highspy.HighsStatus, "kWarning", None)
                ),
                elapsed_seconds=iis_elapsed,
                time_limit_seconds=iis_time_limit,
            )
        if cons or vars_:
            return IISReport(
                available=True,
                method=f"highs.{method_name}.irreducible",
                constraint_names=cons,
                variable_names=vars_,
                bound_conflicts=bound_conflicts,
                irreducible=True,
                elapsed_seconds=iis_elapsed,
                time_limit_seconds=iis_time_limit,
            )

    reason = (
        f"HiGHS se ejecutó pero no produjo un IIS no vacío. "
        f"Métodos intentados: {attempted or '—'}. "
        "Verifica la versión de highspy o que el LP realmente sea infactible."
    )
    return IISReport(available=False, method=None, unavailable_reason=reason)


def _parse_iis_payload_details(
    payload: Any,
    *,
    row_names: list[str],
    col_names: list[str],
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    """Normaliza lo que devuelven los distintos ``getIis`` de highspy.

    Formatos observados según versión:
      * highspy >=1.8: tupla ``(HighsStatus, HighsIis)`` donde ``HighsIis`` tiene
        atributos ``row_index_`` / ``col_index_`` (listas de int).
      * Versiones antiguas: tupla ``(row_indices, col_indices)``.
      * Variantes dict ``{"rows": [...], "cols": [...]}`` u objeto con
        ``row_index`` / ``col_index`` directos.

    Extrae dos listas de ints y las mapea a nombres (row_names/col_names del LP).
    """

    def _pluck_from_iis_like(obj: Any) -> tuple[Iterable[int] | None, Iterable[int] | None]:
        # highspy.HighsIis: atributos terminan en "_".
        r = getattr(obj, "row_index_", None)
        c = getattr(obj, "col_index_", None)
        if r is not None or c is not None:
            return r, c
        # Variantes sin guion bajo.
        r = getattr(obj, "row_index", None) or getattr(obj, "rows", None)
        c = getattr(obj, "col_index", None) or getattr(obj, "cols", None)
        return r, c

    rows: Iterable[int] | None = None
    cols: Iterable[int] | None = None

    if isinstance(payload, tuple) and len(payload) >= 2:
        # highspy >=1.8: (HighsStatus, HighsIis). El primer elemento NO son los
        # índices de fila, sino el status. Detectamos el objeto IIS en el segundo.
        first, second = payload[0], payload[1]
        # Intenta primero tratar a `second` como HighsIis.
        r, c = _pluck_from_iis_like(second)
        if r is None and c is None:
            # Fallback legacy: (rows, cols) directo.
            rows, cols = first, second
        else:
            rows, cols = r, c
    elif isinstance(payload, dict):
        rows = payload.get("rows") or payload.get("row_index") or payload.get("row_index_")
        cols = payload.get("cols") or payload.get("col_index") or payload.get("col_index_")
    else:
        rows, cols = _pluck_from_iis_like(payload)

    def _to_names(indices: Iterable[int] | None, names: list[str]) -> list[str]:
        if indices is None:
            return []
        try:
            seq = list(indices)
        except Exception:
            return []
        out: list[str] = []
        for idx in seq:
            try:
                i = int(idx)
            except Exception:
                continue
            if 0 <= i < len(names):
                out.append(names[i])
            else:
                out.append(f"<idx:{i}>")
        return out

    constraint_names = _to_names(rows, row_names)
    variable_names = _to_names(cols, col_names)

    # highspy 1.15.1 expone el lado de bound de cada columna incluida en el
    # IIS. Los códigos de IisBoundStatus son: 2=lower, 3=upper, 4=boxed.
    bound_conflicts: list[dict[str, str]] = []
    iis_obj = (
        payload[1]
        if isinstance(payload, tuple) and len(payload) >= 2
        else payload
    )
    col_bounds = getattr(iis_obj, "col_bound_", None)
    if col_bounds is not None:
        try:
            bound_codes = [int(code) for code in list(col_bounds)]
        except Exception:
            bound_codes = []
        for name, code in zip(variable_names, bound_codes):
            if code in (2, 4):
                bound_conflicts.append({"name": name, "side": "LB"})
            if code in (3, 4):
                bound_conflicts.append({"name": name, "side": "UB"})

    return constraint_names, variable_names, bound_conflicts


def _parse_iis_payload(
    payload: Any,
    *,
    row_names: list[str],
    col_names: list[str],
) -> tuple[list[str], list[str]]:
    """Compatibilidad: devuelve sólo nombres; los detalles viven en el helper nuevo."""
    constraints, variables, _ = _parse_iis_payload_details(
        payload,
        row_names=row_names,
        col_names=col_names,
    )
    return constraints, variables


# =====================================================================
# Reporte final
# =====================================================================


@dataclass
class ConstraintAnalysis:
    name: str
    constraint_type: str
    indices: dict[str, str]
    body: float | None
    lower: float | None
    upper: float | None
    side: str
    violation: float
    in_iis: bool
    has_mapping: bool
    description: str
    related_params: list[ParamHit]


@dataclass
class InfeasibilityOverview:
    """Resumen de alto nivel: años, tipos de restricción/variable y codigos
    (tecnologías/combustibles) únicos que aparecen en el IIS o, en su defecto,
    en las restricciones violadas.

    Todos los contadores están deduplicados: si ``EnergyBalanceEachYear4`` aparece
    10 veces, se reporta como ``{"EnergyBalanceEachYear4": 10}``.
    """

    years: list[int]                       # ordenados ascendente
    constraint_types: dict[str, int]       # tipo → # entradas
    variable_types: dict[str, int]         # tipo → # entradas
    techs_or_fuels: dict[str, int]         # código → # entradas (constraints + vars)
    total_constraints: int
    total_variables: int


@dataclass
class DiagnosisClassification:
    code: str
    evidence_level: str
    solver_status: str
    explanation: str


def classify_solver_outcome(status: str | None) -> DiagnosisClassification:
    """Clasifica el resultado sin confundir límites/fallos con infactibilidad."""
    raw = str(status or "").strip()
    normalized = re.sub(r"[^a-z]", "", raw.lower())
    if ("infeasible" in normalized or "infactible" in normalized) and "unbounded" in normalized:
        return DiagnosisClassification(
            code="UNCLASSIFIED",
            evidence_level="OPERATIONAL",
            solver_status=raw,
            explanation="El solver no distinguió entre infactibilidad y no acotación.",
        )
    if "infeasible" in normalized or "infactible" in normalized:
        return DiagnosisClassification(
            code="INFEASIBLE_CERTIFIED",
            evidence_level="CERTIFIED",
            solver_status=raw,
            explanation="El solver declaró matemáticamente infactible el modelo.",
        )
    if "unbounded" in normalized or "noacotado" in normalized:
        return DiagnosisClassification(
            code="UNBOUNDED_CERTIFIED",
            evidence_level="CERTIFIED",
            solver_status=raw,
            explanation="El objetivo puede mejorar sin límite; no corresponde ejecutar IIS.",
        )
    if any(token in normalized for token in ("knotset", "notset", "unknown", "error")):
        return DiagnosisClassification(
            code="NUMERICAL_FAILURE",
            evidence_level="OPERATIONAL",
            solver_status=raw,
            explanation="El solver no produjo una clasificación matemática utilizable.",
        )
    if any(token in normalized for token in ("timelimit", "iterationlimit", "objectivelimit", "maxtime", "maxiteration")):
        return DiagnosisClassification(
            code="RESOURCE_LIMIT",
            evidence_level="OPERATIONAL",
            solver_status=raw,
            explanation="La ejecución terminó por un límite operativo, no por infactibilidad certificada.",
        )
    if "cancel" in normalized:
        return DiagnosisClassification(
            code="CANCELLED",
            evidence_level="OPERATIONAL",
            solver_status=raw,
            explanation="La ejecución fue cancelada antes de una conclusión matemática.",
        )
    if "optimal" in normalized or "optimo" in normalized:
        return DiagnosisClassification(
            code="OPTIMAL",
            evidence_level="CERTIFIED",
            solver_status=raw,
            explanation="El solver encontró una solución óptima factible.",
        )
    return DiagnosisClassification(
        code="UNCLASSIFIED",
        evidence_level="OPERATIONAL",
        solver_status=raw,
        explanation="No hay evidencia suficiente para clasificar el resultado.",
    )


@dataclass
class InfeasibilityReport:
    solver_name: str
    solver_status: str
    classification: DiagnosisClassification
    csv_dir: str | None
    certificate: DualRayReport
    feasibility_relaxation: FeasibilityRelaxationReport
    iis: IISReport
    overview: InfeasibilityOverview
    top_suspects: list[ParamHit]
    constraint_analyses: list[ConstraintAnalysis]
    var_bound_conflicts: list[dict[str, Any]]
    structural_findings: list[dict[str, Any]]
    unmapped_constraint_prefixes: list[str]


def _top_suspects(
    analyses: list["ConstraintAnalysis"],
    k: int = 10,
) -> list[ParamHit]:
    """Top-K ``ParamHit`` ordenados por **|diff_abs|** (diferencia absoluta vs
    default), deduplicados por ``(param, indices)``.

    Usamos ``|diff_abs|`` en lugar de ``deviation_score`` porque el score se
    satura en 100 cuando el default es 0 (muy común en OSeMOSYS — p.ej.
    ``TotalAnnualMaxCapacity`` default=9999999, si el usuario puso 0 el score
    sería 100; y muchos otros params con default=0 que tengan cualquier valor
    saltan a 100). Eso sesgaba el ranking. La diferencia absoluta refleja la
    magnitud real del cambio.

    Nota: comparar magnitudes absolutas entre parámetros con unidades distintas
    no es apples-to-apples (ej. ``AnnualEmissionLimit`` en t/año vs
    ``CapacityFactor`` en [0,1]), pero para un ranking cualitativo de
    "cuál cambió más" es robusto y no saturable.
    """
    seen: dict[tuple[str, tuple[tuple[str, str], ...]], ParamHit] = {}
    for a in analyses:
        for hit in a.related_params or []:
            if hit.diff_abs is None:
                continue
            key = (hit.param, tuple(sorted((hit.indices or {}).items())))
            current = seen.get(key)
            current_mag = abs(current.diff_abs or 0.0) if current else -1.0
            if abs(hit.diff_abs) > current_mag:
                seen[key] = hit
    ordered = sorted(
        seen.values(),
        key=lambda h: (-abs(h.diff_abs or 0.0), h.param),
    )
    return ordered[:k]


def _max_abs_diff_of(a: "ConstraintAnalysis") -> float:
    """Mayor ``|diff_abs|`` entre los ``related_params`` de una restricción."""
    best = 0.0
    for hit in a.related_params or []:
        if hit.diff_abs is not None:
            m = abs(hit.diff_abs)
            if m > best:
                best = m
    return best


def _coerce_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def _pyomo_names_by_canon(instance: Any | None) -> dict[str, str]:
    """Devuelve ``{canon(con.name): con.name}`` para todas las restricciones activas.

    Sirve para mapear los nombres que HiGHS reporta en el IIS (con la forma
    transformada del LP, ej. ``Name(i_j)_``) de regreso al nombre interno de
    Pyomo (``Name[i,j]``), que es el que podemos parsear con
    :func:`parse_constraint_name`.
    """
    if instance is None:
        return {}
    try:
        from pyomo.core import Constraint  # noqa: WPS433 - import local para evitar dep en tests
    except Exception:
        return {}
    name_by_canon: dict[str, str] = {}
    try:
        for con in instance.component_data_objects(Constraint, active=True):
            name_by_canon[_canon_name(con.name)] = con.name
    except Exception as exc:  # pragma: no cover - best effort
        logger.info("No se pudo construir name_by_canon: %s", exc)
    return name_by_canon


def _build_analysis_entry(
    *,
    pyomo_name: str,
    viol: dict[str, Any] | None,
    in_iis: bool,
    csv_dir: Path | str | None,
    unmapped: set[str],
) -> ConstraintAnalysis:
    prefix, tokens = parse_constraint_name(pyomo_name)
    spec = CONSTRAINT_PARAM_MAP.get(prefix)
    indices = constraint_indices(prefix, tokens)
    if spec is None:
        unmapped.add(prefix)

    related: list[ParamHit] = []
    if csv_dir is not None and indices:
        try:
            related = values_for_constraint(csv_dir, prefix, indices)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "No se pudieron extraer parámetros para %s: %s", pyomo_name, exc
            )

    v = viol or {}
    return ConstraintAnalysis(
        name=pyomo_name,
        constraint_type=prefix,
        indices=indices,
        body=_coerce_float(v.get("body")),
        lower=_coerce_float(v.get("lower")),
        upper=_coerce_float(v.get("upper")),
        side=str(v.get("side") or ""),
        violation=float(v.get("violation") or 0.0),
        in_iis=in_iis,
        has_mapping=spec is not None,
        description=spec.description if spec else "",
        related_params=related,
    )


def analyze(
    *,
    solution: dict[str, Any],
    instance: Any | None = None,
    solver: Any | None = None,  # noqa: ARG001 - reservado para futuros backends
    csv_dir: Path | str | None = None,
    top_n: int = 20,
    lp_path: Path | None = None,
    job_id: int | None = None,
    ilp_out: Path | None = None,
    on_phase: Callable[[str], None] | None = None,
    analysis_level: str = "full",
) -> InfeasibilityReport:
    """Construye el reporte enriquecido a partir del dict que retorna ``solve_model``.

    Estrategia de selección de ``constraint_analyses``:

    * **Cuando el IIS está disponible** (HiGHS con estrategia irreducible),
      ``constraint_analyses`` se construye a partir del subsystem reportado.
      ``iis.irreducible`` indica si el solver certificó minimalidad. Esta fuente
      es típicamente mucho más pequeña y precisa que
      la lista de violaciones post-solve.
    * **Si no hay IIS**, se usa ``constraint_violations`` del diagnóstico básico
      (``_run_infeasibility_diagnostics``). **Atención**: esa lista evalúa
      ``con.body`` con las variables en su punto inicial (generalmente 0 porque
      ``load_solutions=False`` en modelos infactibles), por lo que suele contener
      muchos falsos positivos — cualquier restricción que compara contra una
      demanda no nula aparecerá violada. Úsala como señal cualitativa.
    """
    valid_levels = {"full", "dual_ray", "iis", "relaxation"}
    if analysis_level not in valid_levels:
        raise ValueError(f"Nivel de análisis inválido: {analysis_level!r}")
    solver_name = str(solution.get("solver_name") or "").lower()
    solver_status = str(solution.get("solver_status") or "")
    diagnostics = solution.get("infeasibility_diagnostics") or {}
    violations: list[dict[str, Any]] = list(
        diagnostics.get("constraint_violations") or []
    )
    var_conflicts: list[dict[str, Any]] = list(
        diagnostics.get("var_bound_conflicts") or []
    )
    violations.sort(key=lambda v: -float(v.get("violation") or 0.0))

    classification = classify_solver_outcome(solver_status)
    if on_phase:
        on_phase("classify")

    # Crear una sola representación LP reproducible para certificado,
    # relajación e IIS. Cada operación usa su propia instancia Highs para no
    # contaminar estados internos.
    effective_lp_path = Path(lp_path) if lp_path is not None else None
    if (
        solver_name == "highs"
        and instance is not None
        and (effective_lp_path is None or not effective_lp_path.exists())
    ):
        try:
            from app.simulation.core.solver import write_lp_file  # noqa: WPS433

            suffix = f"job_{int(job_id)}" if job_id is not None else "diagnostic"
            effective_lp_path = Path("tmp/infeasibility-reports") / f"{suffix}.lp"
            write_lp_file(instance, effective_lp_path)
        except Exception:
            logger.exception("No se pudo preparar LP compartido para el diagnóstico")
            effective_lp_path = None

    certificate = DualRayReport(
        available=False,
        unavailable_reason="El estado no habilita certificado de infactibilidad.",
    )
    relaxation = FeasibilityRelaxationReport(
        available=False,
        unavailable_reason="El estado no habilita relajación de factibilidad.",
    )
    if classification.code == "INFEASIBLE_CERTIFIED" and analysis_level in {"full", "dual_ray"}:
        if on_phase:
            on_phase("dual_ray")
        certificate = try_compute_dual_ray(
            instance,
            solver_name,
            lp_path=effective_lp_path,
        )
    elif classification.code == "UNBOUNDED_CERTIFIED" and analysis_level in {"full", "dual_ray"}:
        certificate = try_compute_primal_ray(
            solver_name,
            lp_path=effective_lp_path,
        )
    elif analysis_level not in {"full", "dual_ray"}:
        certificate.unavailable_reason = "No solicitado en este nivel de diagnóstico."

    if classification.code == "INFEASIBLE_CERTIFIED" and analysis_level in {"full", "relaxation"}:
        if on_phase:
            on_phase("feasibility_relaxation")
        relaxation = try_feasibility_relaxation(
            instance,
            solver_name,
            lp_path=effective_lp_path,
        )
    elif analysis_level not in {"full", "relaxation"}:
        relaxation.unavailable_reason = "No solicitada en este nivel de diagnóstico."

    # IIS (HiGHS o Gurobi). Para Gurobi, si no se pasa `ilp_out` explícito
    # pero sí `job_id`, se persiste como `tmp/infeasibility-reports/job_<id>.ilp`.
    if ilp_out is None and job_id is not None and solver_name == "gurobi":
        ilp_out = Path("tmp/infeasibility-reports") / f"job_{int(job_id)}.ilp"
    if classification.code == "INFEASIBLE_CERTIFIED" and analysis_level in {"full", "iis"}:
        if on_phase:
            on_phase("iis")
        iis = try_compute_iis(
            instance,
            solver_name=solver_name,
            lp_path=effective_lp_path,
            ilp_out=ilp_out,
        )
    elif classification.code != "INFEASIBLE_CERTIFIED":
        iis = IISReport(
            available=False,
            method=None,
            unavailable_reason=(
                "No se ejecutó IIS porque el resultado no certifica "
                f"infactibilidad ({classification.code})."
            ),
        )
    else:
        iis = IISReport(
            available=False,
            method=None,
            unavailable_reason="No solicitado en este nivel de diagnóstico.",
        )

    # 2) Índices rápidos: canónico → nombre Pyomo (para IIS → Pyomo),
    # canónico → dict de violación básica (para anexar body/bounds si hay).
    pyomo_by_canon = _pyomo_names_by_canon(instance)
    violation_by_canon: dict[str, dict[str, Any]] = {
        _canon_name(str(v.get("name") or "")): v for v in violations
    }
    iis_canon = {_canon_name(n) for n in iis.constraint_names}

    # Para GLPK: lookup enriquecido (act, bound, diff) por nombre canónico LP.
    glpk_viol_by_canon: dict[str, dict[str, Any]] = {}
    for gv in (iis.glpk_violations or []):
        lp_name = str(gv.get("lp_name") or "")
        if not lp_name:
            continue
        bt = gv.get("bound_type", "lower")
        bound = gv.get("bound")
        glpk_viol_by_canon[_canon_name(lp_name)] = {
            "body": gv.get("act"),
            "lower": bound if bt in ("lower", "equality") else None,
            "upper": bound if bt in ("upper", "equality") else None,
            "violation": gv.get("diff_abs", 0.0),
            "side": bt,
        }

    analyses: list[ConstraintAnalysis] = []
    unmapped: set[str] = set()

    if iis.available and iis.constraint_names:
        # Fuente primaria: IIS. Recorremos los nombres del LP, los mapeamos al
        # nombre interno Pyomo y construimos la entrada con los datos de
        # violación (si están) del diagnóstico básico.
        seen_canon: set[str] = set()
        for lp_name in iis.constraint_names:
            canon = _canon_name(lp_name)
            if canon in seen_canon:
                continue
            seen_canon.add(canon)
            pyomo_name = pyomo_by_canon.get(canon, lp_name)
            viol = glpk_viol_by_canon.get(canon) or violation_by_canon.get(canon)
            analyses.append(
                _build_analysis_entry(
                    pyomo_name=pyomo_name,
                    viol=viol,
                    in_iis=True,
                    csv_dir=csv_dir,
                    unmapped=unmapped,
                )
            )
    else:
        # Fallback: violaciones post-solve (noisy).
        for viol in violations[:top_n]:
            name = str(viol.get("name") or "")
            analyses.append(
                _build_analysis_entry(
                    pyomo_name=name,
                    viol=viol,
                    in_iis=_canon_name(name) in iis_canon,
                    csv_dir=csv_dir,
                    unmapped=unmapped,
                )
            )

    overview = _build_overview(iis, analyses)

    # Ordenar las restricciones por la mayor diferencia absoluta vs default
    # entre sus parámetros relacionados. Usar |diff_abs| evita el sesgo del
    # score=100 cuando un default es 0 (ver doc de `_top_suspects`).
    analyses.sort(key=lambda a: -(max(_max_abs_diff_of(a), a.violation)))

    suspects = _top_suspects(analyses, k=10)

    structural_findings: list[dict[str, Any]] = []
    if csv_dir is not None:
        if on_phase:
            on_phase("structural")
        try:
            from app.simulation.core.structural_infeasibility import (  # noqa: WPS433
                analyze_structural_infeasibility,
            )

            structural_findings = [
                finding.to_dict()
                for finding in analyze_structural_infeasibility(csv_dir)
            ]
        except Exception:
            logger.exception("Falló el análisis estructural de infactibilidad")

    return InfeasibilityReport(
        solver_name=solver_name,
        solver_status=solver_status,
        classification=classification,
        csv_dir=str(csv_dir) if csv_dir is not None else None,
        certificate=certificate,
        feasibility_relaxation=relaxation,
        iis=iis,
        overview=overview,
        top_suspects=suspects,
        constraint_analyses=analyses,
        var_bound_conflicts=var_conflicts,
        structural_findings=structural_findings,
        unmapped_constraint_prefixes=sorted(unmapped),
    )


# =====================================================================
# Serialización / impresión
# =====================================================================


def _report_to_dict(report: InfeasibilityReport) -> dict[str, Any]:
    return {
        "solver_name": report.solver_name,
        "solver_status": report.solver_status,
        "classification": asdict(report.classification),
        "csv_dir": report.csv_dir,
        "overview": asdict(report.overview),
        "certificate": asdict(report.certificate),
        "feasibility_relaxation": asdict(report.feasibility_relaxation),
        "iis": asdict(report.iis),
        "top_suspects": [asdict(h) for h in report.top_suspects],
        "constraint_analyses": [asdict(c) for c in report.constraint_analyses],
        "var_bound_conflicts": report.var_bound_conflicts,
        "structural_findings": report.structural_findings,
        "unmapped_constraint_prefixes": report.unmapped_constraint_prefixes,
    }


def enrich_solution_dict(
    solution: dict[str, Any],
    *,
    instance: Any | None,
    csv_dir: Path | str | None,
    top_n: int = 50,
    job_id: int | None = None,
    lp_path: Path | None = None,
    on_phase: Callable[[str], None] | None = None,
    analysis_level: str = "full",
) -> InfeasibilityReport | None:
    """Corre :func:`analyze` y **muta** ``solution['infeasibility_diagnostics']``.

    Agrega los campos enriquecidos ``iis``, ``constraint_analyses``,
    ``unmapped_constraint_prefixes`` y ``csv_dir`` al diagnóstico existente sin
    romper los consumidores actuales (que ya leen ``constraint_violations`` y
    ``var_bound_conflicts``).

    Devuelve el reporte estructurado para que el llamador pueda, si quiere,
    imprimirlo en consola o escribirlo a disco. Si la solución no es infactible
    (no hay ``infeasibility_diagnostics``) retorna ``None`` sin modificar nada.
    """
    diag = solution.get("infeasibility_diagnostics")
    if not isinstance(diag, dict):
        return None

    report = analyze(
        solution=solution,
        instance=instance,
        csv_dir=csv_dir,
        top_n=top_n,
        job_id=job_id,
        lp_path=lp_path,
        on_phase=on_phase,
        analysis_level=analysis_level,
    )

    diag["classification"] = asdict(report.classification)
    diag["certificate"] = asdict(report.certificate)
    diag["feasibility_relaxation"] = asdict(report.feasibility_relaxation)
    diag["iis"] = asdict(report.iis)
    diag["overview"] = asdict(report.overview)
    diag["top_suspects"] = [asdict(h) for h in report.top_suspects]
    diag["constraint_analyses"] = [asdict(c) for c in report.constraint_analyses]
    diag["structural_findings"] = list(report.structural_findings)
    diag["unmapped_constraint_prefixes"] = list(report.unmapped_constraint_prefixes)
    if csv_dir is not None:
        diag["csv_dir"] = str(csv_dir)
    return report


def write_report_json(report: InfeasibilityReport, path: Path | str) -> Path:
    """Escribe el reporte completo como JSON. Devuelve el Path del archivo."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_report_to_dict(report), fh, ensure_ascii=False, indent=2, default=str)
    return path


def print_report_console(report: InfeasibilityReport, *, top_n: int = 10) -> None:
    """Imprime un resumen legible en consola (top_n violaciones)."""
    bar = "=" * 78
    print("\n" + bar)
    print("ANÁLISIS DE INFACTIBILIDAD")
    print(bar)
    print(f"Solver        : {report.solver_name}")
    print(f"Estado        : {report.solver_status}")
    print(f"CSV dir       : {report.csv_dir or '—'}")
    if report.iis.available:
        print(
            f"IIS           : disponible ({len(report.iis.constraint_names)} restricciones, "
            f"{len(report.iis.variable_names)} variables) via {report.iis.method}"
        )
        source_label = (
            "IIS irreducible"
            if report.iis.irreducible
            else "subsistema de conflicto no certificado como irreducible"
        )
        print(
            f"Fuente        : {source_label} — "
            f"{len(report.constraint_analyses)} restricciones"
        )
    else:
        print(f"IIS           : no disponible — {report.iis.unavailable_reason}")
        print(
            f"Fuente        : violaciones post-solve (heurística, puede contener falsos "
            f"positivos) — {len(report.constraint_analyses)} restricciones (top {top_n} abajo)"
        )
    print(bar)

    # ── Resumen inicial: años / tipos / tecnologías únicos ─────────────
    ov = report.overview

    def _fmt_counter(items: dict[str, int], max_items: int = 10) -> str:
        if not items:
            return "(ninguno)"
        ordered = sorted(items.items(), key=lambda kv: (-kv[1], kv[0]))
        head = ordered[:max_items]
        suffix = f"  (+{len(ordered) - max_items} más)" if len(ordered) > max_items else ""
        return ", ".join(f"{name}×{cnt}" for name, cnt in head) + suffix

    print("\nRESUMEN")
    if ov.years:
        print(f"  Años infactibles    ({len(ov.years)}): {', '.join(str(y) for y in ov.years)}")
    else:
        print("  Años infactibles    : (ninguno detectado)")
    print(
        f"  Tipos de restricción ({len(ov.constraint_types)}): "
        f"{_fmt_counter(ov.constraint_types)}"
    )
    print(
        f"  Tipos de variable   ({len(ov.variable_types)}): "
        f"{_fmt_counter(ov.variable_types)}"
    )
    print(
        f"  Tecnologías/Combustibles únicos ({len(ov.techs_or_fuels)}): "
        f"{_fmt_counter(ov.techs_or_fuels, max_items=15)}"
    )
    print(bar)

    for i, c in enumerate(report.constraint_analyses[:top_n], start=1):
        marker = " ⭐ IIS" if c.in_iis else ""
        print(f"\n[{i}] {c.name}{marker}")
        print(f"    Tipo      : {c.constraint_type}{' (sin mapeo)' if not c.has_mapping else ''}")
        if c.description:
            print(f"    Descripción: {c.description}")
        if c.indices:
            idx_txt = ", ".join(f"{k}={v}" for k, v in c.indices.items())
            print(f"    Índices   : {idx_txt}")
        lb_txt = f"{c.lower:.4g}" if c.lower is not None else "-inf"
        ub_txt = f"{c.upper:.4g}" if c.upper is not None else "+inf"
        body_txt = f"{c.body:.4g}" if c.body is not None else "—"
        print(
            f"    Body={body_txt}  Bounds=[{lb_txt}, {ub_txt}]  "
            f"Lado={c.side or '—'}  Violación={c.violation:.4g}"
        )
        if c.related_params:
            print(f"    Parámetros relacionados ({len(c.related_params)}):")
            for hit in c.related_params[:15]:
                if hit.is_default:
                    print(f"      - {hit.param}: <no hay CSV o no hay fila para estos índices>")
                else:
                    idx_txt = ", ".join(f"{k}={v}" for k, v in hit.indices.items())
                    val_txt = f"{hit.value:.6g}" if hit.value is not None else "—"
                    print(f"      - {hit.param}[{idx_txt}] = {val_txt}")
            if len(c.related_params) > 15:
                print(f"      (… y {len(c.related_params) - 15} más; ver JSON)")

    if report.var_bound_conflicts:
        print("\n" + bar)
        print(f"CONFLICTOS DE BOUNDS DE VARIABLES: {len(report.var_bound_conflicts)}")
        print(bar)
        for i, v in enumerate(report.var_bound_conflicts[:top_n], start=1):
            name = v.get("name")
            lb = v.get("lb")
            ub = v.get("ub")
            gap = v.get("gap")
            print(f"[{i}] {name}: LB={lb}  UB={ub}  Gap={gap}")

    if report.unmapped_constraint_prefixes:
        print("\n" + bar)
        print("PREFIJOS DE RESTRICCIÓN SIN MAPEO ESTÁTICO")
        print(bar)
        for p in report.unmapped_constraint_prefixes:
            print(f"  - {p}")
        print(
            "→ Estos tipos se reportan sin traceo a parámetros. Agrégalos a "
            "CONSTRAINT_PARAM_MAP en infeasibility_analysis.py si son recurrentes."
        )

    print("\n" + bar + "\n")
