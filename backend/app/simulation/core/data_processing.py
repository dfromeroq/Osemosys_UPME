"""Procesamiento de datos: PostgreSQL → CSVs temporales.

Replica las celdas 4-13 y 17-19 del notebook:
  - Lee datos de BD (osemosys_param_value con JOINs)
  - Genera CSVs para sets y parámetros
  - Completa matrices (ActivityRatio, Emission, Cost)
  - Procesa emisiones a la entrada
  - Parametriza UDC

Flujo: run_data_processing() → export_scenario_to_csv() → completar matrices
       → process_and_save_emission_ratios() → ensure_udc_csvs() → apply_udc_config().
"""

from __future__ import annotations

import itertools
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.orm import Session

# Tablas del esquema osemosys y modelos de catálogo (región, tecnología, combustible, etc.)
from app.db.dialect import osemosys_table
from app.models import (
    Dailytimebracket,
    Daytype,
    Emission,
    Fuel,
    ModeOfOperation,
    Region,
    Scenario,
    Season,
    StorageSet,
    Technology,
    Timeslice,
    UdcSet,
)
from app.simulation.core.mode_of_operation_normalize import (
    normalize_mode_of_operation_scalar,
    normalize_mode_of_operation_series,
)

logger = logging.getLogger(__name__)

# Mapeo: nombre del parámetro OSeMOSYS → lista de dimensiones (columnas) del CSV.
# Define el índice de cada parámetro para leer correctamente la fila de la BD.
PARAM_INDEX: dict[str, list[str]] = {
    "YearSplit":                      ["TIMESLICE", "YEAR"],
    "DiscountRate":                   ["REGION"],
    "DepreciationMethod":             ["REGION"],
    "OperationalLife":                ["REGION", "TECHNOLOGY"],
    "CapacityToActivityUnit":         ["REGION", "TECHNOLOGY"],
    "CapacityOfOneTechnologyUnit":    ["REGION", "TECHNOLOGY", "YEAR"],
    "CapacityFactor":                 ["REGION", "TECHNOLOGY", "TIMESLICE", "YEAR"],
    "AvailabilityFactor":             ["REGION", "TECHNOLOGY", "YEAR"],
    "ResidualCapacity":               ["REGION", "TECHNOLOGY", "YEAR"],
    "InputActivityRatio":             ["REGION", "TECHNOLOGY", "FUEL", "MODE_OF_OPERATION", "YEAR"],
    "OutputActivityRatio":            ["REGION", "TECHNOLOGY", "FUEL", "MODE_OF_OPERATION", "YEAR"],
    "CapitalCost":                    ["REGION", "TECHNOLOGY", "YEAR"],
    "VariableCost":                   ["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"],
    "FixedCost":                      ["REGION", "TECHNOLOGY", "YEAR"],
    "TotalAnnualMaxCapacity":                   ["REGION", "TECHNOLOGY", "YEAR"],
    "TotalAnnualMinCapacity":                   ["REGION", "TECHNOLOGY", "YEAR"],
    "TotalAnnualMaxCapacityInvestment":         ["REGION", "TECHNOLOGY", "YEAR"],
    "TotalAnnualMinCapacityInvestment":         ["REGION", "TECHNOLOGY", "YEAR"],
    "TotalTechnologyAnnualActivityUpperLimit":  ["REGION", "TECHNOLOGY", "YEAR"],
    "TotalTechnologyAnnualActivityLowerLimit":  ["REGION", "TECHNOLOGY", "YEAR"],
    "TotalTechnologyModelPeriodActivityUpperLimit": ["REGION", "TECHNOLOGY"],
    "TotalTechnologyModelPeriodActivityLowerLimit": ["REGION", "TECHNOLOGY"],
    "ReserveMarginTagTechnology":     ["REGION", "TECHNOLOGY", "YEAR"],
    "ReserveMarginTagFuel":           ["REGION", "FUEL", "YEAR"],
    "ReserveMargin":                  ["REGION", "YEAR"],
    "RETagTechnology":                ["REGION", "TECHNOLOGY", "YEAR"],
    "RETagFuel":                      ["REGION", "FUEL", "YEAR"],
    "REMinProductionTarget":          ["REGION", "YEAR"],
    "AccumulatedAnnualDemand":        ["REGION", "FUEL", "YEAR"],
    "SpecifiedAnnualDemand":          ["REGION", "FUEL", "YEAR"],
    "SpecifiedDemandProfile":         ["REGION", "FUEL", "TIMESLICE", "YEAR"],
    "EmissionActivityRatio":          ["REGION", "TECHNOLOGY", "EMISSION", "MODE_OF_OPERATION", "YEAR"],
    "EmissionsPenalty":               ["REGION", "EMISSION", "YEAR"],
    "AnnualExogenousEmission":        ["REGION", "EMISSION", "YEAR"],
    "AnnualEmissionLimit":            ["REGION", "EMISSION", "YEAR"],
    "ModelPeriodExogenousEmission":   ["REGION", "EMISSION"],
    "ModelPeriodEmissionLimit":       ["REGION", "EMISSION"],
    "TechnologyActivityByModeUpperLimit":      ["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"],
    "TechnologyActivityByModeLowerLimit":      ["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"],
    "TechnologyActivityIncreaseByModeLimit":   ["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"],
    "TechnologyActivityDecreaseByModeLimit":   ["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"],
    "InputToNewCapacityRatio":        ["REGION", "TECHNOLOGY", "FUEL", "YEAR"],
    "InputToTotalCapacityRatio":      ["REGION", "TECHNOLOGY", "FUEL", "YEAR"],
    "EmissionToActivityChangeRatio":  ["REGION", "TECHNOLOGY", "EMISSION", "MODE_OF_OPERATION", "YEAR"],
    "DisposalCostPerCapacity":        ["REGION", "TECHNOLOGY"],
    "RecoveryValuePerCapacity":       ["REGION", "TECHNOLOGY"],
    "UDCMultiplierTotalCapacity":     ["REGION", "TECHNOLOGY", "UDC", "YEAR"],
    "UDCMultiplierNewCapacity":       ["REGION", "TECHNOLOGY", "UDC", "YEAR"],
    "UDCMultiplierActivity":          ["REGION", "TECHNOLOGY", "UDC", "YEAR"],
    "UDCConstant":                    ["REGION", "UDC", "YEAR"],
    "UDCTag":                         ["REGION", "UDC"],
    "TechnologyToStorage":            ["REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION"],
    "TechnologyFromStorage":          ["REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION"],
    "StorageLevelStart":              ["REGION", "STORAGE"],
    "StorageMaxChargeRate":           ["REGION", "STORAGE"],
    "StorageMaxDischargeRate":        ["REGION", "STORAGE"],
    "MinStorageCharge":               ["REGION", "STORAGE", "YEAR"],
    "OperationalLifeStorage":         ["REGION", "STORAGE"],
    "CapitalCostStorage":             ["REGION", "STORAGE", "YEAR"],
    "ResidualStorageCapacity":        ["REGION", "STORAGE", "YEAR"],
    "DaySplit":                       ["DAILYTIMEBRACKET", "YEAR"],
    "Conversionls":                   ["TIMESLICE", "SEASON"],
    "Conversionld":                   ["TIMESLICE", "DAYTYPE"],
    "Conversionlh":                   ["TIMESLICE", "DAILYTIMEBRACKET"],
    "DaysInDayType":                  ["SEASON", "DAYTYPE", "YEAR"],
    "DiscountRateIdv":                ["REGION", "TECHNOLOGY"],
}

# Posición de cada dimensión en la fila devuelta por _resolved_query() (columna 0 = param_name, 1+ = dimensiones).
_DIM_COL: dict[str, int] = {
    "REGION": 0, "TECHNOLOGY": 1, "FUEL": 2, "EMISSION": 3,
    "TIMESLICE": 4, "MODE_OF_OPERATION": 5, "SEASON": 6, "DAYTYPE": 7,
    "DAILYTIMEBRACKET": 8, "STORAGE": 9, "UDC": 10, "YEAR": 11,
}


