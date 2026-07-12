"""Definición completa del AbstractModel OSeMOSYS.

Replica fielmente la celda 3 del notebook osemosys_notebook_UPME_OPT_01.ipynb:
sets, parámetros, variables, función objetivo y TODAS las restricciones
en un solo archivo.

OSeMOSYS: Open Source energy MOdeling SYStem
Copyright [2010-2015] [OSeMOSYS Forum steering committee see: www.osemosys.org]
Licensed under the Apache License, Version 2.0

Estructura del archivo:
  - Sets: YEAR, TECHNOLOGY, TIMESLICE, FUEL, EMISSION, MODE_OF_OPERATION, REGION; opcionales STORAGE, SEASON, DAYTYPE, DAILYTIMEBRACKET, UDC.
  - Parameters: demanda, rendimientos (CapacityFactor, ActivityRatios), costes, límites de capacidad/actividad, emisiones, UDC, almacenamiento.
  - Variables: NewCapacity, RateOfActivity, costes descontados, emisiones, reserva, RE, almacenamiento.
  - Objective: minimizar suma de TotalDiscountedCost por región y año.
  - Constraints: capacidad, balance energético, costes, límites, emisiones, reserve margin, UDC, almacenamiento.
"""

from __future__ import annotations

import os

from pyomo.environ import (
    AbstractModel,
    Any,
    Constraint,
    NonNegativeIntegers,
    NonNegativeReals,
    Objective,
    Param,
    Reals,
    Set,
    Suffix,
    Var,
    minimize,
)


from collections.abc import Mapping

from app.simulation.core.osemosys_defaults import OSEMOSYS_PARAM_DEFAULTS


def _resolve_defaults(param_defaults: Mapping[str, float] | None) -> dict[str, float]:
    merged = dict(OSEMOSYS_PARAM_DEFAULTS)
    if param_defaults:
        merged.update(param_defaults)
    return merged


def _d(key: str, defaults: dict[str, float]) -> float:
    return float(defaults.get(key, OSEMOSYS_PARAM_DEFAULTS.get(key, 0.0)))


