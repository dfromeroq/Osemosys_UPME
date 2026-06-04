"""Catálogo de parámetros OSeMOSYS con ``default=`` en model_definition.

Fuente para migración Alembic (seed) y documentación de índices/categorías.
Los valores iniciales deben coincidir con :data:`OSEMOSYS_PARAM_DEFAULTS`.
"""

from __future__ import annotations

from typing import NamedTuple

from app.simulation.core.osemosys_defaults import OSEMOSYS_PARAM_DEFAULTS, _normalize_param_name


class CatalogEntry(NamedTuple):
    pyomo_name: str
    index_dims: str
    category: str
    description: str
    requires_storage: bool = False
    requires_udc: bool = False
    min_value: float | None = None
    max_value: float | None = None

    @property
    def param_key(self) -> str:
        return _normalize_param_name(self.pyomo_name)

    @property
    def initial_value(self) -> float:
        return float(OSEMOSYS_PARAM_DEFAULTS.get(self.param_key, 0.0))


MODEL_PARAMETER_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry("DiscountRate", "REGION", "global", "Tasa de descuento regional."),
    CatalogEntry("OperationalLife", "REGION,TECHNOLOGY", "global", "Vida operativa de la tecnología (años)."),
    CatalogEntry("DepreciationMethod", "REGION", "global", "Método de depreciación (1=estándar OSeMOSYS)."),
    CatalogEntry("AccumulatedAnnualDemand", "REGION,FUEL,YEAR", "demand", "Demanda anual acumulada."),
    CatalogEntry("SpecifiedAnnualDemand", "REGION,FUEL,YEAR", "demand", "Demanda anual especificada."),
    CatalogEntry(
        "SpecifiedDemandProfile",
        "REGION,FUEL,TIMESLICE,YEAR",
        "demand",
        "Perfil de demanda por timeslice.",
    ),
    CatalogEntry("Demand", "REGION,TIMESLICE,FUEL,YEAR", "demand", "Demanda derivada (default si no hay initialize)."),
    CatalogEntry("CapacityToActivityUnit", "REGION,TECHNOLOGY", "performance", "Factor capacidad → actividad."),
    CatalogEntry(
        "CapacityFactor",
        "REGION,TECHNOLOGY,TIMESLICE,YEAR",
        "performance",
        "Factor de capacidad por timeslice.",
    ),
    CatalogEntry("AvailabilityFactor", "REGION,TECHNOLOGY,YEAR", "performance", "Disponibilidad anual de la tecnología."),
    CatalogEntry("ResidualCapacity", "REGION,TECHNOLOGY,YEAR", "performance", "Capacidad residual."),
    CatalogEntry(
        "InputActivityRatio",
        "REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR",
        "performance",
        "Ratio de actividad de entrada.",
    ),
    CatalogEntry(
        "OutputActivityRatio",
        "REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR",
        "performance",
        "Ratio de actividad de salida.",
    ),
    CatalogEntry("CapitalCost", "REGION,TECHNOLOGY,YEAR", "costs", "Costo de capital."),
    CatalogEntry(
        "VariableCost",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,YEAR",
        "costs",
        "Costo variable por modo.",
    ),
    CatalogEntry("FixedCost", "REGION,TECHNOLOGY,YEAR", "costs", "Costo fijo."),
    CatalogEntry(
        "CapacityOfOneTechnologyUnit",
        "REGION,TECHNOLOGY,YEAR",
        "capacity",
        "Capacidad de una unidad de tecnología.",
    ),
    CatalogEntry(
        "TotalAnnualMaxCapacity",
        "REGION,TECHNOLOGY,YEAR",
        "capacity",
        "Límite máximo anual de capacidad total.",
    ),
    CatalogEntry(
        "TotalAnnualMinCapacity",
        "REGION,TECHNOLOGY,YEAR",
        "capacity",
        "Límite mínimo anual de capacidad total.",
    ),
    CatalogEntry(
        "TotalAnnualMaxCapacityInvestment",
        "REGION,TECHNOLOGY,YEAR",
        "capacity",
        "Límite máximo de inversión en capacidad anual.",
    ),
    CatalogEntry(
        "TotalAnnualMinCapacityInvestment",
        "REGION,TECHNOLOGY,YEAR",
        "capacity",
        "Límite mínimo de inversión en capacidad anual.",
    ),
    CatalogEntry(
        "TotalTechnologyAnnualActivityUpperLimit",
        "REGION,TECHNOLOGY,YEAR",
        "activity",
        "Límite superior de actividad anual.",
    ),
    CatalogEntry(
        "TotalTechnologyAnnualActivityLowerLimit",
        "REGION,TECHNOLOGY,YEAR",
        "activity",
        "Límite inferior de actividad anual.",
    ),
    CatalogEntry(
        "TotalTechnologyModelPeriodActivityUpperLimit",
        "REGION,TECHNOLOGY",
        "activity",
        "Límite superior de actividad en el horizonte.",
    ),
    CatalogEntry(
        "TotalTechnologyModelPeriodActivityLowerLimit",
        "REGION,TECHNOLOGY",
        "activity",
        "Límite inferior de actividad en el horizonte.",
    ),
    CatalogEntry(
        "ReserveMarginTagTechnology",
        "REGION,TECHNOLOGY,YEAR",
        "reserve",
        "Etiqueta de margen de reserva por tecnología.",
    ),
    CatalogEntry("ReserveMarginTagFuel", "REGION,FUEL,YEAR", "reserve", "Etiqueta de margen de reserva por combustible."),
    CatalogEntry("ReserveMargin", "REGION,YEAR", "reserve", "Margen de reserva."),
    CatalogEntry("RETagTechnology", "REGION,TECHNOLOGY,YEAR", "re", "Etiqueta ER por tecnología."),
    CatalogEntry("RETagFuel", "REGION,FUEL,YEAR", "re", "Etiqueta ER por combustible."),
    CatalogEntry("REMinProductionTarget", "REGION,YEAR", "re", "Meta mínima de producción renovable."),
    CatalogEntry(
        "EmissionActivityRatio",
        "REGION,TECHNOLOGY,EMISSION,MODE_OF_OPERATION,YEAR",
        "emissions",
        "Ratio de emisión por actividad.",
    ),
    CatalogEntry("EmissionsPenalty", "REGION,EMISSION,YEAR", "emissions", "Penalización por emisiones."),
    CatalogEntry(
        "AnnualExogenousEmission",
        "REGION,EMISSION,YEAR",
        "emissions",
        "Emisión exógena anual.",
    ),
    CatalogEntry("AnnualEmissionLimit", "REGION,EMISSION,YEAR", "emissions", "Límite de emisión anual."),
    CatalogEntry(
        "ModelPeriodExogenousEmission",
        "REGION,EMISSION",
        "emissions",
        "Emisión exógena del periodo del modelo.",
    ),
    CatalogEntry(
        "ModelPeriodEmissionLimit",
        "REGION,EMISSION",
        "emissions",
        "Límite de emisión del periodo del modelo.",
    ),
    CatalogEntry(
        "InputToNewCapacityRatio",
        "REGION,TECHNOLOGY,FUEL,YEAR",
        "muio",
        "Ratio insumo a nueva capacidad (MUIO).",
    ),
    CatalogEntry(
        "InputToTotalCapacityRatio",
        "REGION,TECHNOLOGY,FUEL,YEAR",
        "muio",
        "Ratio insumo a capacidad total (MUIO).",
    ),
    CatalogEntry(
        "TechnologyActivityByModeLowerLimit",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,YEAR",
        "muio",
        "Límite inferior de actividad por modo.",
    ),
    CatalogEntry(
        "TechnologyActivityByModeUpperLimit",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,YEAR",
        "muio",
        "Límite superior de actividad por modo.",
    ),
    CatalogEntry(
        "TechnologyActivityDecreaseByModeLimit",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,YEAR",
        "muio",
        "Límite de disminución de actividad por modo.",
    ),
    CatalogEntry(
        "TechnologyActivityIncreaseByModeLimit",
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,YEAR",
        "muio",
        "Límite de aumento de actividad por modo.",
    ),
    CatalogEntry(
        "EmissionToActivityChangeRatio",
        "REGION,TECHNOLOGY,EMISSION,MODE_OF_OPERATION,YEAR",
        "emissions",
        "Ratio cambio emisión-actividad.",
    ),
    CatalogEntry(
        "UDCMultiplierTotalCapacity",
        "REGION,TECHNOLOGY,UDC,YEAR",
        "udc",
        "Multiplicador UDC sobre capacidad total.",
        requires_udc=True,
    ),
    CatalogEntry(
        "UDCMultiplierNewCapacity",
        "REGION,TECHNOLOGY,UDC,YEAR",
        "udc",
        "Multiplicador UDC sobre nueva capacidad.",
        requires_udc=True,
    ),
    CatalogEntry(
        "UDCMultiplierActivity",
        "REGION,TECHNOLOGY,UDC,YEAR",
        "udc",
        "Multiplicador UDC sobre actividad.",
        requires_udc=True,
    ),
    CatalogEntry("UDCConstant", "REGION,UDC,YEAR", "udc", "Constante RHS de UDC.", requires_udc=True),
    CatalogEntry(
        "UDCTag",
        "REGION,UDC",
        "udc",
        "Tipo de restricción UDC (0=≤, 1==, 2=omitir).",
        requires_udc=True,
        min_value=0.0,
        max_value=2.0,
    ),
    CatalogEntry(
        "DaySplit",
        "DAILYTIMEBRACKET,YEAR",
        "storage",
        "Fracción del día por bracket.",
        requires_storage=True,
    ),
    CatalogEntry("Conversionls", "TIMESLICE,SEASON", "storage", "Conversión timeslice-estación.", requires_storage=True),
    CatalogEntry("Conversionld", "TIMESLICE,DAYTYPE", "storage", "Conversión timeslice-tipo de día.", requires_storage=True),
    CatalogEntry(
        "Conversionlh",
        "TIMESLICE,DAILYTIMEBRACKET",
        "storage",
        "Conversión timeslice-bracket horario.",
        requires_storage=True,
    ),
    CatalogEntry(
        "DaysInDayType",
        "SEASON,DAYTYPE,YEAR",
        "storage",
        "Días por tipo de día.",
        requires_storage=True,
    ),
    CatalogEntry(
        "TechnologyToStorage",
        "REGION,TECHNOLOGY,STORAGE,MODE_OF_OPERATION",
        "storage",
        "Tecnología hacia almacenamiento.",
        requires_storage=True,
    ),
    CatalogEntry(
        "TechnologyFromStorage",
        "REGION,TECHNOLOGY,STORAGE,MODE_OF_OPERATION",
        "storage",
        "Tecnología desde almacenamiento.",
        requires_storage=True,
    ),
    CatalogEntry(
        "StorageLevelStart",
        "REGION,STORAGE",
        "storage",
        "Nivel inicial de almacenamiento.",
        requires_storage=True,
    ),
    CatalogEntry(
        "StorageMaxChargeRate",
        "REGION,STORAGE",
        "storage",
        "Tasa máxima de carga.",
        requires_storage=True,
    ),
    CatalogEntry(
        "StorageMaxDischargeRate",
        "REGION,STORAGE",
        "storage",
        "Tasa máxima de descarga.",
        requires_storage=True,
    ),
    CatalogEntry(
        "MinStorageCharge",
        "REGION,STORAGE,YEAR",
        "storage",
        "Carga mínima de almacenamiento.",
        requires_storage=True,
    ),
    CatalogEntry(
        "OperationalLifeStorage",
        "REGION,STORAGE",
        "storage",
        "Vida operativa del almacenamiento.",
        requires_storage=True,
    ),
    CatalogEntry(
        "CapitalCostStorage",
        "REGION,STORAGE,YEAR",
        "storage",
        "Costo de capital de almacenamiento.",
        requires_storage=True,
    ),
    CatalogEntry(
        "ResidualStorageCapacity",
        "REGION,STORAGE,YEAR",
        "storage",
        "Capacidad residual de almacenamiento.",
        requires_storage=True,
    ),
    CatalogEntry(
        "DisposalCostPerCapacity",
        "REGION,TECHNOLOGY",
        "costs",
        "Costo de disposición por unidad de capacidad.",
    ),
    CatalogEntry(
        "RecoveryValuePerCapacity",
        "REGION,TECHNOLOGY",
        "costs",
        "Valor de recuperación por unidad de capacidad.",
    ),
)