def normalize_mode_of_operation_in_csv_dir(csv_dir: str) -> None:
    """Normaliza MODE_OF_OPERATION en MODE_OF_OPERATION.csv y en parámetros que la incluyen."""
    moo_path = os.path.join(csv_dir, "MODE_OF_OPERATION.csv")
    if os.path.exists(moo_path):
        df = pd.read_csv(moo_path)
        if not df.empty and "VALUE" in df.columns:
            df["VALUE"] = normalize_mode_of_operation_series(df["VALUE"])
            df = df[df["VALUE"] != ""]
            df = df.drop_duplicates(subset=["VALUE"], keep="first")
            df.to_csv(moo_path, index=False)

    for pname, cols in PARAM_INDEX.items():
        if "MODE_OF_OPERATION" not in cols:
            continue
        ppath = os.path.join(csv_dir, f"{pname}.csv")
        if not os.path.exists(ppath):
            continue
        df = pd.read_csv(ppath)
        if df.empty or "MODE_OF_OPERATION" not in df.columns:
            continue
        df["MODE_OF_OPERATION"] = normalize_mode_of_operation_series(df["MODE_OF_OPERATION"])
        df.to_csv(ppath, index=False)


def _resolved_query():
    """Construye la consulta SQL que une osemosys_param_value con todas las tablas de catálogo.
    Devuelve param_name, region, technology, fuel, emission, timeslice, mode_of_operation,
    season, daytype, dailytimebracket, storage, udc, year, value para id_scenario dado.
    """
    p = osemosys_table("osemosys_param_value")
    region = osemosys_table("region")
    technology = osemosys_table("technology")
    fuel = osemosys_table("fuel")
    emission = osemosys_table("emission")
    timeslice = osemosys_table("timeslice")
    mode_of_operation = osemosys_table("mode_of_operation")
    season = osemosys_table("season")
    daytype = osemosys_table("daytype")
    dailytimebracket = osemosys_table("dailytimebracket")
    storage_set = osemosys_table("storage_set")
    udc_set = osemosys_table("udc_set")
    return text(f"""
        SELECT
            p.param_name,
            r.name       AS region,
            t.name       AS technology,
            f.name       AS fuel,
            e.name       AS emission,
            ts.code      AS timeslice,
            mo.code      AS mode_of_operation,
            s.code       AS season,
            dt.code      AS daytype,
            dtb.code     AS dailytimebracket,
            st.code      AS storage,
            u.code       AS udc,
            p.year,
            p.value
        FROM {p} p
        LEFT JOIN {region} r             ON p.id_region = r.id
        LEFT JOIN {technology} t         ON p.id_technology = t.id
        LEFT JOIN {fuel} f               ON p.id_fuel = f.id
        LEFT JOIN {emission} e           ON p.id_emission = e.id
        LEFT JOIN {timeslice} ts         ON p.id_timeslice = ts.id
        LEFT JOIN {mode_of_operation} mo ON p.id_mode_of_operation = mo.id
        LEFT JOIN {season} s             ON p.id_season = s.id
        LEFT JOIN {daytype} dt           ON p.id_daytype = dt.id
        LEFT JOIN {dailytimebracket} dtb ON p.id_dailytimebracket = dtb.id
        LEFT JOIN {storage_set} st       ON p.id_storage_set = st.id
        LEFT JOIN {udc_set} u            ON p.id_udc_set = u.id
        WHERE p.id_scenario = :scenario_id
        ORDER BY p.param_name, p.id
    """)


# Para cada set OSeMOSYS: (nombre_set, modelo SQLAlchemy, atributo para el valor).
# Se usa en _load_catalog_lookups para mapear id <-> nombre/código.
_CATALOG_MAP: list[tuple[str, type, str]] = [
    ("REGION",            Region,            "name"),
    ("TECHNOLOGY",        Technology,        "name"),
    ("FUEL",              Fuel,              "name"),
    ("EMISSION",          Emission,          "name"),
    ("TIMESLICE",         Timeslice,         "code"),
    ("MODE_OF_OPERATION", ModeOfOperation,   "code"),
    ("SEASON",            Season,            "code"),
    ("DAYTYPE",           Daytype,           "code"),
    ("DAILYTIMEBRACKET",  Dailytimebracket,  "code"),
    ("STORAGE",           StorageSet,        "code"),
    ("UDC",               UdcSet,            "code"),
]


@dataclass
class ProcessingResult:
    """Metadatos del procesamiento de datos.
    Contiene flags (has_storage, has_udc), sets derivados, conteo de parámetros
    y diccionarios id_by_name / name_by_id para región, tecnología, combustible, emisión y almacenamiento.
    """
    has_storage: bool = False
    has_udc: bool = False
    sets: dict[str, list] = field(default_factory=dict)
    param_count: int = 0
    region_id_by_name: dict[str, int] = field(default_factory=dict)
    technology_id_by_name: dict[str, int] = field(default_factory=dict)
    fuel_id_by_name: dict[str, int] = field(default_factory=dict)
    emission_id_by_name: dict[str, int] = field(default_factory=dict)
    timeslice_id_by_name: dict[str, int] = field(default_factory=dict)
    mode_of_operation_id_by_name: dict[str, int] = field(default_factory=dict)
    season_id_by_name: dict[str, int] = field(default_factory=dict)
    daytype_id_by_name: dict[str, int] = field(default_factory=dict)
    dailytimebracket_id_by_name: dict[str, int] = field(default_factory=dict)
    storage_id_by_name: dict[str, int] = field(default_factory=dict)
    region_name_by_id: dict[int, str] = field(default_factory=dict)
    technology_name_by_id: dict[int, str] = field(default_factory=dict)
    fuel_name_by_id: dict[int, str] = field(default_factory=dict)
    emission_name_by_id: dict[int, str] = field(default_factory=dict)
    storage_name_by_id: dict[int, str] = field(default_factory=dict)
    # Reporte de calidad de datos detectado durante el procesamiento.
    # Estructura: ver app.simulation.core.data_validation.DataQualityReport.to_dict()
    data_quality_warnings: dict = field(default_factory=dict)


def _load_catalog_lookups(db: Session) -> dict[str, dict]:
    """Carga desde la BD los mapeos id↔nombre/código para cada set (REGION, TECHNOLOGY, etc.)."""
    lookups: dict[str, dict] = {}
    for set_name, model_cls, attr in _CATALOG_MAP:
        rows = db.execute(select(model_cls)).scalars().all()
        id_to_name = {r.id: getattr(r, attr) for r in rows}
        name_to_id = {v: k for k, v in id_to_name.items()}
        lookups[set_name] = {"id_to_name": id_to_name, "name_to_id": name_to_id}
    return lookups


def _get_scenario_processing_mode(db: Session, *, scenario_id: int) -> str:
    """Retorna el modo de procesamiento configurado para el escenario."""
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        return "STANDARD"
    return str(getattr(scenario, "processing_mode", "STANDARD") or "STANDARD").upper()


# ========================================================================
#  Paso 1: BD → CSVs (sets + parámetros)
# ========================================================================

