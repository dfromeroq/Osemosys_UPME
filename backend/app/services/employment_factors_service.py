"""Derived employment-factor outputs for solved OSeMOSYS simulations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

PJ_PER_YEAR_PER_GW = 31.5576
MW_PER_PJ_PER_YEAR = 1000.0 / PJ_PER_YEAR_PER_GW
OPTIMIZATION_START_YEAR = 2025

CONSTRUCTION_FACTOR_TYPE = "Construction&Manufacturing"
OM_FACTOR_TYPE = "O&M"
DIRECT_JOB_TYPE = "Direct"

EMPLOYMENT_VARIABLE_BY_FACTOR_TYPE = {
    CONSTRUCTION_FACTOR_TYPE: "EmploymentConstructionManufacturingDirect",
    OM_FACTOR_TYPE: "EmploymentOMDirect",
}

DEFAULT_MAPPING_PATH = Path(__file__).with_name("employment_factors_mapping.yaml")


@dataclass(frozen=True)
class EmploymentComponent:
    """One employment-factor technology represented by a model technology."""

    employment_technology: str
    multiplier: float = 1.0
    note: str | None = None


def pj_per_year_to_mw(value: float | int | None) -> float:
    """Convert OSeMOSYS capacity output from PJ/year to MW."""
    if value is None:
        return 0.0
    return float(value) * MW_PER_PJ_PER_YEAR


def load_technology_mapping(path: str | Path | None = None) -> dict[str, list[EmploymentComponent]]:
    """Load and validate the OSeMOSYS-to-employment-factor technology mapping."""
    mapping_path = Path(path) if path is not None else DEFAULT_MAPPING_PATH
    raw = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    technologies = raw.get("technologies")
    if not isinstance(technologies, dict):
        raise ValueError(f"Employment mapping {mapping_path} must define a technologies mapping.")

    parsed: dict[str, list[EmploymentComponent]] = {}
    for model_technology, payload in technologies.items():
        if not isinstance(payload, dict):
            raise ValueError(f"Mapping for {model_technology!r} must be an object.")
        components_raw = payload.get("components")
        if not isinstance(components_raw, list) or not components_raw:
            raise ValueError(f"Mapping for {model_technology!r} must define at least one component.")

        components: list[EmploymentComponent] = []
        for component in components_raw:
            if not isinstance(component, dict):
                raise ValueError(f"Component for {model_technology!r} must be an object.")
            employment_technology = str(component.get("employment_technology") or "").strip()
            if not employment_technology:
                raise ValueError(f"Component for {model_technology!r} is missing employment_technology.")
            multiplier = float(component.get("multiplier", 1.0))
            if multiplier < 0:
                raise ValueError(f"Component multiplier for {model_technology!r} cannot be negative.")
            note = component.get("note")
            components.append(
                EmploymentComponent(
                    employment_technology=employment_technology,
                    multiplier=multiplier,
                    note=str(note) if note else None,
                )
            )
        parsed[str(model_technology)] = components
    return parsed


def load_model_employment_factors() -> pd.DataFrame:
    """Load model-ready employment factors from the external package."""
    try:
        from colombia_employment_factors import get_model_employment_factors
    except ImportError as exc:  # pragma: no cover - exercised only in broken envs
        raise RuntimeError(
            "colombia-employment-factors is required for employment post-processing."
        ) from exc
    return get_model_employment_factors()


def _factor_lookup(factors: pd.DataFrame) -> dict[tuple[str, int, str], list[dict[str, Any]]]:
    """Index direct C&M and O&M factor rows by technology, year, and factor type."""
    required = {"Technology", "Year", "Factor_Type", "Job_Type", "Value_Numeric"}
    missing = required - set(factors.columns)
    if missing:
        raise ValueError(f"Employment factors missing required columns: {sorted(missing)}")

    eligible = factors[
        (factors["Job_Type"] == DIRECT_JOB_TYPE)
        & (factors["Factor_Type"].isin([CONSTRUCTION_FACTOR_TYPE, OM_FACTOR_TYPE]))
    ].copy()
    eligible["Year"] = pd.to_numeric(eligible["Year"], errors="coerce").astype("Int64")
    eligible["Value_Numeric"] = pd.to_numeric(eligible["Value_Numeric"], errors="coerce")
    eligible = eligible.dropna(subset=["Year", "Value_Numeric"])

    lookup: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for row in eligible.to_dict(orient="records"):
        key = (str(row["Technology"]), int(row["Year"]), str(row["Factor_Type"]))
        lookup.setdefault(key, []).append(row)
    return lookup


def _lookup_id(lookups: dict[str, dict[str, int]], dimension: str, name: str | None) -> int | None:
    if not name:
        return None
    value = (lookups.get(dimension) or {}).get(str(name))
    return int(value) if value is not None else None


def _new_capacity_rows(solution: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in solution.get("new_capacity", []) or []:
        year = row.get("year")
        if year is None or int(year) < OPTIMIZATION_START_YEAR:
            continue
        rows.append(
            {
                "source_variable": "NewCapacity",
                "region_id": row.get("region_id"),
                "technology_id": row.get("technology_id"),
                "region_name": row.get("region_name"),
                "technology_name": row.get("technology_name"),
                "year": int(year),
                "capacity_pj_per_year": float(row.get("new_capacity", 0.0) or 0.0),
            }
        )
    return rows


def _accumulated_new_capacity_rows(solution: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lookups = solution.get("dimension_lookups", {}) or {}
    for entry in (solution.get("intermediate_variables", {}) or {}).get("AccumulatedNewCapacity", []) or []:
        idx = entry.get("index") or []
        if len(idx) != 3:
            continue
        region_name, technology_name, year = idx
        if year is None or int(year) < OPTIMIZATION_START_YEAR:
            continue
        rows.append(
            {
                "source_variable": "AccumulatedNewCapacity",
                "region_id": _lookup_id(lookups, "REGION", str(region_name)),
                "technology_id": _lookup_id(lookups, "TECHNOLOGY", str(technology_name)),
                "region_name": str(region_name),
                "technology_name": str(technology_name),
                "year": int(year),
                "capacity_pj_per_year": float(entry.get("value", 0.0) or 0.0),
            }
        )
    return rows


def _calculate_for_capacity_row(
    capacity_row: dict[str, Any],
    *,
    factor_type: str,
    mapping: dict[str, list[EmploymentComponent]],
    factors_by_key: dict[tuple[str, int, str], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    model_technology = str(capacity_row.get("technology_name") or "")
    components = mapping.get(model_technology)
    if not components:
        return None

    capacity_mw = pj_per_year_to_mw(capacity_row.get("capacity_pj_per_year"))
    component_details: list[dict[str, Any]] = []
    total_employment = 0.0
    for component in components:
        factor_rows = factors_by_key.get(
            (component.employment_technology, int(capacity_row["year"]), factor_type),
            [],
        )
        component_capacity_mw = capacity_mw * component.multiplier
        for factor in factor_rows:
            factor_value = float(factor["Value_Numeric"])
            employment = component_capacity_mw * factor_value
            total_employment += employment
            component_details.append(
                {
                    "employment_technology": component.employment_technology,
                    "multiplier": component.multiplier,
                    "capacity_mw": component_capacity_mw,
                    "factor_value": factor_value,
                    "factor_unit": factor.get("Unit"),
                    "source": factor.get("Source"),
                    "employment": employment,
                    "note": component.note,
                }
            )

    if not component_details:
        return None

    return {
        "variable_name": EMPLOYMENT_VARIABLE_BY_FACTOR_TYPE[factor_type],
        "region_id": capacity_row.get("region_id"),
        "technology_id": capacity_row.get("technology_id"),
        "region_name": capacity_row.get("region_name"),
        "technology_name": model_technology,
        "year": int(capacity_row["year"]),
        "value": total_employment,
        "source_variable": capacity_row["source_variable"],
        "factor_type": factor_type,
        "job_type": DIRECT_JOB_TYPE,
        "model_capacity_pj_per_year": float(capacity_row.get("capacity_pj_per_year", 0.0) or 0.0),
        "model_capacity_mw": capacity_mw,
        "components": component_details,
    }


def calculate_employment_outputs(
    solution: dict[str, Any],
    *,
    factors: pd.DataFrame | None = None,
    mapping: dict[str, list[EmploymentComponent]] | None = None,
) -> list[dict[str, Any]]:
    """Calculate direct employment outputs from solved capacity variables.

    Construction/manufacturing employment uses ``NewCapacity``. O&M employment
    uses ``AccumulatedNewCapacity`` so residual 2024 capacity is excluded.
    """
    resolved_mapping = mapping if mapping is not None else load_technology_mapping()
    resolved_factors = factors if factors is not None else load_model_employment_factors()
    factors_by_key = _factor_lookup(resolved_factors)

    outputs: list[dict[str, Any]] = []
    for row in _new_capacity_rows(solution):
        result = _calculate_for_capacity_row(
            row,
            factor_type=CONSTRUCTION_FACTOR_TYPE,
            mapping=resolved_mapping,
            factors_by_key=factors_by_key,
        )
        if result is not None:
            outputs.append(result)

    for row in _accumulated_new_capacity_rows(solution):
        result = _calculate_for_capacity_row(
            row,
            factor_type=OM_FACTOR_TYPE,
            mapping=resolved_mapping,
            factors_by_key=factors_by_key,
        )
        if result is not None:
            outputs.append(result)

    return outputs


def attach_employment_outputs(solution: dict[str, Any]) -> dict[str, Any]:
    """Mutate ``solution`` with derived employment rows and return it."""
    employment_outputs = calculate_employment_outputs(solution)
    solution["employment_outputs"] = employment_outputs
    logger.info("Calculated %d direct employment output rows.", len(employment_outputs))
    return solution