def create_abstract_model(
    *,
    has_storage: bool = False,
    has_udc: bool = True,
    param_defaults: Mapping[str, float] | None = None,
    sparse_high_dim_params: bool | None = None,
    sparse_emission_penalties: bool | None = None,
) -> AbstractModel:
    """Construye el AbstractModel OSeMOSYS completo.

    Parameters
    ----------
    has_storage : bool
        Si True, incluye sets/params/vars/constraints de almacenamiento.
    has_udc : bool
        Si True, incluye User-Defined Constraints.
    sparse_high_dim_params : bool | None
        Si True, ActivityRatio y parámetros afines almacenan sólo índices
        presentes y usan default para ausentes. None toma la variable de entorno.

    Returns
    -------
    AbstractModel listo para ``model.create_instance(data)``.
    """
    defaults = _resolve_defaults(param_defaults)
    if sparse_high_dim_params is None:
        sparse_high_dim_params = str(
            os.getenv("OSEMOSYS_SPARSE_HIGH_DIM_PARAMS", "1")
        ).strip().lower() not in {"0", "false", "off", "no"}
    if sparse_emission_penalties is None:
        sparse_emission_penalties = str(
            os.getenv("OSEMOSYS_SPARSE_EMISSION_PENALTIES", "1")
        ).strip().lower() not in {"0", "false", "off", "no"}

    model = AbstractModel()

    # ====================================================================
    #    Sets (conjuntos que indexan parámetros y variables)
    # ====================================================================

    model.YEAR = Set(ordered=True)
    model.TECHNOLOGY = Set()
    model.TIMESLICE = Set(ordered=True)
    model.FUEL = Set()
    model.EMISSION = Set()
    model.MODE_OF_OPERATION = Set()
    model.REGION = Set()

    if has_storage:
        model.STORAGE = Set()
        model.SEASON = Set()
        model.DAYTYPE = Set()
        model.DAILYTIMEBRACKET = Set()
        model.STORAGEINTRADAY = Set()
        model.STORAGEINTRAYEAR = Set()

    model.FLEXIBLEDEMANDTYPE = Set()
    model.UDC = Set()

    # ====================================================================
    #    Parameters — Global (YearSplit, descuento, vida operativa, factores de recuperación)
    # ====================================================================

    model.YearSplit = Param(model.TIMESLICE, model.YEAR)
    model.DiscountRate = Param(model.REGION, default=_d("discountrate", defaults))

    def DiscountRateIdv_init(m, r, t):
        return m.DiscountRate[r]
    model.DiscountRateIdv = Param(
        model.REGION, model.TECHNOLOGY,
        within=NonNegativeReals, initialize=DiscountRateIdv_init, mutable=True,
    )
    model.OperationalLife = Param(model.REGION, model.TECHNOLOGY, default=_d("operationallife", defaults))

    def CapitalRecoveryFactor_rule(m, r, t):
        dr = m.DiscountRateIdv[r, t]
        ol = m.OperationalLife[r, t]
        return (1 - (1 + dr)**(-1)) / (1 - (1 + dr)**(-ol))
    model.CapitalRecoveryFactor = Param(
        model.REGION, model.TECHNOLOGY,
        initialize=CapitalRecoveryFactor_rule, within=Reals, mutable=True,
    )

    def PvAnnuity_rule(m, r, t):
        dr = m.DiscountRate[r]
        ol = m.OperationalLife[r, t]
        return (1 - (1 + dr)**(-ol)) * (1 + dr) / dr
    model.PvAnnuity = Param(
        model.REGION, model.TECHNOLOGY,
        initialize=PvAnnuity_rule, within=Reals, mutable=True,
    )

    model.DepreciationMethod = Param(model.REGION, default=_d("depreciationmethod", defaults))

    # ====================================================================
    #    Parameters — Demands
    # ====================================================================

    model.AccumulatedAnnualDemand = Param(model.REGION, model.FUEL, model.YEAR, default=_d("accumulatedannualdemand", defaults))
    model.SpecifiedAnnualDemand = Param(model.REGION, model.FUEL, model.YEAR, default=_d("specifiedannualdemand", defaults))
    model.SpecifiedDemandProfile = Param(
        model.REGION, model.FUEL, model.TIMESLICE, model.YEAR, default=_d("specifieddemandprofile", defaults),
    )

    def Demand_init(m, r, l, f, y):
        if m.SpecifiedAnnualDemand[r, f, y] > 0:
            return m.SpecifiedAnnualDemand[r, f, y] * m.SpecifiedDemandProfile[r, f, l, y]
        return 0.0
    model.Demand = Param(
        model.REGION, model.TIMESLICE, model.FUEL, model.YEAR,
        initialize=Demand_init, default=_d("demand", defaults),
    )

    # ====================================================================
    #    Parameters — Performance
    # ====================================================================

    model.CapacityToActivityUnit = Param(model.REGION, model.TECHNOLOGY, default=_d("capacitytoactivityunit", defaults))
    model.CapacityFactor = Param(
        model.REGION, model.TECHNOLOGY, model.TIMESLICE, model.YEAR, default=_d("capacityfactor", defaults),
    )
    model.AvailabilityFactor = Param(model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("availabilityfactor", defaults))
    model.ResidualCapacity = Param(model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("residualcapacity", defaults))
    _activity_ratio_index = (
        (Any,)
        if sparse_high_dim_params
        else (model.REGION, model.TECHNOLOGY, model.FUEL, model.MODE_OF_OPERATION, model.YEAR)
    )
    model.InputActivityRatio = Param(
        *_activity_ratio_index, default=_d("inputactivityratio", defaults),
    )
    model.OutputActivityRatio = Param(
        *_activity_ratio_index, default=_d("outputactivityratio", defaults),
    )

    # ====================================================================
    #    Parameters — Technology Costs
    # ====================================================================

    model.CapitalCost = Param(model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("capitalcost", defaults))
    model.VariableCost = Param(
        model.REGION, model.TECHNOLOGY, model.MODE_OF_OPERATION, model.YEAR,
        default=_d("variablecost", defaults),
    )
    model.FixedCost = Param(model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("fixedcost", defaults))

    # ====================================================================
    #    Parameters — Capacity Constraints
    # ====================================================================

    model.CapacityOfOneTechnologyUnit = Param(
        model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("capacityofonetechnologyunit", defaults),
    )
    model.TotalAnnualMaxCapacity = Param(
        model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("totalannualmaxcapacity", defaults),
    )
    model.TotalAnnualMinCapacity = Param(
        model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("totalannualmincapacity", defaults),
    )

    # ====================================================================
    #    Parameters — Investment Constraints
    # ====================================================================

    model.TotalAnnualMaxCapacityInvestment = Param(
        model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("totalannualmaxcapacityinvestment", defaults),
    )
    model.TotalAnnualMinCapacityInvestment = Param(
        model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("totalannualmincapacityinvestment", defaults),
    )

    # ====================================================================
    #    Parameters — Activity Constraints
    # ====================================================================

    model.TotalTechnologyAnnualActivityUpperLimit = Param(
        model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("totaltechnologyannualactivityupperlimit", defaults),
    )
    model.TotalTechnologyAnnualActivityLowerLimit = Param(
        model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("totaltechnologyannualactivitylowerlimit", defaults),
    )
    model.TotalTechnologyModelPeriodActivityUpperLimit = Param(
        model.REGION, model.TECHNOLOGY, default=_d("totaltechnologymodelperiodactivityupperlimit", defaults),
    )
    model.TotalTechnologyModelPeriodActivityLowerLimit = Param(
        model.REGION, model.TECHNOLOGY, default=_d("totaltechnologymodelperiodactivitylowerlimit", defaults),
    )

    # ====================================================================
    #    Parameters — Reserve Margin
    # ====================================================================

    model.ReserveMarginTagTechnology = Param(
        model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("reservemargintagtechnology", defaults),
    )
    model.ReserveMarginTagFuel = Param(model.REGION, model.FUEL, model.YEAR, default=_d("reservemargintagfuel", defaults))
    model.ReserveMargin = Param(model.REGION, model.YEAR, default=_d("reservemargin", defaults))

    # ====================================================================
    #    Parameters — RE Generation Target
    # ====================================================================

    model.RETagTechnology = Param(model.REGION, model.TECHNOLOGY, model.YEAR, default=_d("retagtechnology", defaults))
    model.RETagFuel = Param(model.REGION, model.FUEL, model.YEAR, default=_d("retagfuel", defaults))
    model.REMinProductionTarget = Param(model.REGION, model.YEAR, default=_d("reminproductiontarget", defaults))

    # ====================================================================
    #    Parameters — Emissions & Penalties
    # ====================================================================

    _emission_ratio_index = (
        (Any,)
        if sparse_high_dim_params
        else (model.REGION, model.TECHNOLOGY, model.EMISSION, model.MODE_OF_OPERATION, model.YEAR)
    )
    model.EmissionActivityRatio = Param(
        *_emission_ratio_index, default=_d("emissionactivityratio", defaults),
    )
    model.EmissionsPenalty = Param(model.REGION, model.EMISSION, model.YEAR, default=_d("emissionspenalty", defaults))
    model.AnnualExogenousEmission = Param(
        model.REGION, model.EMISSION, model.YEAR, default=_d("annualexogenousemission", defaults),
    )
    model.AnnualEmissionLimit = Param(
        model.REGION, model.EMISSION, model.YEAR, default=_d("annualemissionlimit", defaults),
    )
    model.ModelPeriodExogenousEmission = Param(model.REGION, model.EMISSION, default=_d("modelperiodexogenousemission", defaults))
    model.ModelPeriodEmissionLimit = Param(model.REGION, model.EMISSION, default=_d("modelperiodemissionlimit", defaults))

    # ====================================================================
    #    Parameters — MUIO
    # ====================================================================

    _input_capacity_ratio_index = (
        (Any,)
        if sparse_high_dim_params
        else (model.REGION, model.TECHNOLOGY, model.FUEL, model.YEAR)
    )
    model.InputToNewCapacityRatio = Param(
        *_input_capacity_ratio_index, within=Reals, default=_d("inputtonewcapacityratio", defaults),
    )
    model.InputToTotalCapacityRatio = Param(
        *_input_capacity_ratio_index, within=Reals, default=_d("inputtototalcapacityratio", defaults),
    )
    model.TechnologyActivityByModeLowerLimit = Param(
        model.REGION, model.TECHNOLOGY, model.MODE_OF_OPERATION, model.YEAR,
        within=Reals, default=_d("technologyactivitybymodelowerlimit", defaults),
    )
    model.TechnologyActivityByModeUpperLimit = Param(
        model.REGION, model.TECHNOLOGY, model.MODE_OF_OPERATION, model.YEAR,
        within=Reals, default=_d("technologyactivitybymodeupperlimit", defaults),
    )
    model.TechnologyActivityDecreaseByModeLimit = Param(
        model.REGION, model.TECHNOLOGY, model.MODE_OF_OPERATION, model.YEAR,
        within=Reals, default=_d("technologyactivitydecreasebymodelimit", defaults),
    )
    model.TechnologyActivityIncreaseByModeLimit = Param(
        model.REGION, model.TECHNOLOGY, model.MODE_OF_OPERATION, model.YEAR,
        within=Reals, default=_d("technologyactivityincreasebymodelimit", defaults),
    )
    model.EmissionToActivityChangeRatio = Param(
        *_emission_ratio_index,
        within=Reals, default=_d("emissiontoactivitychangeratio", defaults),
    )

    # ====================================================================
    #    Parameters — UDC (User-Defined Constraints)
    # ====================================================================

    if has_udc:
        model.UDCMultiplierTotalCapacity = Param(
            model.REGION, model.TECHNOLOGY, model.UDC, model.YEAR,
            within=Reals, default=_d("udcmultipliertotalcapacity", defaults),
        )
        model.UDCMultiplierNewCapacity = Param(
            model.REGION, model.TECHNOLOGY, model.UDC, model.YEAR,
            within=Reals, default=_d("udcmultipliernewcapacity", defaults),
        )
        model.UDCMultiplierActivity = Param(
            model.REGION, model.TECHNOLOGY, model.UDC, model.YEAR,
            within=Reals, default=_d("udcmultiplieractivity", defaults),
        )
        model.UDCConstant = Param(
            model.REGION, model.UDC, model.YEAR, within=Reals, default=_d("udcconstant", defaults),
        )
        model.UDCTag = Param(model.REGION, model.UDC, within=Reals, default=_d("udctag", defaults))

    # ====================================================================
    #    Parameters — Storage
    # ====================================================================

    if has_storage:
        model.DaySplit = Param(model.DAILYTIMEBRACKET, model.YEAR, default=_d("daysplit", defaults))
        model.Conversionls = Param(model.TIMESLICE, model.SEASON, default=_d("conversionls", defaults))
        model.Conversionld = Param(model.TIMESLICE, model.DAYTYPE, default=_d("conversionld", defaults))
        model.Conversionlh = Param(model.TIMESLICE, model.DAILYTIMEBRACKET, default=_d("conversionlh", defaults))
        model.DaysInDayType = Param(model.SEASON, model.DAYTYPE, model.YEAR, default=_d("daysindaytype", defaults))
        model.TechnologyToStorage = Param(
            model.REGION, model.TECHNOLOGY, model.STORAGE, model.MODE_OF_OPERATION, default=_d("technologytostorage", defaults),
        )
        model.TechnologyFromStorage = Param(
            model.REGION, model.TECHNOLOGY, model.STORAGE, model.MODE_OF_OPERATION, default=_d("technologyfromstorage", defaults),
        )
        model.StorageLevelStart = Param(model.REGION, model.STORAGE, default=_d("storagelevelstart", defaults))
        model.StorageMaxChargeRate = Param(model.REGION, model.STORAGE, default=_d("storagemaxchargerate", defaults))
        model.StorageMaxDischargeRate = Param(model.REGION, model.STORAGE, default=_d("storagemaxdischargerate", defaults))
        model.MinStorageCharge = Param(model.REGION, model.STORAGE, model.YEAR, default=_d("minstoragecharge", defaults))
        model.OperationalLifeStorage = Param(model.REGION, model.STORAGE, default=_d("operationallifestorage", defaults))
        model.CapitalCostStorage = Param(
            model.REGION, model.STORAGE, model.YEAR, default=_d("capitalcoststorage", defaults),
        )
        model.ResidualStorageCapacity = Param(
            model.REGION, model.STORAGE, model.YEAR, default=_d("residualstoragecapacity", defaults),
        )

    # ====================================================================
    #    Parameters — Disposal / Recovery (Max B/C)
    # ====================================================================

    model.DisposalCostPerCapacity = Param(model.REGION, model.TECHNOLOGY, default=_d("disposalcostpercapacity", defaults))
    model.RecoveryValuePerCapacity = Param(model.REGION, model.TECHNOLOGY, default=_d("recoveryvaluepercapacity", defaults))

    if sparse_emission_penalties:
        def _penalty_emission_index_init(m):
            return (
                (r, t, e, y)
                for r in m.REGION
                for e in m.EMISSION
                for y in m.YEAR
                if m.EmissionsPenalty[r, e, y] != 0
                for t in m.TECHNOLOGY
            )

        def _penalty_tech_year_index_init(m):
            active = {
                (r, t, y)
                for r, t, _e, y in m.EMISSION_PENALTY_INDEX
            }
            return sorted(active, key=lambda item: tuple(map(str, item)))

        model.EMISSION_PENALTY_INDEX = Set(dimen=4, initialize=_penalty_emission_index_init)
        model.EMISSION_PENALTY_TECH_YEAR_INDEX = Set(
            dimen=3, initialize=_penalty_tech_year_index_init
        )

    # ====================================================================
    #    Variables — Capacity
    # ====================================================================

    model.NumberOfNewTechnologyUnits = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeIntegers, initialize=0,
    )
    model.NewCapacity = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )

    # ====================================================================
    #    Variables — Activity
    # ====================================================================

    model.RateOfActivity = Var(
        model.REGION, model.TIMESLICE, model.TECHNOLOGY, model.MODE_OF_OPERATION, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )

    # ====================================================================
    #    Variables — Costing
    # ====================================================================

    model.VariableOperatingCost = Var(
        model.REGION, model.TECHNOLOGY, model.TIMESLICE, model.YEAR,
        domain=Reals, initialize=0.0,
    )
    model.SalvageValue = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    model.DiscountedSalvageValue = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    model.OperatingCost = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=Reals, initialize=0.0,
    )
    model.CapitalInvestment = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    model.DiscountedCapitalInvestment = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    model.DiscountedOperatingCost = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=Reals, initialize=0.0,
    )
    model.AnnualVariableOperatingCost = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=Reals, initialize=0.0,
    )
    model.AnnualFixedOperatingCost = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    model.TotalDiscountedCostByTechnology = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=Reals, initialize=0.0,
    )
    model.TotalDiscountedCost = Var(
        model.REGION, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )

    # ====================================================================
    #    Variables — Reserve Margin
    # ====================================================================

    model.TotalCapacityInReserveMargin = Var(
        model.REGION, model.YEAR, domain=NonNegativeReals, initialize=0.0,
    )
    model.DemandNeedingReserveMargin = Var(
        model.REGION, model.TIMESLICE, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )

    # ====================================================================
    #    Variables — RE Gen Target
    # ====================================================================

    model.TotalREProductionAnnual = Var(model.REGION, model.YEAR, initialize=0.0)
    model.RETotalProductionOfTargetFuelAnnual = Var(
        model.REGION, model.YEAR, initialize=0.0,
    )
    model.TotalTechnologyModelPeriodActivity = Var(
        model.REGION, model.TECHNOLOGY, initialize=0.0,
    )

    # ====================================================================
    #    Variables — Emissions
    # ====================================================================

    model.AnnualTechnologyEmissionByMode = Var(
        model.REGION, model.TECHNOLOGY, model.EMISSION, model.MODE_OF_OPERATION, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    model.AnnualTechnologyEmission = Var(
        model.REGION, model.TECHNOLOGY, model.EMISSION, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    if sparse_emission_penalties:
        model.AnnualTechnologyEmissionPenaltyByEmission = Var(
            model.EMISSION_PENALTY_INDEX,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.AnnualTechnologyEmissionsPenalty = Var(
            model.EMISSION_PENALTY_TECH_YEAR_INDEX,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.DiscountedTechnologyEmissionsPenalty = Var(
            model.EMISSION_PENALTY_TECH_YEAR_INDEX,
            domain=NonNegativeReals, initialize=0.0,
        )
    else:
        model.AnnualTechnologyEmissionPenaltyByEmission = Var(
            model.REGION, model.TECHNOLOGY, model.EMISSION, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.AnnualTechnologyEmissionsPenalty = Var(
            model.REGION, model.TECHNOLOGY, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.DiscountedTechnologyEmissionsPenalty = Var(
            model.REGION, model.TECHNOLOGY, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
    model.AnnualEmissions = Var(
        model.REGION, model.EMISSION, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    model.ModelPeriodEmissions = Var(
        model.REGION, model.EMISSION,
        domain=NonNegativeReals, initialize=0.0,
    )

    # ====================================================================
    #    Variables — Storage
    # ====================================================================

    if has_storage:
        model.NewStorageCapacity = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.SalvageValueStorage = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.StorageLevelYearStart = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.StorageLevelYearFinish = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.RateOfStorageCharge = Var(
            model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
            model.DAILYTIMEBRACKET, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.RateOfStorageDischarge = Var(
            model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
            model.DAILYTIMEBRACKET, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.NetChargeWithinYear = Var(
            model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
            model.DAILYTIMEBRACKET, model.YEAR,
            domain=Reals, initialize=0.0,
        )
        model.NetChargeWithinDay = Var(
            model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
            model.DAILYTIMEBRACKET, model.YEAR,
            domain=Reals, initialize=0.0,
        )
        model.StorageLevelSeasonStart = Var(
            model.REGION, model.STORAGE, model.SEASON, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.StorageLevelDayTypeStart = Var(
            model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.StorageLevelDayTypeFinish = Var(
            model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.StorageLowerLimit = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.StorageUpperLimit = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.AccumulatedNewStorageCapacity = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.CapitalInvestmentStorage = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.DiscountedCapitalInvestmentStorage = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.DiscountedSalvageValueStorage = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )
        model.TotalDiscountedStorageCost = Var(
            model.REGION, model.STORAGE, model.YEAR,
            domain=NonNegativeReals, initialize=0.0,
        )

    # ====================================================================
    #    Variables — Disposal / Recovery
    # ====================================================================

    model.DisposalCost = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    model.DiscountedDisposalCost = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    model.RecoveryValue = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )
    model.DiscountedRecoveryValue = Var(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        domain=NonNegativeReals, initialize=0.0,
    )

    # ####################################################################
    #    Objective Function
    # ####################################################################

    def ObjectiveFunction_rule(m):
        return sum(m.TotalDiscountedCost[r, y] for r in m.REGION for y in m.YEAR)
    model.OBJ = Objective(rule=ObjectiveFunction_rule, sense=minimize)

    # ####################################################################
    #    Constraints — Capacity Adequacy A
    # ####################################################################

    def TotalNewCapacity_2_rule(m, r, t, y):
        if m.CapacityOfOneTechnologyUnit[r, t, y] != 0:
            return (
                m.CapacityOfOneTechnologyUnit[r, t, y]
                * m.NumberOfNewTechnologyUnits[r, t, y]
                == m.NewCapacity[r, t, y]
            )
        return Constraint.Skip
    model.TotalNewCapacity_2 = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=TotalNewCapacity_2_rule,
    )

    # ConstraintCapacity: en cada (r,l,t,y) la suma de RateOfActivity por modo <=
    # (capacidad nueva acumulada + residual) * CapacityFactor * CapacityToActivityUnit.
    def ConstraintCapacity_rule(m, r, l, t, y):
        return (
            sum(m.RateOfActivity[r, l, t, mo, y] for mo in m.MODE_OF_OPERATION)
            <= (
                sum(
                    m.NewCapacity[r, t, yy]
                    for yy in m.YEAR
                    if ((y - yy < m.OperationalLife[r, t]) and (y - yy >= 0))
                )
                + m.ResidualCapacity[r, t, y]
            )
            * m.CapacityFactor[r, t, l, y]
            * m.CapacityToActivityUnit[r, t]
        )
    model.ConstraintCapacity = Constraint(
        model.REGION, model.TIMESLICE, model.TECHNOLOGY, model.YEAR,
        rule=ConstraintCapacity_rule,
    )

    # ####################################################################
    #    Constraints — Capacity Adequacy B
    # ####################################################################

    def PlannedMaintenance_rule(m, r, t, y):
        return (
            sum(
                m.RateOfActivity[r, l, t, mo, y] * m.YearSplit[l, y]
                for l in m.TIMESLICE
                for mo in m.MODE_OF_OPERATION
            )
            <= sum(
                (
                    sum(
                        m.NewCapacity[r, t, yy]
                        for yy in m.YEAR
                        if ((y - yy < m.OperationalLife[r, t]) and (y - yy >= 0))
                    )
                    + m.ResidualCapacity[r, t, y]
                )
                * m.CapacityFactor[r, t, l, y]
                * m.YearSplit[l, y]
                for l in m.TIMESLICE
            )
            * m.AvailabilityFactor[r, t, y]
            * m.CapacityToActivityUnit[r, t]
        )
    model.PlannedMaintenance = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=PlannedMaintenance_rule,
    )

    # ####################################################################
    #    Constraints — Energy Balance A (por timeslice: oferta >= demanda + inputs)
    # ####################################################################

    _activity_ratio_cache: dict = {}

    def _ensure_oar_iar_cache(m: object) -> None:
        if 'oar_fuels' in _activity_ratio_cache:
            return
        oar_fuels: set = set()
        iar_fuels: set = set()
        oar_tech_modes: dict = {}  # (r,f,y) -> [(t,mo)]
        iar_tech_modes: dict = {}  # (r,f,y) -> [(t,mo)]
        # Only iterate sparse non-zero entries (default=0 → _data omits zeros)
        for _r, _t, _f, _mo, _y in m.OutputActivityRatio._data:
            key = (_r, _f, _y)
            oar_fuels.add(key)
            if key not in oar_tech_modes:
                oar_tech_modes[key] = []
            oar_tech_modes[key].append((_t, _mo))
        for _r, _t, _f, _mo, _y in m.InputActivityRatio._data:
            key = (_r, _f, _y)
            iar_fuels.add(key)
            if key not in iar_tech_modes:
                iar_tech_modes[key] = []
            iar_tech_modes[key].append((_t, _mo))
        _activity_ratio_cache['oar_fuels'] = oar_fuels
        _activity_ratio_cache['iar_fuels'] = iar_fuels
        _activity_ratio_cache['oar_tech_modes'] = oar_tech_modes
        _activity_ratio_cache['iar_tech_modes'] = iar_tech_modes

    def EnergyBalanceEachTS5_rule(m, r, l, f, y):
        _ensure_oar_iar_cache(m)
        key = (r, f, y)
        has_oar = key in _activity_ratio_cache['oar_fuels']
        has_iar = key in _activity_ratio_cache['iar_fuels']
        if not has_oar and m.Demand[r, l, f, y] == 0 and not has_iar:
            return Constraint.Skip
        lhs = sum(
            m.RateOfActivity[r, l, t, mo, y]
            * m.OutputActivityRatio[r, t, f, mo, y]
            * m.YearSplit[l, y]
            for t, mo in _activity_ratio_cache['oar_tech_modes'].get(key, ())
        )
        rhs_inputs = sum(
            m.RateOfActivity[r, l, t, mo, y]
            * m.InputActivityRatio[r, t, f, mo, y]
            * m.YearSplit[l, y]
            for t, mo in _activity_ratio_cache['iar_tech_modes'].get(key, ())
        )
        return lhs >= m.Demand[r, l, f, y] + rhs_inputs
    model.EnergyBalanceEachTS5 = Constraint(
        model.REGION, model.TIMESLICE, model.FUEL, model.YEAR,
        rule=EnergyBalanceEachTS5_rule,
    )

    # ####################################################################
    #    Constraints — Energy Balance B (AccumulatedAnnualDemand)
    # ####################################################################

    def EnergyBalanceEachYear4_rule(m, r, f, y):
        _ensure_oar_iar_cache(m)
        key = (r, f, y)
        has_oar = key in _activity_ratio_cache['oar_fuels']
        has_iar = key in _activity_ratio_cache['iar_fuels']
        if not has_oar and m.AccumulatedAnnualDemand[r, f, y] == 0 and not has_iar:
            return Constraint.Skip
        lhs = sum(
            m.RateOfActivity[r, l, t, mo, y]
            * m.OutputActivityRatio[r, t, f, mo, y]
            * m.YearSplit[l, y]
            for t, mo in _activity_ratio_cache['oar_tech_modes'].get(key, ())
            for l in m.TIMESLICE
        )
        rhs_inputs = sum(
            m.RateOfActivity[r, l, t, mo, y]
            * m.InputActivityRatio[r, t, f, mo, y]
            * m.YearSplit[l, y]
            for t, mo in _activity_ratio_cache['iar_tech_modes'].get(key, ())
            for l in m.TIMESLICE
        )
        return lhs >= rhs_inputs + m.AccumulatedAnnualDemand[r, f, y]
    model.EnergyBalanceEachYear4 = Constraint(
        model.REGION, model.FUEL, model.YEAR,
        rule=EnergyBalanceEachYear4_rule,
    )

    # ####################################################################
    #    Constraints — Capital Costs
    # ####################################################################

    def UndiscountedCapitalInvestment_rule(m, r, t, y):
        return (
            m.CapitalCost[r, t, y]
            * m.NewCapacity[r, t, y]
            * m.CapitalRecoveryFactor[r, t]
            * m.PvAnnuity[r, t]
            == m.CapitalInvestment[r, t, y]
        )
    model.UndiscountedCapitalInvestment = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=UndiscountedCapitalInvestment_rule,
    )

    def DiscountedCapitalInvestment_rule(m, r, t, y):
        return (
            m.CapitalInvestment[r, t, y]
            / ((1 + m.DiscountRate[r]) ** (y - min(m.YEAR)))
            == m.DiscountedCapitalInvestment[r, t, y]
        )
    model.DiscountedCapitalInvestment_constraint = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=DiscountedCapitalInvestment_rule,
    )

    # ####################################################################
    #    Constraints — Operating Costs
    # ####################################################################

    def OperatingCostsVariable_rule(m, r, t, y):
        return (
            sum(
                sum(
                    m.RateOfActivity[r, l, t, mo, y] * m.YearSplit[l, y]
                    for l in m.TIMESLICE
                )
                * m.VariableCost[r, t, mo, y]
                for mo in m.MODE_OF_OPERATION
            )
            == m.AnnualVariableOperatingCost[r, t, y]
        )
    model.OperatingCostsVariable = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=OperatingCostsVariable_rule,
    )

    def OperatingCostsFixedAnnual_rule(m, r, t, y):
        return (
            (
                sum(
                    m.NewCapacity[r, t, yy]
                    for yy in m.YEAR
                    if ((y - yy < m.OperationalLife[r, t]) and (y - yy >= 0))
                )
                + m.ResidualCapacity[r, t, y]
            )
            * m.FixedCost[r, t, y]
            == m.AnnualFixedOperatingCost[r, t, y]
        )
    model.OperatingCostsFixedAnnual = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=OperatingCostsFixedAnnual_rule,
    )

    def OperatingCostsTotalAnnual_rule(m, r, t, y):
        return (
            m.AnnualFixedOperatingCost[r, t, y]
            + m.AnnualVariableOperatingCost[r, t, y]
            == m.OperatingCost[r, t, y]
        )
    model.OperatingCostsTotalAnnual = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=OperatingCostsTotalAnnual_rule,
    )

    def DiscountedOperatingCostsTotalAnnual_rule(m, r, t, y):
        return (
            m.OperatingCost[r, t, y]
            / ((1 + m.DiscountRate[r]) ** (y - min(m.YEAR) + 0.5))
            == m.DiscountedOperatingCost[r, t, y]
        )
    model.DiscountedOperatingCostsTotalAnnual = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=DiscountedOperatingCostsTotalAnnual_rule,
    )

    # ####################################################################
    #    Constraints — Total Discounted Costs
    # ####################################################################

    def TotalDiscountedCostByTechnology_rule(m, r, t, y):
        emission_penalty = (
            m.DiscountedTechnologyEmissionsPenalty[r, t, y]
            if not sparse_emission_penalties
            or (r, t, y) in m.EMISSION_PENALTY_TECH_YEAR_INDEX
            else 0.0
        )
        return (
            m.DiscountedOperatingCost[r, t, y]
            + m.DiscountedCapitalInvestment[r, t, y]
            + emission_penalty
            - m.DiscountedSalvageValue[r, t, y]
            + m.DiscountedDisposalCost[r, t, y]
            - m.DiscountedRecoveryValue[r, t, y]
            == m.TotalDiscountedCostByTechnology[r, t, y]
        )
    model.TotalDiscountedCostByTechnology_constraint = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=TotalDiscountedCostByTechnology_rule,
    )

    if has_storage:
        def TotalDiscountedCost_rule(m, r, y):
            return (
                sum(m.TotalDiscountedCostByTechnology[r, t, y] for t in m.TECHNOLOGY)
                + sum(m.TotalDiscountedStorageCost[r, s, y] for s in m.STORAGE)
                == m.TotalDiscountedCost[r, y]
            )
        model.TotalDiscountedCost_constraint = Constraint(
            model.REGION, model.YEAR, rule=TotalDiscountedCost_rule,
        )
    else:
        def TotalDiscountedCost_rule(m, r, y):
            return (
                sum(m.TotalDiscountedCostByTechnology[r, t, y] for t in m.TECHNOLOGY)
                == m.TotalDiscountedCost[r, y]
            )
        model.TotalDiscountedCost_constraint = Constraint(
            model.REGION, model.YEAR, rule=TotalDiscountedCost_rule,
        )

    # ####################################################################
    #    Constraints — Total Capacity Constraints
    # ####################################################################

    def TotalAnnualMaxCapacityConstraint_rule(m, r, t, y):
        if m.TotalAnnualMaxCapacity[r, t, y] == 9999999:
            return Constraint.Skip
        return (
            sum(
                m.NewCapacity[r, t, yy]
                for yy in m.YEAR
                if ((y - yy < m.OperationalLife[r, t]) and (y - yy >= 0))
            )
            + m.ResidualCapacity[r, t, y]
            <= m.TotalAnnualMaxCapacity[r, t, y]
        )
    model.TotalAnnualMaxCapacityConstraint = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=TotalAnnualMaxCapacityConstraint_rule,
    )

    def TotalAnnualMinCapacityConstraint_rule(m, r, t, y):
        return (
            sum(
                m.NewCapacity[r, t, yy]
                for yy in m.YEAR
                if ((y - yy < m.OperationalLife[r, t]) and (y - yy >= 0))
            )
            + m.ResidualCapacity[r, t, y]
            >= m.TotalAnnualMinCapacity[r, t, y]
        )
    model.TotalAnnualMinCapacityConstraint = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=TotalAnnualMinCapacityConstraint_rule,
    )

    # ####################################################################
    #    Constraints — Salvage Value
    # ####################################################################

    def SalvageValueAtEndOfPeriod1_rule(m, r, t, y):
        if (
            m.DepreciationMethod[r] == 1
            and ((y + m.OperationalLife[r, t] - 1) > max(m.YEAR))
            and m.DiscountRate[r] > 0
        ):
            return m.SalvageValue[r, t, y] == (
                m.CapitalCost[r, t, y]
                * m.NewCapacity[r, t, y]
                * m.CapitalRecoveryFactor[r, t]
                * m.PvAnnuity[r, t]
                * (
                    1
                    - (
                        ((1 + m.DiscountRate[r]) ** (max(m.YEAR) - y + 1) - 1)
                        / ((1 + m.DiscountRate[r]) ** m.OperationalLife[r, t] - 1)
                    )
                )
            )
        elif (
            m.DepreciationMethod[r] == 1
            and ((y + m.OperationalLife[r, t] - 1) > max(m.YEAR))
            and m.DiscountRate[r] == 0
        ) or (
            m.DepreciationMethod[r] == 2
            and (y + m.OperationalLife[r, t] - 1) > max(m.YEAR)
        ):
            return m.SalvageValue[r, t, y] == (
                m.CapitalCost[r, t, y]
                * m.NewCapacity[r, t, y]
                * m.CapitalRecoveryFactor[r, t]
                * m.PvAnnuity[r, t]
                * (1 - (max(m.YEAR) - y + 1) / m.OperationalLife[r, t])
            )
        return m.SalvageValue[r, t, y] == 0
    model.SalvageValueAtEndOfPeriod1 = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=SalvageValueAtEndOfPeriod1_rule,
    )

    def SalvageValueDiscountedToStartYear_rule(m, r, t, y):
        return m.DiscountedSalvageValue[r, t, y] == m.SalvageValue[r, t, y] / (
            (1 + m.DiscountRate[r]) ** (1 + max(m.YEAR) - min(m.YEAR))
        )
    model.SalvageValueDiscountedToStartYear = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=SalvageValueDiscountedToStartYear_rule,
    )

    # ####################################################################
    #    Constraints — New Capacity Constraints
    # ####################################################################

    def TotalAnnualMaxNewCapacityConstraint_rule(m, r, t, y):
        if m.TotalAnnualMaxCapacityInvestment[r, t, y] == 9999999:
            return Constraint.Skip
        return m.NewCapacity[r, t, y] <= m.TotalAnnualMaxCapacityInvestment[r, t, y]
    model.TotalAnnualMaxNewCapacityConstraint = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=TotalAnnualMaxNewCapacityConstraint_rule,
    )

    def TotalAnnualMinNewCapacityConstraint_rule(m, r, t, y):
        return m.NewCapacity[r, t, y] >= m.TotalAnnualMinCapacityInvestment[r, t, y]
    model.TotalAnnualMinNewCapacityConstraint = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=TotalAnnualMinNewCapacityConstraint_rule,
    )

    # ####################################################################
    #    Constraints — Annual Activity Constraints
    # ####################################################################

    def TotalAnnualTechnologyActivityUpperLimit_rule(m, r, t, y):
        if m.TotalTechnologyAnnualActivityUpperLimit[r, t, y] == 9999999:
            return Constraint.Skip
        return (
            sum(
                sum(m.RateOfActivity[r, l, t, mo, y] for mo in m.MODE_OF_OPERATION)
                * m.YearSplit[l, y]
                for l in m.TIMESLICE
            )
            <= m.TotalTechnologyAnnualActivityUpperLimit[r, t, y]
        )
    model.TotalAnnualTechnologyActivityUpperlimit = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=TotalAnnualTechnologyActivityUpperLimit_rule,
    )

    def TotalAnnualTechnologyActivityLowerLimit_rule(m, r, t, y):
        return (
            sum(
                sum(m.RateOfActivity[r, l, t, mo, y] for mo in m.MODE_OF_OPERATION)
                * m.YearSplit[l, y]
                for l in m.TIMESLICE
            )
            >= m.TotalTechnologyAnnualActivityLowerLimit[r, t, y]
        )
    model.TotalAnnualTechnologyActivityLowerlimit = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=TotalAnnualTechnologyActivityLowerLimit_rule,
    )

    # ####################################################################
    #    Constraints — Total Activity Constraints
    # ####################################################################

    def TotalModelHorizonTechnologyActivity_rule(m, r, t):
        return (
            sum(
                sum(
                    sum(m.RateOfActivity[r, l, t, mo, y] for mo in m.MODE_OF_OPERATION)
                    * m.YearSplit[l, y]
                    for l in m.TIMESLICE
                )
                for y in m.YEAR
            )
            == m.TotalTechnologyModelPeriodActivity[r, t]
        )
    model.TotalModelHorizonTechnologyActivity = Constraint(
        model.REGION, model.TECHNOLOGY,
        rule=TotalModelHorizonTechnologyActivity_rule,
    )

    def TotalModelHorizonTechnologyActivityUpperLimit_rule(m, r, t):
        if m.TotalTechnologyModelPeriodActivityUpperLimit[r, t] == 9999999:
            return Constraint.Skip
        return (
            m.TotalTechnologyModelPeriodActivity[r, t]
            <= m.TotalTechnologyModelPeriodActivityUpperLimit[r, t]
        )
    model.TotalModelHorizonTechnologyActivityUpperLimit = Constraint(
        model.REGION, model.TECHNOLOGY,
        rule=TotalModelHorizonTechnologyActivityUpperLimit_rule,
    )

    def TotalModelHorizonTechnologyActivityLowerLimit_rule(m, r, t):
        return (
            m.TotalTechnologyModelPeriodActivity[r, t]
            >= m.TotalTechnologyModelPeriodActivityLowerLimit[r, t]
        )
    model.TotalModelHorizonTechnologyActivityLowerLimit = Constraint(
        model.REGION, model.TECHNOLOGY,
        rule=TotalModelHorizonTechnologyActivityLowerLimit_rule,
    )

    # ####################################################################
    #    Constraints — Emissions Accounting (emisión por tecnología/modo, límites anuales y periodo)
    # ####################################################################

    def AnnualEmissionProductionByMode_rule(m, r, t, e, mo, y):
        if m.EmissionActivityRatio[r, t, e, mo, y] != 0:
            return (
                m.EmissionActivityRatio[r, t, e, mo, y]
                * sum(m.RateOfActivity[r, l, t, mo, y] * m.YearSplit[l, y] for l in m.TIMESLICE)
                == m.AnnualTechnologyEmissionByMode[r, t, e, mo, y]
            )
        return m.AnnualTechnologyEmissionByMode[r, t, e, mo, y] == 0
    model.AnnualEmissionProductionByMode = Constraint(
        model.REGION, model.TECHNOLOGY, model.EMISSION, model.MODE_OF_OPERATION, model.YEAR,
        rule=AnnualEmissionProductionByMode_rule,
    )

    def AnnualEmissionProduction_rule(m, r, t, e, y):
        return (
            sum(m.AnnualTechnologyEmissionByMode[r, t, e, mo, y] for mo in m.MODE_OF_OPERATION)
            == m.AnnualTechnologyEmission[r, t, e, y]
        )
    model.AnnualEmissionProduction = Constraint(
        model.REGION, model.TECHNOLOGY, model.EMISSION, model.YEAR,
        rule=AnnualEmissionProduction_rule,
    )

    def EmissionPenaltyByTechAndEmission_rule(m, r, t, e, y):
        return (
            m.AnnualTechnologyEmission[r, t, e, y] * m.EmissionsPenalty[r, e, y]
            == m.AnnualTechnologyEmissionPenaltyByEmission[r, t, e, y]
        )
    if sparse_emission_penalties:
        model.EmissionPenaltyByTechAndEmission = Constraint(
            model.EMISSION_PENALTY_INDEX,
            rule=EmissionPenaltyByTechAndEmission_rule,
        )
    else:
        model.EmissionPenaltyByTechAndEmission = Constraint(
            model.REGION, model.TECHNOLOGY, model.EMISSION, model.YEAR,
            rule=EmissionPenaltyByTechAndEmission_rule,
        )

    def EmissionsPenaltyByTechnology_rule(m, r, t, y):
        active_emissions = (
            (e for e in m.EMISSION if (r, t, e, y) in m.EMISSION_PENALTY_INDEX)
            if sparse_emission_penalties
            else iter(m.EMISSION)
        )
        return (
            sum(m.AnnualTechnologyEmissionPenaltyByEmission[r, t, e, y] for e in active_emissions)
            == m.AnnualTechnologyEmissionsPenalty[r, t, y]
        )
    _penalty_tech_year_index = (
        (model.EMISSION_PENALTY_TECH_YEAR_INDEX,)
        if sparse_emission_penalties
        else (model.REGION, model.TECHNOLOGY, model.YEAR)
    )
    model.EmissionsPenaltyByTechnology = Constraint(
        *_penalty_tech_year_index,
        rule=EmissionsPenaltyByTechnology_rule,
    )

    def DiscountedEmissionsPenaltyByTechnology_rule(m, r, t, y):
        return (
            m.AnnualTechnologyEmissionsPenalty[r, t, y]
            / ((1 + m.DiscountRate[r]) ** (y - min(m.YEAR) + 0.5))
            == m.DiscountedTechnologyEmissionsPenalty[r, t, y]
        )
    model.DiscountedEmissionsPenaltyByTechnology = Constraint(
        *_penalty_tech_year_index,
        rule=DiscountedEmissionsPenaltyByTechnology_rule,
    )

    def EmissionsAccounting1_rule(m, r, e, y):
        return (
            sum(m.AnnualTechnologyEmission[r, t, e, y] for t in m.TECHNOLOGY)
            == m.AnnualEmissions[r, e, y]
        )
    model.EmissionsAccounting1 = Constraint(
        model.REGION, model.EMISSION, model.YEAR,
        rule=EmissionsAccounting1_rule,
    )

    def EmissionsAccounting2_rule(m, r, e):
        return (
            sum(m.AnnualEmissions[r, e, y] for y in m.YEAR)
            == m.ModelPeriodEmissions[r, e] - m.ModelPeriodExogenousEmission[r, e]
        )
    model.EmissionsAccounting2 = Constraint(
        model.REGION, model.EMISSION,
        rule=EmissionsAccounting2_rule,
    )

    def AnnualEmissionsLimit_rule(m, r, e, y):
        if m.AnnualEmissionLimit[r, e, y] == 9999999:
            return Constraint.Skip
        return (
            m.AnnualEmissions[r, e, y] + m.AnnualExogenousEmission[r, e, y]
            <= m.AnnualEmissionLimit[r, e, y]
        )
    model.AnnualEmissionsLimit = Constraint(
        model.REGION, model.EMISSION, model.YEAR,
        rule=AnnualEmissionsLimit_rule,
    )

    def ModelPeriodEmissionsLimit_rule(m, r, e):
        if m.ModelPeriodEmissionLimit[r, e] == 9999999:
            return Constraint.Skip
        return m.ModelPeriodEmissions[r, e] <= m.ModelPeriodEmissionLimit[r, e]
    model.ModelPeriodEmissionsLimit = Constraint(
        model.REGION, model.EMISSION,
        rule=ModelPeriodEmissionsLimit_rule,
    )

    # ####################################################################
    #    Constraints — Reserve Margin (capacidad en reserva >= demanda * factor por timeslice)
    # ####################################################################

    def ReserveMargin_TechnologiesIncluded_rule(m, r, y):
        return (
            sum(
                (
                    sum(
                        m.NewCapacity[r, t, yy]
                        for yy in m.YEAR
                        if ((y - yy < m.OperationalLife[r, t]) and (y - yy >= 0))
                    )
                    + m.ResidualCapacity[r, t, y]
                )
                * m.ReserveMarginTagTechnology[r, t, y]
                * m.CapacityToActivityUnit[r, t]
                for t in m.TECHNOLOGY
            )
            == m.TotalCapacityInReserveMargin[r, y]
        )
    model.ReserveMargin_TechnologiesIncluded = Constraint(
        model.REGION, model.YEAR,
        rule=ReserveMargin_TechnologiesIncluded_rule,
    )

    def ReserveMargin_FuelsIncluded_rule(m, r, l, y):
        _ensure_oar_iar_cache(m)
        return (
            sum(
                sum(
                    m.RateOfActivity[r, l, t, mo, y] * m.OutputActivityRatio[r, t, f, mo, y]
                    for t, mo in _activity_ratio_cache['oar_tech_modes'].get((r, f, y), ())
                )
                * m.ReserveMarginTagFuel[r, f, y]
                for f in m.FUEL
                if m.ReserveMarginTagFuel[r, f, y] != 0
            )
            == m.DemandNeedingReserveMargin[r, l, y]
        )
    model.ReserveMargin_FuelsIncluded = Constraint(
        model.REGION, model.TIMESLICE, model.YEAR,
        rule=ReserveMargin_FuelsIncluded_rule,
    )

    def ReserveMarginConstraint_rule(m, r, l, y):
        return (
            m.DemandNeedingReserveMargin[r, l, y] * m.ReserveMargin[r, y]
            <= m.TotalCapacityInReserveMargin[r, y]
        )
    model.ReserveMarginConstraint = Constraint(
        model.REGION, model.TIMESLICE, model.YEAR,
        rule=ReserveMarginConstraint_rule,
    )

    # ####################################################################
    #    Constraints — MUIO
    # ####################################################################

    def LU1_rule(m, r, t, mo, y):
        if m.TechnologyActivityByModeUpperLimit[r, t, mo, y] == 0:
            return Constraint.Skip
        return (
            sum(m.RateOfActivity[r, l, t, mo, y] * m.YearSplit[l, y] for l in m.TIMESLICE)
            <= m.TechnologyActivityByModeUpperLimit[r, t, mo, y]
        )
    model.LU1_TechnologyActivityByModeUL = Constraint(
        model.REGION, model.TECHNOLOGY, model.MODE_OF_OPERATION, model.YEAR,
        rule=LU1_rule,
    )

    def LU2_rule(m, r, t, mo, y):
        if m.TechnologyActivityByModeLowerLimit[r, t, mo, y] == 0:
            return Constraint.Skip
        return (
            sum(m.RateOfActivity[r, l, t, mo, y] * m.YearSplit[l, y] for l in m.TIMESLICE)
            >= m.TechnologyActivityByModeLowerLimit[r, t, mo, y]
        )
    model.LU2_TechnologyActivityByModeLL = Constraint(
        model.REGION, model.TECHNOLOGY, model.MODE_OF_OPERATION, model.YEAR,
        rule=LU2_rule,
    )

    def LU3_rule(m, r, t, mo, y, yy):
        if (y - yy != 1) or (m.TechnologyActivityIncreaseByModeLimit[r, t, mo, yy] == 0):
            return Constraint.Skip
        return (
            sum(m.RateOfActivity[r, l, t, mo, y] * m.YearSplit[l, y] for l in m.TIMESLICE)
            <= (1 + m.TechnologyActivityIncreaseByModeLimit[r, t, mo, yy])
            * sum(m.RateOfActivity[r, l, t, mo, yy] * m.YearSplit[l, yy] for l in m.TIMESLICE)
        )
    model.LU3_TechnologyActivityIncreaseByMode = Constraint(
        model.REGION, model.TECHNOLOGY, model.MODE_OF_OPERATION, model.YEAR, model.YEAR,
        rule=LU3_rule,
    )

    def LU4_rule(m, r, t, mo, y, yy):
        if (y - yy != 1) or (m.TechnologyActivityDecreaseByModeLimit[r, t, mo, yy] == 0):
            return Constraint.Skip
        return (
            sum(m.RateOfActivity[r, l, t, mo, y] * m.YearSplit[l, y] for l in m.TIMESLICE)
            >= (1 - m.TechnologyActivityDecreaseByModeLimit[r, t, mo, yy])
            * sum(m.RateOfActivity[r, l, t, mo, yy] * m.YearSplit[l, yy] for l in m.TIMESLICE)
        )
    model.LU4_TechnologyActivityDecreaseByMode = Constraint(
        model.REGION, model.TECHNOLOGY, model.MODE_OF_OPERATION, model.YEAR, model.YEAR,
        rule=LU4_rule,
    )

    # ####################################################################
    #    Constraints — UDC (User-Defined Constraints: combinación lineal de capacidad/actividad vs constante)
    # ####################################################################

    if has_udc:
        def UDC1_rule(m, r, u, y):
            if m.UDCTag[r, u] != 0:
                return Constraint.Skip
            return (
                sum(
                    m.UDCMultiplierTotalCapacity[r, t, u, y]
                    * (
                        sum(
                            m.NewCapacity[r, t, yy]
                            for yy in m.YEAR
                            if ((y - yy < m.OperationalLife[r, t]) and (y - yy >= 0))
                        )
                        + m.ResidualCapacity[r, t, y]
                    )
                    for t in m.TECHNOLOGY
                )
                + sum(
                    m.UDCMultiplierNewCapacity[r, t, u, y] * m.NewCapacity[r, t, y]
                    for t in m.TECHNOLOGY
                )
                + sum(
                    m.UDCMultiplierActivity[r, t, u, y]
                    * sum(
                        m.RateOfActivity[r, l, t, mo, y] * m.YearSplit[l, y]
                        for l in m.TIMESLICE
                        for mo in m.MODE_OF_OPERATION
                    )
                    for t in m.TECHNOLOGY
                )
                <= m.UDCConstant[r, u, y]
            )
        model.UDC1_UserDefinedConstraintInequality = Constraint(
            model.REGION, model.UDC, model.YEAR, rule=UDC1_rule,
        )

        def UDC2_rule(m, r, u, y):
            if m.UDCTag[r, u] != 1:
                return Constraint.Skip
            return (
                sum(
                    m.UDCMultiplierTotalCapacity[r, t, u, y]
                    * (
                        sum(
                            m.NewCapacity[r, t, yy]
                            for yy in m.YEAR
                            if ((y - yy < m.OperationalLife[r, t]) and (y - yy >= 0))
                        )
                        + m.ResidualCapacity[r, t, y]
                    )
                    for t in m.TECHNOLOGY
                )
                + sum(
                    m.UDCMultiplierNewCapacity[r, t, u, y] * m.NewCapacity[r, t, y]
                    for t in m.TECHNOLOGY
                )
                + sum(
                    m.UDCMultiplierActivity[r, t, u, y]
                    * sum(
                        m.RateOfActivity[r, l, t, mo, y] * m.YearSplit[l, y]
                        for l in m.TIMESLICE
                        for mo in m.MODE_OF_OPERATION
                    )
                    for t in m.TECHNOLOGY
                )
                == m.UDCConstant[r, u, y]
            )
        model.UDC2_UserDefinedConstraintEquality = Constraint(
            model.REGION, model.UDC, model.YEAR, rule=UDC2_rule,
        )

    # ####################################################################
    #    Constraints — Disposal / Recovery (Max B/C)
    # ####################################################################

    def DisposalCostAtEndOfPeriod1_rule(m, r, t, y):
        return m.DisposalCost[r, t, y] == (
            m.DisposalCostPerCapacity[r, t] * m.CapitalCost[r, t, y] * m.NewCapacity[r, t, y]
        )
    model.DisposalCostAtEndOfPeriod1 = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=DisposalCostAtEndOfPeriod1_rule,
    )

    def DisposalCostDiscounted_rule(m, r, t, y):
        return m.DiscountedDisposalCost[r, t, y] == m.DisposalCost[r, t, y] / (
            (1 + m.DiscountRate[r]) ** (y + m.OperationalLife[r, t] - min(m.YEAR))
        )
    model.DiscountedDisposalCost_constraint = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=DisposalCostDiscounted_rule,
    )

    def RecoveryValueAtEndOfPeriod_rule(m, r, t, y):
        return m.RecoveryValue[r, t, y] == (
            m.RecoveryValuePerCapacity[r, t] * m.CapitalCost[r, t, y] * m.NewCapacity[r, t, y]
        )
    model.RecoveryValueAtEndOfPeriod = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=RecoveryValueAtEndOfPeriod_rule,
    )

    def RecoveryValueDiscounted_rule(m, r, t, y):
        return m.DiscountedRecoveryValue[r, t, y] == m.RecoveryValue[r, t, y] / (
            (1 + m.DiscountRate[r]) ** (y + m.OperationalLife[r, t] - min(m.YEAR))
        )
    model.RecoveryValueDiscounted_constraint = Constraint(
        model.REGION, model.TECHNOLOGY, model.YEAR,
        rule=RecoveryValueDiscounted_rule,
    )

    # ####################################################################
    #    Constraints — Storage
    # ####################################################################

    if has_storage:
        _add_storage_constraints(model)

    model.dual = Suffix(direction=Suffix.IMPORT)

    return model