def export_scenario_to_csv(
    db: Session,
    *,
    scenario_id: int,
    csv_dir: str,
) -> ProcessingResult:
    """Lee datos de BD y genera CSVs para sets y parámetros.
    1) Ejecuta _resolved_query y agrupa por param_name en param_rows.
    2) Construye sets desde parámetros (YearSplit→TIMESLICE/YEAR, OutputActivityRatio→REGION/TECH/FUEL/MODE, etc.).
    3) Agrega timeslices a uno solo si hay varios; excluye años con YearSplit=0.
    4) Filtra filas que no pertenecen a los sets; rellena YearSplit; reconcilia bounds lower/upper.
    5) Escribe CSVs de sets y de cada parámetro.
    """

    os.makedirs(csv_dir, exist_ok=True)
    lookups = _load_catalog_lookups(db)

    # Acumuladores — NO se construyen sets aquí; se hace después
    # replicando la lógica de SAND_SETS_to_CSV del notebook.
    param_rows: dict[str, list[dict]] = defaultdict(list)
    total_rows = 0

    result_proxy = db.execute(_resolved_query(), {"scenario_id": scenario_id})

    # Recorrer filas de la BD: row[0]=param_name, row[13]=value, resto=dimensiones según _DIM_COL.
    for row in result_proxy.yield_per(50_000):
        pname = row[0]
        spec = PARAM_INDEX.get(pname)
        if spec is None:
            continue

        value = float(row[13])
        record: dict = {}
        skip_row = False

        for dim in spec:
            col_idx = _DIM_COL[dim]
            raw = row[col_idx + 1]
            if dim == "YEAR":
                if raw is None:
                    skip_row = True
                    break
                resolved = int(raw)
            elif dim == "MODE_OF_OPERATION":
                resolved = normalize_mode_of_operation_scalar(raw)
                if resolved == "":
                    skip_row = True
                    break
            else:
                resolved = str(raw) if raw is not None else ""
            record[dim] = resolved

        if skip_row:
            continue

        record["VALUE"] = value
        param_rows[pname].append(record)
        total_rows += 1

    # ------------------------------------------------------------------
    # Construcción de SETS — replica SAND_SETS_to_CSV del notebook.
    # Los sets principales se derivan de parámetros específicos (no de
    # todos), tal como hace el notebook para mantener paridad exacta.
    # ------------------------------------------------------------------
    sets: dict[str, dict] = {
        "TIMESLICE": {},
        "YEAR": {},
        "EMISSION": {},
        "REGION": {},
        "TECHNOLOGY": {},
        "FUEL": {},
        "MODE_OF_OPERATION": {},
    }

    # Paso 1 (notebook): YearSplit → TIMESLICE, YEAR
    for rec in param_rows.get("YearSplit", []):
        ts = rec.get("TIMESLICE")
        yr = rec.get("YEAR")
        if ts:
            sets["TIMESLICE"][ts] = None
        if yr is not None:
            sets["YEAR"][yr] = None

    # Paso 2 (notebook): EmissionActivityRatio (valor ≠ 0) → EMISSION
    for rec in param_rows.get("EmissionActivityRatio", []):
        if float(rec.get("VALUE", 0)) != 0.0:
            em = rec.get("EMISSION")
            if em:
                sets["EMISSION"][em] = None

    # Paso 3 (notebook): OutputActivityRatio (valor ≠ 0) →
    # REGION, TECHNOLOGY, FUEL, MODE_OF_OPERATION
    oar_region: dict[str, None] = {}
    oar_technology: dict[str, None] = {}
    oar_fuel: dict[str, None] = {}
    oar_mode: dict[str, None] = {}
    for rec in param_rows.get("OutputActivityRatio", []):
        if float(rec.get("VALUE", 0)) != 0.0:
            rg = rec.get("REGION")
            tc = rec.get("TECHNOLOGY")
            fl = rec.get("FUEL")
            mo = rec.get("MODE_OF_OPERATION")
            if rg:
                oar_region[rg] = None
            if tc:
                oar_technology[tc] = None
            if fl:
                oar_fuel[fl] = None
            if mo:
                oar_mode[mo] = None
    sets["REGION"] = oar_region
    sets["TECHNOLOGY"] = oar_technology
    sets["FUEL"] = oar_fuel
    sets["MODE_OF_OPERATION"] = oar_mode

    # Paso 4 (notebook): CapacityToActivityUnit (valor ≠ 0) →
    # REGION, TECHNOLOGY  (sobreescribe paso 3, replica notebook)
    catu_region: dict[str, None] = {}
    catu_technology: dict[str, None] = {}
    for rec in param_rows.get("CapacityToActivityUnit", []):
        if float(rec.get("VALUE", 0)) != 0.0:
            rg = rec.get("REGION")
            tc = rec.get("TECHNOLOGY")
            if rg:
                catu_region[rg] = None
            if tc:
                catu_technology[tc] = None
    sets["REGION"] = catu_region
    sets["TECHNOLOGY"] = catu_technology

    # Sets auxiliares (STORAGE, SEASON, DAYTYPE, DAILYTIMEBRACKET, UDC)
    _AUX_DIMS = {"STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET", "UDC"}
    for pname_aux, rows_aux in param_rows.items():
        spec_aux = PARAM_INDEX.get(pname_aux, [])
        aux_in_spec = [d for d in spec_aux if d in _AUX_DIMS]
        if not aux_in_spec:
            continue
        for rec in rows_aux:
            for dim in aux_in_spec:
                val = rec.get(dim)
                if val:
                    if dim not in sets:
                        sets[dim] = {}
                    sets[dim][val] = None

    # ------------------------------------------------------------------
    # Agregación de timeslices a 1 solo (replica notebook con div=1)
    # ------------------------------------------------------------------
    ts_set = sets.get("TIMESLICE", {})
    if len(ts_set) > 1:
        canonical_ts = sorted(ts_set.keys())[0]
        logger.info(
            "Agregando %d timeslices a 1 ('%s')", len(ts_set), canonical_ts,
        )
        _PARAMS_TS_AVG = {"CapacityFactor"}
        _PARAMS_TS_SKIP = {"Conversionls", "Conversionld", "Conversionlh"}

        for pname in list(param_rows.keys()):
            spec = PARAM_INDEX.get(pname, [])
            if "TIMESLICE" not in spec:
                continue

            if pname in _PARAMS_TS_SKIP:
                del param_rows[pname]
                continue

            non_ts_dims = [d for d in spec if d != "TIMESLICE"]
            rows = param_rows[pname]

            groups: dict[tuple, list[dict]] = defaultdict(list)
            for rec in rows:
                key = tuple(rec.get(d, "") for d in non_ts_dims)
                groups[key].append(rec)

            aggregated: list[dict] = []
            use_mean = pname in _PARAMS_TS_AVG
            for key, recs in groups.items():
                vals = [r["VALUE"] for r in recs]
                agg_val = sum(vals) / len(vals) if use_mean else sum(vals)
                new_rec = dict(zip(non_ts_dims, key))
                new_rec["TIMESLICE"] = canonical_ts
                new_rec["VALUE"] = agg_val
                aggregated.append(new_rec)

            param_rows[pname] = aggregated

        sets["TIMESLICE"] = {canonical_ts: None}

    if not sets.get("TIMESLICE"):
        sets["TIMESLICE"]["1"] = None
    if not sets.get("MODE_OF_OPERATION"):
        sets["MODE_OF_OPERATION"]["1"] = None

    # ------------------------------------------------------------------
    # NOTA (refactor 2026-05): la exclusión de "dead years" (YearSplit==0)
    # ya NO se hace aquí. Se aplica de forma uniforme en los 3 modos
    # (Excel/CSV/BD) vía `data_validation.apply_dead_year_exclusion` después
    # de generar los CSVs. La nueva regla además es más estricta: requiere
    # que TODOS los timeslices de un año tengan YearSplit=0, no sólo alguno.
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Filtrar param_rows para incluir solo set members existentes.
    # Replica el comportamiento implícito del notebook donde los CSVs de
    # parámetros solo contienen datos para set members válidos.
    # ------------------------------------------------------------------
    def _record_in_sets(rec: dict, spec: list[str]) -> bool:
        for dim in spec:
            val = rec.get(dim)
            dim_set = sets.get(dim)
            if dim_set is None:
                continue
            if val not in dim_set:
                return False
        return True

    for pname in list(param_rows.keys()):
        spec = PARAM_INDEX.get(pname, [])
        before = len(param_rows[pname])
        param_rows[pname] = [r for r in param_rows[pname] if _record_in_sets(r, spec)]
        dropped = before - len(param_rows[pname])
        if dropped:
            logger.info("%s: %d filas excluidas por sets derivados", pname, dropped)

    # Completar YearSplit para todas las combinaciones TIMESLICE x YEAR
    # evitando fallos de Pyomo por índices faltantes.
    ys_rows = param_rows.get("YearSplit", [])
    ys_lookup = {(r.get("TIMESLICE"), r.get("YEAR")): r for r in ys_rows}
    for ts in sorted(sets.get("TIMESLICE", {}).keys()):
        for yy in sorted(sets.get("YEAR", {}).keys()):
            key = (ts, yy)
            if key not in ys_lookup:
                ys_rows.append({"TIMESLICE": ts, "YEAR": yy, "VALUE": 1.0})

    # ------------------------------------------------------------------
    # NOTA (refactor 2026-05): la reconciliación silenciosa de pares
    # lower/upper se ELIMINÓ. Antes se promediaban automáticamente todos
    # los casos `Min > Max` lo que destruía datos cuando la diferencia era
    # real (no precisión float).
    #
    # Ahora los conflictos se DETECTAN (vía
    # `data_validation.detect_bound_conflicts`) y se reportan como
    # warnings en `ProcessingResult.data_quality_warnings`. La corrección
    # automática sólo está disponible para los conflictos clasificados
    # como `numeric_precision` (gap < 1e-4) y debe pedirse explícitamente
    # vía `apply_bound_fix_numeric_precision`.
    # ------------------------------------------------------------------

    has_storage = bool(
        sets.get("STORAGE")
        and sets.get("SEASON")
        and sets.get("DAYTYPE")
        and sets.get("DAILYTIMEBRACKET")
    )
    has_udc = bool(sets.get("UDC"))

    # Escribir CSVs de sets (preservar orden de inserción = orden del SAND)
    for set_name in ["YEAR", "REGION", "TECHNOLOGY", "FUEL", "EMISSION",
                     "TIMESLICE", "MODE_OF_OPERATION"]:
        vals = list(sets.get(set_name, {}).keys())
        pd.DataFrame({"VALUE": vals}).to_csv(
            os.path.join(csv_dir, f"{set_name}.csv"), index=False,
        )

    if has_storage:
        for set_name in ["STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET"]:
            vals = list(sets.get(set_name, {}).keys())
            pd.DataFrame({"VALUE": vals}).to_csv(
                os.path.join(csv_dir, f"{set_name}.csv"), index=False,
            )

    if has_udc:
        vals = list(sets.get("UDC", {}).keys())
        pd.DataFrame({"VALUE": vals}).to_csv(
            os.path.join(csv_dir, "UDC.csv"), index=False,
        )

    # Escribir CSVs de parámetros
    for pname, rows in param_rows.items():
        spec = PARAM_INDEX[pname]
        df = pd.DataFrame(rows)
        cols = spec + ["VALUE"]
        for c in cols:
            if c not in df.columns:
                df[c] = 0
        df = df[cols]
        key_cols = [c for c in spec]
        if key_cols and not df.empty:
            df = df.drop_duplicates(subset=key_cols, keep="first")
        df.to_csv(os.path.join(csv_dir, f"{pname}.csv"), index=False)

    sets_dict = {k: list(v.keys()) for k, v in sets.items()}

    return ProcessingResult(
        has_storage=has_storage,
        has_udc=has_udc,
        sets=sets_dict,
        param_count=total_rows,
        region_id_by_name=lookups["REGION"]["name_to_id"],
        technology_id_by_name=lookups["TECHNOLOGY"]["name_to_id"],
        fuel_id_by_name=lookups["FUEL"]["name_to_id"],
        emission_id_by_name=lookups["EMISSION"]["name_to_id"],
        timeslice_id_by_name=lookups["TIMESLICE"]["name_to_id"],
        mode_of_operation_id_by_name=lookups["MODE_OF_OPERATION"]["name_to_id"],
        season_id_by_name=lookups["SEASON"]["name_to_id"],
        daytype_id_by_name=lookups["DAYTYPE"]["name_to_id"],
        dailytimebracket_id_by_name=lookups["DAILYTIMEBRACKET"]["name_to_id"],
        storage_id_by_name=lookups["STORAGE"]["name_to_id"],
        region_name_by_id=lookups["REGION"]["id_to_name"],
        technology_name_by_id=lookups["TECHNOLOGY"]["id_to_name"],
        fuel_name_by_id=lookups["FUEL"]["id_to_name"],
        emission_name_by_id=lookups["EMISSION"]["id_to_name"],
        storage_name_by_id=lookups["STORAGE"]["id_to_name"],
    )