# ========================================================================
#  Storage constraints (separadas en helper para legibilidad)
# ========================================================================

def _add_storage_constraints(model: AbstractModel) -> None:
    """Agrega todas las restricciones de almacenamiento al modelo."""

    # --- Storage equations ---

    def RateOfStorageCharge_rule(m, r, s, ls, ld, lh, y, t, mo):
        if m.TechnologyToStorage[r, t, s, mo] > 0:
            return (
                sum(
                    m.RateOfActivity[r, l, t, mo, y]
                    * m.TechnologyToStorage[r, t, s, mo]
                    * m.Conversionls[l, ls]
                    * m.Conversionld[l, ld]
                    * m.Conversionlh[l, lh]
                    for mo in m.MODE_OF_OPERATION
                    for l in m.TIMESLICE
                    for t in m.TECHNOLOGY
                )
                == m.RateOfStorageCharge[r, s, ls, ld, lh, y]
            )
        return Constraint.Skip
    model.RateOfStorageCharge_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR, model.TECHNOLOGY, model.MODE_OF_OPERATION,
        rule=RateOfStorageCharge_rule,
    )

    def RateOfStorageDischarge_rule(m, r, s, ls, ld, lh, y, t, mo):
        if m.TechnologyFromStorage[r, t, s, mo] > 0:
            return (
                sum(
                    m.RateOfActivity[r, l, t, mo, y]
                    * m.TechnologyFromStorage[r, t, s, mo]
                    * m.Conversionls[l, ls]
                    * m.Conversionld[l, ld]
                    * m.Conversionlh[l, lh]
                    for mo in m.MODE_OF_OPERATION
                    for l in m.TIMESLICE
                    for t in m.TECHNOLOGY
                )
                == m.RateOfStorageDischarge[r, s, ls, ld, lh, y]
            )
        return Constraint.Skip
    model.RateOfStorageDischarge_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR, model.TECHNOLOGY, model.MODE_OF_OPERATION,
        rule=RateOfStorageDischarge_rule,
    )

    def NetChargeWithinYear_rule(m, r, s, ls, ld, lh, y):
        return (
            sum(
                (m.RateOfStorageCharge[r, s, ls, ld, lh, y]
                 - m.RateOfStorageDischarge[r, s, ls, ld, lh, y])
                * m.YearSplit[l, y]
                * m.Conversionls[l, ls]
                * m.Conversionld[l, ld]
                * m.Conversionlh[l, lh]
                for l in m.TIMESLICE
            )
            == m.NetChargeWithinYear[r, s, ls, ld, lh, y]
        )
    model.NetChargeWithinYear_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=NetChargeWithinYear_rule,
    )

    def NetChargeWithinDay_rule(m, r, s, ls, ld, lh, y):
        return (
            (m.RateOfStorageCharge[r, s, ls, ld, lh, y]
             - m.RateOfStorageDischarge[r, s, ls, ld, lh, y])
            * m.DaySplit[lh, y]
            == m.NetChargeWithinDay[r, s, ls, ld, lh, y]
        )
    model.NetChargeWithinDay_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=NetChargeWithinDay_rule,
    )

    # --- Storage level tracking ---

    def StorageLevelYearStart_rule(m, r, s, y):
        if y == min(m.YEAR):
            return m.StorageLevelStart[r, s] == m.StorageLevelYearStart[r, s, y]
        return (
            m.StorageLevelYearStart[r, s, y - 1]
            + sum(
                m.NetChargeWithinYear[r, s, ls, ld, lh, y - 1]
                for ls in m.SEASON for ld in m.DAYTYPE for lh in m.DAILYTIMEBRACKET
            )
            == m.StorageLevelYearStart[r, s, y]
        )
    model.StorageLevelYearStart_constraint = Constraint(
        model.REGION, model.STORAGE, model.YEAR,
        rule=StorageLevelYearStart_rule,
    )

    def StorageLevelYearFinish_rule(m, r, s, y):
        if y < max(m.YEAR):
            return m.StorageLevelYearStart[r, s, y + 1] == m.StorageLevelYearFinish[r, s, y]
        return (
            m.StorageLevelYearStart[r, s, y]
            + sum(
                m.NetChargeWithinYear[r, s, ls, ld, lh, y - 1]
                for ls in m.SEASON for ld in m.DAYTYPE for lh in m.DAILYTIMEBRACKET
            )
            == m.StorageLevelYearFinish[r, s, y]
        )
    model.StorageLevelYearFinish_constraint = Constraint(
        model.REGION, model.STORAGE, model.YEAR,
        rule=StorageLevelYearFinish_rule,
    )

    def StorageLevelSeasonStart_rule(m, r, s, ls, y):
        if ls == min(m.SEASON):
            return m.StorageLevelYearStart[r, s, y] == m.StorageLevelSeasonStart[r, s, ls, y]
        return (
            m.StorageLevelSeasonStart[r, s, ls - 1, y]
            + sum(
                m.NetChargeWithinYear[r, s, ls - 1, ld, lh, y]
                for ld in m.DAYTYPE for lh in m.DAILYTIMEBRACKET
            )
            == m.StorageLevelSeasonStart[r, s, ls, y]
        )
    model.StorageLevelSeasonStart_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.YEAR,
        rule=StorageLevelSeasonStart_rule,
    )

    def StorageLevelDayTypeStart_rule(m, r, s, ls, ld, y):
        if ld == min(m.DAYTYPE):
            return (
                m.StorageLevelSeasonStart[r, s, ls, y]
                == m.StorageLevelDayTypeStart[r, s, ls, ld, y]
            )
        return (
            m.StorageLevelDayTypeStart[r, s, ls, ld - 1, y]
            + sum(
                m.NetChargeWithinDay[r, s, ls, ld - 1, lh, y]
                for lh in m.DAILYTIMEBRACKET
            )
            == m.StorageLevelDayTypeStart[r, s, ls, ld, y]
        )
    model.StorageLevelDayTypeStart_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE, model.YEAR,
        rule=StorageLevelDayTypeStart_rule,
    )

    def StorageLevelDayTypeFinish_rule(m, r, s, ls, ld, y):
        if ld == max(m.DAYTYPE):
            if ls == max(m.SEASON):
                return (
                    m.StorageLevelYearFinish[r, s, y]
                    == m.StorageLevelDayTypeFinish[r, s, ls, ld, y]
                )
            return (
                m.StorageLevelSeasonStart[r, s, ls + 1, y]
                == m.StorageLevelDayTypeFinish[r, s, ls, ld, y]
            )
        return (
            m.StorageLevelDayTypeFinish[r, s, ls, ld + 1, y]
            - sum(
                m.NetChargeWithinDay[r, s, ls, ld + 1, lh, y]
                for lh in m.DAILYTIMEBRACKET
            )
            * m.DaysInDayType[ls, ld + 1, y]
            == m.StorageLevelDayTypeFinish[r, s, ls, ld, y]
        )
    model.StorageLevelDayTypeFinish_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE, model.YEAR,
        rule=StorageLevelDayTypeFinish_rule,
    )

    # --- Storage bounds ---

    def LowerLimit_1TimeBracket1InstanceOfDayType1week_rule(m, r, s, ls, ld, lh, y):
        return (
            0
            <= (
                m.StorageLevelDayTypeStart[r, s, ls, ld, y]
                + sum(
                    m.NetChargeWithinDay[r, s, ls, ld, lhlh, y]
                    for lhlh in m.DAILYTIMEBRACKET if (lh - lhlh > 0)
                )
            )
            - m.StorageLowerLimit[r, s, y]
        )
    model.LowerLimit_1TimeBracket1InstanceOfDayType1week_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=LowerLimit_1TimeBracket1InstanceOfDayType1week_rule,
    )

    def LowerLimit_EndDaylyTimeBracketLastInstanceOfDayType1Week_rule(m, r, s, ls, ld, lh, y):
        if ld > min(m.DAYTYPE):
            return (
                0
                <= (
                    m.StorageLevelDayTypeStart[r, s, ls, ld, y]
                    - sum(
                        m.NetChargeWithinDay[r, s, ls, ld - 1, lhlh, y]
                        for lhlh in m.DAILYTIMEBRACKET if (lh - lhlh < 0)
                    )
                )
                - m.StorageLowerLimit[r, s, y]
            )
        return Constraint.Skip
    model.LowerLimit_EndDaylyTimeBracketLastInstanceOfDayType1Week_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=LowerLimit_EndDaylyTimeBracketLastInstanceOfDayType1Week_rule,
    )

    def LowerLimit_EndDaylyTimeBracketLastInstanceOfDayTypeLastWeek_rule(m, r, s, ls, ld, lh, y):
        return (
            0
            <= (
                m.StorageLevelDayTypeFinish[r, s, ls, ld, y]
                - sum(
                    m.NetChargeWithinDay[r, s, ls, ld, lhlh, y]
                    for lhlh in m.DAILYTIMEBRACKET if (lh - lhlh < 0)
                )
            )
            - m.StorageLowerLimit[r, s, y]
        )
    model.LowerLimit_EndDaylyTimeBracketLastInstanceOfDayTypeLastWeek_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=LowerLimit_EndDaylyTimeBracketLastInstanceOfDayTypeLastWeek_rule,
    )

    def LowerLimit_1TimeBracket1InstanceOfDayTypeLastweek_rule(m, r, s, ls, ld, lh, y):
        if ld > min(m.DAYTYPE):
            return (
                0
                <= (
                    m.StorageLevelDayTypeFinish[r, s, ls, ld - 1, y]
                    + sum(
                        m.NetChargeWithinDay[r, s, ls, ld, lhlh, y]
                        for lhlh in m.DAILYTIMEBRACKET if (lh - lhlh > 0)
                    )
                )
                - m.StorageLowerLimit[r, s, y]
            )
        return Constraint.Skip
    model.LowerLimit_1TimeBracket1InstanceOfDayTypeLastweek_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=LowerLimit_1TimeBracket1InstanceOfDayTypeLastweek_rule,
    )

    def UpperLimit_1TimeBracket1InstanceOfDayType1week_rule(m, r, s, ls, ld, lh, y):
        return (
            (
                m.StorageLevelDayTypeStart[r, s, ls, ld, y]
                + sum(
                    m.NetChargeWithinDay[r, s, ls, ld, lhlh, y]
                    for lhlh in m.DAILYTIMEBRACKET if (lh - lhlh > 0)
                )
            )
            - m.StorageUpperLimit[r, s, y]
            <= 0
        )
    model.UpperLimit_1TimeBracket1InstanceOfDayType1week_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=UpperLimit_1TimeBracket1InstanceOfDayType1week_rule,
    )

    def UpperLimit_EndDaylyTimeBracketLastInstanceOfDayType1Week_rule(m, r, s, ls, ld, lh, y):
        if ld > min(m.DAYTYPE):
            return (
                m.StorageLevelDayTypeStart[r, s, ls, ld, y]
                - sum(
                    m.NetChargeWithinDay[r, s, ls, ld - 1, lhlh, y]
                    for lhlh in m.DAILYTIMEBRACKET if (lh - lhlh < 0)
                )
            ) - m.StorageUpperLimit[r, s, y] <= 0
        return Constraint.Skip
    model.UpperLimit_EndDaylyTimeBracketLastInstanceOfDayType1Week_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=UpperLimit_EndDaylyTimeBracketLastInstanceOfDayType1Week_rule,
    )

    def UpperLimit_EndDaylyTimeBracketLastInstanceOfDayTypeLastWeek_rule(m, r, s, ls, ld, lh, y):
        return (
            m.StorageLevelDayTypeFinish[r, s, ls, ld, y]
            - sum(
                m.NetChargeWithinDay[r, s, ls, ld, lhlh, y]
                for lhlh in m.DAILYTIMEBRACKET if (lh - lhlh < 0)
            )
        ) - m.StorageUpperLimit[r, s, y] <= 0
    model.UpperLimit_EndDaylyTimeBracketLastInstanceOfDayTypeLastWeek_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=UpperLimit_EndDaylyTimeBracketLastInstanceOfDayTypeLastWeek_rule,
    )

    def UpperLimit_1TimeBracket1InstanceOfDayTypeLastweek_rule(m, r, s, ls, ld, lh, y):
        if ld > min(m.DAYTYPE):
            return (
                0
                >= (
                    m.StorageLevelDayTypeFinish[r, s, ls, ld - 1, y]
                    + sum(
                        m.NetChargeWithinDay[r, s, ls, ld, lhlh, y]
                        for lhlh in m.DAILYTIMEBRACKET if (lh - lhlh > 0)
                    )
                )
                - m.StorageUpperLimit[r, s, y]
            )
        return Constraint.Skip
    model.UpperLimit_1TimeBracket1InstanceOfDayTypeLastweek_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=UpperLimit_1TimeBracket1InstanceOfDayTypeLastweek_rule,
    )

    # --- Charge/discharge rate limits ---

    def MaxChargeConstraint_rule(m, r, s, ls, ld, lh, y):
        return m.RateOfStorageCharge[r, s, ls, ld, lh, y] <= m.StorageMaxChargeRate[r, s]
    model.MaxChargeConstraint_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=MaxChargeConstraint_rule,
    )

    def MaxDischargeConstraint_rule(m, r, s, ls, ld, lh, y):
        return m.RateOfStorageDischarge[r, s, ls, ld, lh, y] <= m.StorageMaxDischargeRate[r, s]
    model.MaxDischargeConstraint_constraint = Constraint(
        model.REGION, model.STORAGE, model.SEASON, model.DAYTYPE,
        model.DAILYTIMEBRACKET, model.YEAR,
        rule=MaxDischargeConstraint_rule,
    )

    # --- Storage investments ---

    def StorageUpperLimit_rule(m, r, s, y):
        return (
            m.AccumulatedNewStorageCapacity[r, s, y]
            + m.ResidualStorageCapacity[r, s, y]
            == m.StorageUpperLimit[r, s, y]
        )
    model.StorageUpperLimit_constraint = Constraint(
        model.REGION, model.STORAGE, model.YEAR, rule=StorageUpperLimit_rule,
    )

    def StorageLowerLimit_rule(m, r, s, y):
        return (
            m.MinStorageCharge[r, s, y] * m.StorageUpperLimit[r, s, y]
            == m.StorageLowerLimit[r, s, y]
        )
    model.StorageLowerLimit_constraint = Constraint(
        model.REGION, model.STORAGE, model.YEAR, rule=StorageLowerLimit_rule,
    )

    def TotalNewStorage_rule(m, r, s, y):
        return (
            sum(
                m.NewStorageCapacity[r, s, yy]
                for yy in m.YEAR
                if ((y - yy < m.OperationalLifeStorage[r, s]) and (y - yy >= 0))
            )
            == m.AccumulatedNewStorageCapacity[r, s, y]
        )
    model.TotalNewStorage_constraint = Constraint(
        model.REGION, model.STORAGE, model.YEAR, rule=TotalNewStorage_rule,
    )

    def UndiscountedCapitalInvestmentStorage_rule(m, r, s, y):
        return (
            m.CapitalCostStorage[r, s, y] * m.NewStorageCapacity[r, s, y]
            == m.CapitalInvestmentStorage[r, s, y]
        )
    model.UndiscountedCapitalInvestmentStorage_constraint = Constraint(
        model.REGION, model.STORAGE, model.YEAR,
        rule=UndiscountedCapitalInvestmentStorage_rule,
    )

    def DiscountingCapitalInvestmentStorage_rule(m, r, s, y):
        return (
            m.CapitalInvestmentStorage[r, s, y]
            / ((1 + m.DiscountRate[r]) ** (y - min(m.YEAR)))
            == m.DiscountedCapitalInvestmentStorage[r, s, y]
        )
    model.DiscountingCapitalInvestmentStorage_constraint = Constraint(
        model.REGION, model.STORAGE, model.YEAR,
        rule=DiscountingCapitalInvestmentStorage_rule,
    )

    def SalvageValueStorageAtEndOfPeriod_rule(m, r, s, y):
        if (
            m.DepreciationMethod[r] == 1
            and ((y + m.OperationalLifeStorage[r, s] - 1) > max(m.YEAR))
            and m.DiscountRate[r] > 0
        ):
            return m.SalvageValueStorage[r, s, y] == m.CapitalInvestmentStorage[r, s, y] * (
                1 - (
                    ((1 + m.DiscountRate[r]) ** (max(m.YEAR) - y + 1) - 1)
                    / ((1 + m.DiscountRate[r]) ** m.OperationalLifeStorage[r, s] - 1)
                )
            )
        elif (
            m.DepreciationMethod[r] == 1
            and ((y + m.OperationalLifeStorage[r, s] - 1) > max(m.YEAR))
            and m.DiscountRate[r] == 0
        ) or (
            m.DepreciationMethod[r] == 2
            and (y + m.OperationalLifeStorage[r, s] - 1) > max(m.YEAR)
        ):
            return m.SalvageValueStorage[r, s, y] == m.CapitalInvestmentStorage[r, s, y] * (
                1 - (max(m.YEAR) - y + 1) / m.OperationalLifeStorage[r, s]
            )
        return m.SalvageValueStorage[r, s, y] == 0
    model.SalvageValueStorageAtEndOfPeriod_constraint = Constraint(
        model.REGION, model.STORAGE, model.YEAR,
        rule=SalvageValueStorageAtEndOfPeriod_rule,
    )

    def SalvageValueStorageDiscountedToStartYear_rule(m, r, s, y):
        return (
            m.SalvageValueStorage[r, s, y]
            / ((1 + m.DiscountRate[r]) ** (max(m.YEAR) - min(m.YEAR) + 1))
            == m.DiscountedSalvageValueStorage[r, s, y]
        )
    model.SalvageValueDiscountedToStartYear_constraint = Constraint(
        model.REGION, model.STORAGE, model.YEAR,
        rule=SalvageValueStorageDiscountedToStartYear_rule,
    )

    def TotalDiscountedCostByStorage_rule(m, r, s, y):
        return (
            m.DiscountedCapitalInvestmentStorage[r, s, y]
            - m.DiscountedSalvageValueStorage[r, s, y]
            == m.TotalDiscountedStorageCost[r, s, y]
        )
    model.TotalDiscountedCostByStorage_constraint = Constraint(
        model.REGION, model.STORAGE, model.YEAR,
        rule=TotalDiscountedCostByStorage_rule,
    )