# ========================================================================
#  Paso 2: Completar matrices (celdas 10-13 del notebook OPT_YA_20260220)
#  Nota: el nuevo notebook NO hace fillna(0). Las filas sin datos se
#  eliminan (dropna) para que DataPortal use el default del modelo.
# ========================================================================

def completar_Matrix_Act_Ratio(path_csv: str, variable: str) -> None:
    """Completa la matriz de InputActivityRatio o OutputActivityRatio.
    Genera todas las combinaciones REGION×TECHNOLOGY×FUEL×MODE_OF_OPERATION×YEAR,
    hace merge left con los datos existentes y elimina filas sin VALUE (dropna).
    Así DataPortal no rellena con 0 sino que usa el default del modelo para índices faltantes.
    """
    df = pd.read_csv(path_csv + variable)
    df["MODE_OF_OPERATION"] = normalize_mode_of_operation_series(df["MODE_OF_OPERATION"])

    regions = df["REGION"].unique()
    technologies = pd.read_csv(path_csv + "TECHNOLOGY.csv", dtype=str)["VALUE"].unique()
    fuels = pd.read_csv(path_csv + "FUEL.csv", dtype=str)["VALUE"].unique()
    moo_df = pd.read_csv(path_csv + "MODE_OF_OPERATION.csv")
    modes = normalize_mode_of_operation_series(moo_df["VALUE"])
    modes = modes[modes != ""].drop_duplicates().tolist()
    years = pd.read_csv(path_csv + "YEAR.csv")["VALUE"].unique()

    all_combinations = pd.DataFrame(itertools.product(
        regions, technologies, fuels, modes, years),
        columns=["REGION", "TECHNOLOGY", "FUEL", "MODE_OF_OPERATION", "YEAR"]
    )

    result = all_combinations.merge(df, on=["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "FUEL", "YEAR"], how="left")

    result.dropna(subset=["VALUE"], inplace=True)
    result.to_csv(path_csv + variable, index=False)


def completar_Matrix_Emission(path_csv: str, variable: str) -> None:
    """Completa la matriz de EmissionActivityRatio (REGION×TECHNOLOGY×EMISSION×MODE×YEAR)."""
    df = pd.read_csv(path_csv + variable)
    df["MODE_OF_OPERATION"] = normalize_mode_of_operation_series(df["MODE_OF_OPERATION"])

    regions = df["REGION"].unique()
    technologies = pd.read_csv(path_csv + "TECHNOLOGY.csv")["VALUE"].unique()
    emission = pd.read_csv(path_csv + "EMISSION.csv")["VALUE"].unique()
    moo_df = pd.read_csv(path_csv + "MODE_OF_OPERATION.csv")
    modes = normalize_mode_of_operation_series(moo_df["VALUE"])
    modes = modes[modes != ""].drop_duplicates().tolist()
    years = pd.read_csv(path_csv + "YEAR.csv")["VALUE"].unique()

    all_combinations = pd.DataFrame(itertools.product(
        regions, technologies, emission, modes, years),
        columns=["REGION", "TECHNOLOGY", "EMISSION", "MODE_OF_OPERATION", "YEAR"]
    )

    result = all_combinations.merge(df, on=["REGION", "TECHNOLOGY", "EMISSION", "MODE_OF_OPERATION", "YEAR"], how="left")

    result.dropna(subset=["VALUE"], inplace=True)
    result.to_csv(path_csv + variable, index=False)


def completar_Matrix_Storage(path_csv: str, variable: str) -> None:
    """Completa TechnologyToStorage o TechnologyFromStorage (REGION×TECHNOLOGY×STORAGE×MODE)."""
    df = pd.read_csv(path_csv + variable)
    df["MODE_OF_OPERATION"] = normalize_mode_of_operation_series(df["MODE_OF_OPERATION"])

    regions = df["REGION"].unique()
    technologies = pd.read_csv(path_csv + "TECHNOLOGY.csv")["VALUE"].unique()
    storage = pd.read_csv(path_csv + "STORAGE.csv")["VALUE"].unique()
    moo_df = pd.read_csv(path_csv + "MODE_OF_OPERATION.csv")
    modes = normalize_mode_of_operation_series(moo_df["VALUE"])
    modes = modes[modes != ""].drop_duplicates().tolist()

    all_combinations = pd.DataFrame(itertools.product(
        regions, technologies, storage, modes),
        columns=["REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION"]
    )

    result = all_combinations.merge(df, on=["REGION", "TECHNOLOGY", "STORAGE", "MODE_OF_OPERATION"], how="left")

    result.dropna(subset=["VALUE"], inplace=True)
    result.to_csv(path_csv + variable, index=False)


def completar_Matrix_Cost(path_csv: str, variable: str) -> None:

    df = pd.read_csv(path_csv + variable)
    df["MODE_OF_OPERATION"] = normalize_mode_of_operation_series(df["MODE_OF_OPERATION"])

    regions = df["REGION"].unique()
    technologies = pd.read_csv(path_csv + "TECHNOLOGY.csv")["VALUE"].unique()
    moo_df = pd.read_csv(path_csv + "MODE_OF_OPERATION.csv")
    modes = normalize_mode_of_operation_series(moo_df["VALUE"])
    modes = modes[modes != ""].drop_duplicates().tolist()
    years = pd.read_csv(path_csv + "YEAR.csv")["VALUE"].unique()

    all_combinations = pd.DataFrame(itertools.product(
        regions, technologies, modes, years),
        columns=["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"]
    )

    result = all_combinations.merge(df, on=["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"], how="left")

    result.dropna(subset=["VALUE"], inplace=True)
    result.to_csv(path_csv + variable, index=False)


# ========================================================================
#  Paso 3: Contabilizar emisiones a la entrada (celda 13 del notebook)
# ========================================================================

def process_and_save_emission_ratios(emission_activity_path, input_activity_path, output_path, path_csv):
    """
    Procesa emisiones a la entrada (celda 13 del notebook): combina EmissionActivityRatio
    con InputActivityRatio (VALUE = VALUE_emission * VALUE_input por cada fuel),
    agrupa por REGION/TECHNOLOGY/EMISSION/MODE/YEAR y actualiza EmissionActivityRatio.csv.
    Processes emission activity ratios by merging with input activity ratios,
    calculates updated values, and saves the result to a CSV.

    Parameters:
    - emission_activity_path: Path to EmissionActivityRatio.csv
    - input_activity_path: Path to InputActivityRatio.csv
    - output_path: Output path for the updated CSV
    """
    df_emission = pd.read_csv(path_csv + emission_activity_path)
    df_input = pd.read_csv(path_csv + input_activity_path)
    df_emission["MODE_OF_OPERATION"] = normalize_mode_of_operation_series(
        df_emission["MODE_OF_OPERATION"]
    )
    df_input["MODE_OF_OPERATION"] = normalize_mode_of_operation_series(
        df_input["MODE_OF_OPERATION"]
    )

    merged = pd.merge(
        df_emission,
        df_input,
        on=['REGION', 'TECHNOLOGY', 'MODE_OF_OPERATION', 'YEAR'],
        how='left'
    ).query("VALUE_x != 0 and VALUE_y != 0").assign(
        VALUE=lambda x: x['VALUE_x'] * x['VALUE_y']
    ).drop(columns=['VALUE_x', 'VALUE_y', 'FUEL'])

    merged_unique = merged.groupby(
        ['REGION', 'TECHNOLOGY', 'EMISSION', 'MODE_OF_OPERATION', 'YEAR'],
        as_index=False
    ).agg({'VALUE': 'first'})

    final_merged = pd.merge(
        df_emission,
        merged_unique,
        on=['REGION', 'TECHNOLOGY', 'EMISSION', 'MODE_OF_OPERATION', 'YEAR'],
        how='left',
        suffixes=('_df1', '_df4')
    ).assign(
        VALUE=lambda x: x.apply(
            lambda row: row['VALUE_df4'] if pd.notnull(row['VALUE_df4']) and row['VALUE_df1'] != row['VALUE_df4'] else row['VALUE_df1'],
            axis=1
        )
    ).loc[:, ['REGION', 'TECHNOLOGY', 'EMISSION', 'MODE_OF_OPERATION', 'YEAR', 'VALUE']]

    final_merged.to_csv(path_csv + output_path, index=False)


# ========================================================================
#  Paso 4: Eliminar valores fuera de índices (celda 8 del notebook)
# ========================================================================

def eliminar_valores_fuera_de_indices(csv_dir: str) -> None:
    """Filtra filas de cada parámetro CSV cuyos índices no estén en los sets (celda 8 del notebook).
    Para cada columna de dimensión que tenga un CSV de set, deja solo filas con valor en ese set.
    """
    param_files = [
        f for f in os.listdir(csv_dir)
        if f.endswith(".csv") and f.replace(".csv", "") in PARAM_INDEX
    ]

    for pfile in param_files:
        pname = pfile.replace(".csv", "")
        path = os.path.join(csv_dir, pfile)
        df = pd.read_csv(path)
        if df.empty:
            continue

        cols = [c for c in df.columns if c != "VALUE"]
        modified = False
        for col in cols:
            set_path = os.path.join(csv_dir, f"{col}.csv")
            if os.path.exists(set_path):
                set_df = pd.read_csv(set_path)
                if "VALUE" in set_df.columns:
                    valid_values = set_df["VALUE"].tolist()
                    before = len(df)
                    df = df[df[col].isin(valid_values)]
                    if len(df) < before:
                        modified = True

        if modified:
            df.to_csv(path, index=False)


# ========================================================================
#  Paso 5: UDC (celdas 17-19 del notebook)
# ========================================================================

def crear_csv_UDC(udc_list: list[str], csv_dir: str) -> None:
    """Crea CSV/UDC.csv a partir de una lista de UDC."""
    path = os.path.join(csv_dir, "UDC.csv")
    pd.DataFrame({"VALUE": udc_list}).to_csv(path, index=False)


def crear_UDCMultiplier(
    csv_dir: str,
    multiplier_type: str,
    valor_default: float = 0,
) -> None:
    """Crea UDCMultiplier{TotalCapacity|NewCapacity|Activity}.csv."""
    af_path = os.path.join(csv_dir, "AvailabilityFactor.csv")
    udc_path = os.path.join(csv_dir, "UDC.csv")
    out_file = f"UDCMultiplier{multiplier_type}.csv"
    out_path = os.path.join(csv_dir, out_file)

    if not os.path.exists(af_path) or not os.path.exists(udc_path):
        return

    df_af = pd.read_csv(af_path)
    df_udc = pd.read_csv(udc_path)

    if df_af.empty or df_udc.empty:
        return

    df_af["REGION"] = df_af["REGION"].astype(str)
    df_af["TECHNOLOGY"] = df_af["TECHNOLOGY"].astype(str)
    df_af["YEAR"] = df_af["YEAR"].astype(int)

    df_udc["UDC"] = df_udc["VALUE"].astype(str)
    df_udc = df_udc[["UDC"]]

    df_af["_tmp"] = 1
    df_udc["_tmp"] = 1
    df = df_af.merge(df_udc, on="_tmp", how="left").drop(columns="_tmp")
    df["VALUE"] = valor_default

    df = df[["REGION", "TECHNOLOGY", "UDC", "YEAR", "VALUE"]].sort_values(
        ["REGION", "TECHNOLOGY", "UDC", "YEAR"],
    )
    df.to_csv(out_path, index=False)


def crear_UDC_parametros(
    csv_dir: str,
    valor_constant_default: float = 0.0,
    valor_tag_default: float = 2.0,
) -> None:
    """Crea UDCConstant.csv y UDCTag.csv."""
    region_path = os.path.join(csv_dir, "REGION.csv")
    udc_path = os.path.join(csv_dir, "UDC.csv")
    year_path = os.path.join(csv_dir, "YEAR.csv")

    if not all(os.path.exists(p) for p in [region_path, udc_path, year_path]):
        return

    df_region = pd.read_csv(region_path)
    df_udc = pd.read_csv(udc_path)
    df_year = pd.read_csv(year_path)

    if df_region.empty or df_udc.empty or df_year.empty:
        return

    df_region["REGION"] = df_region["VALUE"].astype(str)
    df_udc["UDC"] = df_udc["VALUE"].astype(str)
    df_year["YEAR"] = df_year["VALUE"].astype(int)

    df_region = df_region[["REGION"]]
    df_udc = df_udc[["UDC"]]
    df_year = df_year[["YEAR"]]

    df_region["_tmp"] = 1
    df_udc["_tmp"] = 1
    df_year["_tmp"] = 1

    # UDCConstant: (REGION, UDC, YEAR)
    df_constant = (
        df_region.merge(df_udc, on="_tmp").merge(df_year, on="_tmp").drop(columns="_tmp")
    )
    df_constant["VALUE"] = valor_constant_default
    df_constant = df_constant[["REGION", "UDC", "YEAR", "VALUE"]].sort_values(
        ["REGION", "UDC", "YEAR"],
    )
    df_constant.to_csv(os.path.join(csv_dir, "UDCConstant.csv"), index=False)

    # UDCTag: (REGION, UDC)
    df_region["_tmp"] = 1
    df_udc["_tmp"] = 1
    df_tag = df_region.merge(df_udc, on="_tmp").drop(columns="_tmp")
    df_tag["VALUE"] = valor_tag_default
    df_tag = df_tag[["REGION", "UDC", "VALUE"]].sort_values(["REGION", "UDC"])
    df_tag.to_csv(os.path.join(csv_dir, "UDCTag.csv"), index=False)


def actualizar_UDCMultiplier(
    multiplier_type,
    carpeta="CSV",
    tech_multiplier_dict=None,
):
    if tech_multiplier_dict is None:
        raise ValueError("Debe proporcionar tech_multiplier_dict")

    archivo = f"UDCMultiplier{multiplier_type}.csv"
    path = os.path.join(carpeta, archivo)

    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe el archivo: {path}")

    df = pd.read_csv(path)

    df["REGION"] = df["REGION"].astype(str)
    df["TECHNOLOGY"] = df["TECHNOLOGY"].astype(str)
    df["UDC"] = df["UDC"].astype(str)
    df["VALUE"] = df["VALUE"].astype(float)

    if "YEAR" in df.columns:
        df["YEAR"] = df["YEAR"].astype(int)

    mask = df["TECHNOLOGY"].isin(tech_multiplier_dict.keys())

    df.loc[mask, "VALUE"] = (
        df.loc[mask, "TECHNOLOGY"]
        .map(tech_multiplier_dict)
        .astype(float)
    )

    sort_cols = ["REGION", "TECHNOLOGY", "UDC"]
    if "YEAR" in df.columns:
        sort_cols.append("YEAR")

    df = df.sort_values(sort_cols)

    df.to_csv(path, index=False)


def actualizar_UDCTag(
    valor,
    carpeta="CSV",
    archivo="UDCTag.csv",
):
    if valor not in [0, 1]:
        raise ValueError("UDCTag solo puede tomar los valores 0 (≤) o 1 (=).")

    path = os.path.join(carpeta, archivo)

    df = pd.read_csv(path)

    df["REGION"] = df["REGION"].astype(str)
    df["UDC"] = df["UDC"].astype(str)

    df["VALUE"] = float(valor)

    df = df.sort_values(["REGION", "UDC"])

    df.to_csv(path, index=False)


# Diccionario del notebook (celda 20) para ReserveMargin
_UDC_RESERVE_MARGIN_DICT: dict[str, float] = {
    "PWRAFR": -1.0,
    "PWRBGS": -1.0,
    "PWRCOA": -1.0,
    "PWRCOACCS": -1.0,
    "PWRCSP": 0.0,
    "PWRDSL": -1.0,
    "PWRFOL": -1.0,
    "PWRGEO": -1.0,
    "PWRHYDDAM": -1.0,
    "PWRHYDROR": 0.0,
    "PWRHYDROR_NDC": 0.0,
    "PWRJET": -1.0,
    "PWRLPG": -1.0,
    "PWRNGS_CC": -1.0,
    "PWRNGS_CS": -1.0,
    "PWRNGSCCS": -1.0,
    "PWRNUC": -1.0,
    "PWRSOLRTP": 0.0,
    "PWRSOLRTP_ZNI": 0.0,
    "PWRSOLUGE": 0.0,
    "PWRSOLUGE_BAT": -1.0,
    "PWRSOLUPE": 0.0,
    "PWRSTD": 0.0,
    "PWRWAS": -1.0,
    "PWRWNDOFS_FIX": -1.0,
    "PWRWNDOFS_FLO": -1.0,
    "PWRWNDONS": -1.0,
    "GRDTYDELC": (1.0 / 0.9) * 1.2,
}


def ensure_udc_csvs(csv_dir: str) -> None:
    """Genera CSVs UDC replicando celdas 17-19 del notebook.

    El notebook hardcodea udc_list = ["UDC_Margin"]; aquí hacemos lo mismo
    para garantizar paridad CSV, independientemente de los UDC en la BD.
    """
    udc_list = ["UDC_Margin"]
    crear_csv_UDC(udc_list, csv_dir)

    for mtype in ["TotalCapacity", "NewCapacity", "Activity"]:
        crear_UDCMultiplier(csv_dir, mtype, valor_default=0)

    crear_UDC_parametros(csv_dir, valor_constant_default=0.0, valor_tag_default=2.0)


def apply_udc_config(db: Session, scenario_id: int, csv_dir: str) -> None:
    """Lee la configuración UDC del escenario y aplica actualizar_UDCMultiplier / actualizar_UDCTag.

    Replica la celda 20 del notebook pero con configuración dinámica desde la BD.
    Si el escenario no tiene udc_config, aplica el default de ReserveMargin.
    """
    from app.models import Scenario

    scenario = db.execute(
        select(Scenario).where(Scenario.id == scenario_id)
    ).scalar_one_or_none()

    udc_config = None
    if scenario is not None:
        udc_config = getattr(scenario, "udc_config", None)

    if udc_config is None:
        logger.warning("apply_udc_config llamado sin udc_config en escenario %s", scenario_id)
        return

    for mult_cfg in udc_config.get("multipliers", []):
        mtype = mult_cfg.get("type")
        tech_dict = mult_cfg.get("tech_dict")
        if mtype and tech_dict:
            try:
                actualizar_UDCMultiplier(
                    multiplier_type=mtype,
                    carpeta=csv_dir,
                    tech_multiplier_dict=tech_dict,
                )
            except FileNotFoundError:
                logger.warning("UDCMultiplier%s.csv no encontrado, omitiendo", mtype)

    tag_value = udc_config.get("tag_value")
    if tag_value is not None:
        try:
            actualizar_UDCTag(tag_value, carpeta=csv_dir)
        except (FileNotFoundError, ValueError) as e:
            logger.warning("No se pudo actualizar UDCTag: %s", e)


def reorder_activity_ratio_csvs_for_dataportal(csv_dir: str) -> None:
    """Reordena columnas de Input/OutputActivityRatio al orden que espera DataPortal.

    Coincide con el paso 7 de ``run_data_processing``. Algunos CSV (p. ej. export
    notebook) traen MODE_OF_OPERATION antes que FUEL; Pyomo indexa el parámetro
    como REGION, TECHNOLOGY, FUEL, MODE_OF_OPERATION, YEAR.
    """
    for ratio_file in ("InputActivityRatio.csv", "OutputActivityRatio.csv"):
        ratio_path = os.path.join(csv_dir, ratio_file)
        if os.path.exists(ratio_path):
            df = pd.read_csv(ratio_path)
            expected_cols = ["REGION", "TECHNOLOGY", "FUEL", "MODE_OF_OPERATION", "YEAR", "VALUE"]
            if all(c in df.columns for c in expected_cols):
                df["MODE_OF_OPERATION"] = normalize_mode_of_operation_series(
                    df["MODE_OF_OPERATION"]
                )
                df[expected_cols].to_csv(ratio_path, index=False)


def strip_whitespace_in_set_csvs(csv_dir: str) -> None:
    """Normaliza la columna VALUE de los CSV de sets (espacios y saltos de línea).

    Exportaciones mal formadas pueden dejar nombres de tecnología con ``\\n`` en
    TECHNOLOGY.csv; eso rompe la coincidencia con columnas de parámetros.
    """
    set_files = [
        "REGION", "TECHNOLOGY", "FUEL", "EMISSION", "YEAR",
        "TIMESLICE", "MODE_OF_OPERATION",
        "STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET", "UDC",
    ]
    for name in set_files:
        fpath = os.path.join(csv_dir, f"{name}.csv")
        if not os.path.exists(fpath):
            continue
        df = pd.read_csv(fpath)
        if df.empty or "VALUE" not in df.columns:
            continue
        if name == "YEAR":

            def _year_cell(v):
                if pd.isna(v):
                    return v
                s = str(v).strip()
                return int(float(s)) if s else v

            df["VALUE"] = df["VALUE"].map(_year_cell)
        elif name == "MODE_OF_OPERATION":
            df["VALUE"] = normalize_mode_of_operation_series(df["VALUE"])
        else:
            df["VALUE"] = df["VALUE"].map(
                lambda x: str(x).strip() if pd.notna(x) else x,
            )
        df.to_csv(fpath, index=False)


# ========================================================================
#  Pipeline desde Excel (sin BD)
# ========================================================================

def _build_processing_result_from_csv_dir(csv_dir: str) -> ProcessingResult:
    """Construye ProcessingResult leyendo los CSVs de sets (para flujo Excel sin BD).

    Los IDs se asignan por orden 1-based (posición en el CSV) para compatibilidad
    con process_results.
    """
    path = os.path.join
    sets: dict[str, list] = {}
    set_files = [
        "REGION", "TECHNOLOGY", "FUEL", "EMISSION", "YEAR",
        "TIMESLICE", "MODE_OF_OPERATION",
        "STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET", "UDC",
    ]
    def _parse_set_value(set_name: str, raw_value):
        """Normaliza tipos de set al leer CSVs (YEAR como int; resto como str)."""
        if pd.isna(raw_value):
            return None
        if set_name == "YEAR":
            text = str(raw_value).strip()
            if not text:
                return None
            return int(float(text))
        if set_name == "MODE_OF_OPERATION":
            m = normalize_mode_of_operation_scalar(raw_value)
            return m if m != "" else None
        return str(raw_value).strip()

    for name in set_files:
        fpath = path(csv_dir, f"{name}.csv")
        if os.path.exists(fpath):
            df = pd.read_csv(fpath)
            if not df.empty and "VALUE" in df.columns:
                values = []
                for raw_value in df["VALUE"].tolist():
                    parsed = _parse_set_value(name, raw_value)
                    if parsed in (None, ""):
                        continue
                    values.append(parsed)
                sets[name] = values

    has_storage = all(
        os.path.exists(path(csv_dir, f"{s}.csv"))
        for s in ["STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET"]
    )
    udc_path = path(csv_dir, "UDC.csv")
    has_udc = os.path.exists(udc_path) and os.path.getsize(udc_path) > 0

    def _lookups_from_list(items: list) -> tuple[dict[str, int], dict[int, str]]:
        id_by_name = {str(v): i + 1 for i, v in enumerate(items)}
        name_by_id = {i + 1: str(v) for i, v in enumerate(items)}
        return id_by_name, name_by_id

    region_id_by_name, region_name_by_id = _lookups_from_list(sets.get("REGION", []))
    technology_id_by_name, technology_name_by_id = _lookups_from_list(sets.get("TECHNOLOGY", []))
    fuel_id_by_name, fuel_name_by_id = _lookups_from_list(sets.get("FUEL", []))
    emission_id_by_name, emission_name_by_id = _lookups_from_list(sets.get("EMISSION", []))
    timeslice_id_by_name, _ = _lookups_from_list(sets.get("TIMESLICE", []))
    mode_of_operation_id_by_name, _ = _lookups_from_list(sets.get("MODE_OF_OPERATION", []))
    season_id_by_name, _ = _lookups_from_list(sets.get("SEASON", []))
    daytype_id_by_name, _ = _lookups_from_list(sets.get("DAYTYPE", []))
    dailytimebracket_id_by_name, _ = _lookups_from_list(sets.get("DAILYTIMEBRACKET", []))
    storage_id_by_name, _ = _lookups_from_list(sets.get("STORAGE", []))
    storage_name_by_id = dict(enumerate(sets.get("STORAGE", []), start=1)) if sets.get("STORAGE") else {}

    param_count = sum(
        1 for f in os.listdir(csv_dir)
        if f.endswith(".csv") and f.replace(".csv", "") in PARAM_INDEX
    )

    return ProcessingResult(
        has_storage=has_storage,
        has_udc=bool(has_udc),
        sets=sets,
        param_count=param_count,
        region_id_by_name=region_id_by_name,
        technology_id_by_name=technology_id_by_name,
        fuel_id_by_name=fuel_id_by_name,
        emission_id_by_name=emission_id_by_name,
        timeslice_id_by_name=timeslice_id_by_name,
        mode_of_operation_id_by_name=mode_of_operation_id_by_name,
        season_id_by_name=season_id_by_name,
        daytype_id_by_name=daytype_id_by_name,
        dailytimebracket_id_by_name=dailytimebracket_id_by_name,
        storage_id_by_name=storage_id_by_name,
        region_name_by_id=region_name_by_id,
        technology_name_by_id=technology_name_by_id,
        fuel_name_by_id=fuel_name_by_id,
        emission_name_by_id=emission_name_by_id,
        storage_name_by_id=storage_name_by_id,
    )


def run_data_processing_from_excel(
    excel_path: str | Path,
    csv_dir: str,
    *,
    sheet_name: str = "Parameters",
    div: int = 1,
) -> ProcessingResult:
    """Pipeline completo: Excel SAND → CSVs temporales procesados (sin BD).

    Genera CSVs con la misma lógica que el notebook (vía compare_notebook_vs_app),
    luego aplica filtrado por sets, completado de matrices, emisiones y UDC por defecto.
    Devuelve ProcessingResult para usar con create_abstract_model, build_instance,
    solve_model y process_results (mismo flujo que run_osemosys_from_db).
    """
    from app.simulation.core.excel_to_csv import generate_csvs_from_excel

    excel_path = Path(excel_path)
    if not excel_path.is_file():
        raise FileNotFoundError(f"No existe el archivo Excel: {excel_path}")

    logger.info("Generando CSVs desde Excel %s hacia %s", excel_path, csv_dir)
    generate_csvs_from_excel(excel_path, csv_dir, sheet_name=sheet_name, div=div)

    normalize_mode_of_operation_in_csv_dir(csv_dir)

    # 2. Eliminar valores fuera de índices (celda 8)
    eliminar_valores_fuera_de_indices(csv_dir)

    # 3. Completar matrices (celdas 9-12)
    path_csv = csv_dir + os.sep
    completar_Matrix_Act_Ratio(path_csv, "InputActivityRatio.csv")
    completar_Matrix_Act_Ratio(path_csv, "OutputActivityRatio.csv")

    if os.path.exists(os.path.join(csv_dir, "EMISSION.csv")):
        completar_Matrix_Emission(path_csv, "EmissionActivityRatio.csv")

    storage_csvs = ["STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET"]
    has_storage = all(os.path.exists(os.path.join(csv_dir, f"{s}.csv")) for s in storage_csvs)
    if has_storage:
        completar_Matrix_Storage(path_csv, "TechnologyFromStorage.csv")
        completar_Matrix_Storage(path_csv, "TechnologyToStorage.csv")

    completar_Matrix_Cost(path_csv, "VariableCost.csv")

    # 4. Emisiones a la entrada (celda 13 del notebook)
    if os.path.exists(os.path.join(csv_dir, "EMISSION.csv")):
        process_and_save_emission_ratios(
            "EmissionActivityRatio.csv",
            "InputActivityRatio.csv",
            "EmissionActivityRatio.csv",
            path_csv,
        )

    # 5. UDC — deshabilitado en modo Excel (generate_notebook_csvs crea UDC con Tag=0;
    #    eliminamos esos archivos para que has_udc=False y no se apliquen restricciones)
    _udc_files = [
        "UDC.csv", "UDCConstant.csv", "UDCTag.csv",
        "UDCMultiplierTotalCapacity.csv", "UDCMultiplierNewCapacity.csv",
        "UDCMultiplierActivity.csv",
    ]
    for _f in _udc_files:
        _fp = os.path.join(csv_dir, _f)
        if os.path.exists(_fp):
            os.remove(_fp)
            logger.debug("UDC eliminado para modo Excel: %s", _f)

    # 7. Reordenar columnas de ActivityRatio para DataPortal
    reorder_activity_ratio_csvs_for_dataportal(csv_dir)

    # 8. Validación de calidad de datos (común a Excel/CSV/BD).
    #    Aplica dead_year exclusion automáticamente y reporta bound_conflicts
    #    como warnings sin corregirlos.
    quality = _apply_data_quality_validation(csv_dir, detected_during="excel")

    # Re-leer ProcessingResult tras la posible exclusión de años.
    result = _build_processing_result_from_csv_dir(csv_dir)
    result.data_quality_warnings = quality
    logger.info("Procesamiento desde Excel completado: %d sets, has_storage=%s, has_udc=%s",
                len(result.sets), result.has_storage, result.has_udc)
    return result


def get_processing_result_from_csv_dir(
    csv_dir: str, *, validate: bool = True
) -> ProcessingResult:
    """Construye ProcessingResult leyendo los CSVs de sets en un directorio existente.

    Útil cuando ya tienes CSVs temporales listos (p. ej. generados por el script
    compare_notebook_vs_app o por run_data_processing_from_excel) y quieres
    ejecutar solo build_instance → solve → process_results.

    Parameters
    ----------
    csv_dir : str
        Ruta al directorio que contiene los CSVs (REGION.csv, TECHNOLOGY.csv, etc.).
    validate : bool
        Si True (default), aplica `_apply_data_quality_validation` al directorio
        — esto **modifica los CSVs** excluyendo años con YearSplit=0 en todos
        sus timeslices y agrega `data_quality_warnings` al resultado. Pasar
        False para inspección no destructiva.

    Returns
    -------
    ProcessingResult
        Sets, has_storage, has_udc, lookups y data_quality_warnings.
    """
    if validate:
        quality = _apply_data_quality_validation(csv_dir, detected_during="csv")
    else:
        quality = {}
    result = _build_processing_result_from_csv_dir(csv_dir)
    result.data_quality_warnings = quality
    return result


def _apply_data_quality_validation(
    csv_dir: str, *, detected_during: str
) -> dict:
    """Paso final común a los 3 pipelines (Excel/CSV/BD).

    1. Detecta `BoundConflict`s y `YearExclusion`s en los CSVs ya generados.
    2. **Aplica** la exclusión de dead_years (modifica YEAR.csv y todos los
       CSVs con columna YEAR).
    3. Logea los warnings.
    4. Devuelve el reporte como dict (ya con dead_years aplicados, los demás
       conflicts permanecen sin tocar; corresponde al usuario corregirlos vía
       `data_validation.apply_bound_fix_numeric_precision`).

    Garantiza comportamiento idéntico entre Excel, CSV-dir y BD.
    """
    from app.simulation.core import data_validation as dv

    report = dv.build_report(csv_dir, detected_during=detected_during)
    if report.year_exclusions:
        n_files = dv.apply_dead_year_exclusion(csv_dir, report.year_exclusions)
        logger.info(
            "Excluyendo %d años (YearSplit=0 en TODOS los timeslices). %d archivos modificados.",
            len(report.year_exclusions), n_files,
        )
    dv.log_report(report, source=detected_during)
    return report.to_dict()


# ========================================================================
#  Pipeline completo
# ========================================================================

def run_data_processing(
    db: Session,
    *,
    scenario_id: int,
    csv_dir: str,
) -> ProcessingResult:
    """Pipeline completo: BD → CSVs temporales procesados.

    Replica el flujo completo del notebook (celdas 4-19).
    Pasos: 1) export_scenario_to_csv  2) eliminar_valores_fuera_de_indices
    3) completar matrices (ActivityRatio, Emission, Storage, Cost)
    4) process_and_save_emission_ratios  5) ensure_udc_csvs  6) apply_udc_config
    7) reordenar columnas de Input/OutputActivityRatio para DataPortal.
    """
    logger.info("Exportando datos del escenario %d a CSVs en %s", scenario_id, csv_dir)

    # 1. BD → CSVs base (sets + parámetros)
    result = export_scenario_to_csv(db, scenario_id=scenario_id, csv_dir=csv_dir)
    logger.info("Exportados %d registros de parámetros", result.param_count)

    if _get_scenario_processing_mode(db, scenario_id=scenario_id) == "PREPROCESSED_CSV":
        logger.info(
            "Escenario %d marcado como PREPROCESSED_CSV; se omite reprocesamiento posterior a la exportación.",
            scenario_id,
        )
        return result

    normalize_mode_of_operation_in_csv_dir(csv_dir)

    # 2. Eliminar valores fuera de índices (celda 8)
    eliminar_valores_fuera_de_indices(csv_dir)

    # 3. Completar matrices (celdas 9-12)
    path_csv = csv_dir + os.sep
    completar_Matrix_Act_Ratio(path_csv, "InputActivityRatio.csv")
    completar_Matrix_Act_Ratio(path_csv, "OutputActivityRatio.csv")

    if os.path.exists(os.path.join(csv_dir, "EMISSION.csv")):
        completar_Matrix_Emission(path_csv, "EmissionActivityRatio.csv")

    if result.has_storage:
        completar_Matrix_Storage(path_csv, "TechnologyFromStorage.csv")
        completar_Matrix_Storage(path_csv, "TechnologyToStorage.csv")

    completar_Matrix_Cost(path_csv, "VariableCost.csv")

    # 4. Emisiones a la entrada (celda 13 del notebook)
    if os.path.exists(os.path.join(csv_dir, "EMISSION.csv")):
        process_and_save_emission_ratios(
            "EmissionActivityRatio.csv",
            "InputActivityRatio.csv",
            "EmissionActivityRatio.csv",
            path_csv,
        )

    # 5-6. UDC — solo si el escenario tiene udc_config con enabled=True
    from app.models import Scenario as _Scenario
    _scenario = db.get(_Scenario, scenario_id)
    _udc_active = False
    _udc_cfg = getattr(_scenario, "udc_config", None)
    if _udc_cfg and _udc_cfg.get("enabled", True):
        ensure_udc_csvs(csv_dir)
        apply_udc_config(db, scenario_id, csv_dir)
        _udc_active = True
    result.has_udc = _udc_active

    # 7. Reordenar columnas de ActivityRatio para compatibilidad con DataPortal
    reorder_activity_ratio_csvs_for_dataportal(csv_dir)

    # 8. Validación de calidad de datos (común a Excel/CSV/BD).
    #    Aplica dead_year exclusion automáticamente y reporta bound_conflicts
    #    como warnings sin corregirlos.
    quality = _apply_data_quality_validation(csv_dir, detected_during="db")

    # Re-leer ProcessingResult tras la posible exclusión de años, y
    # adjuntar warnings.
    result_after = _build_processing_result_from_csv_dir(csv_dir)
    # Preservar lookups y flags de la versión BD; sólo refrescamos sets y warnings.
    result.sets = result_after.sets
    result.data_quality_warnings = quality

    logger.info("Procesamiento de datos completado")
    return result
