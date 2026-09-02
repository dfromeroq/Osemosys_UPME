"""Derived employment-factor outputs for solved OSeMOSYS simulations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import floor
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

EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT = "Employment_FTEyear_ConsManu_Direct"
EMPLOYMENT_FTE_CONSMANU_DIRECT_ANNUALIZED_IN_HORIZON = (
    "Employment_FTE_ConsManu_Direct_Annualized_InHorizon"
)
EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT_PRE_HORIZON = (
    "Employment_FTEyear_ConsManu_Direct_PreHorizon"
)
EMPLOYMENT_FTE_OM_DIRECT_ANNUAL = "Employment_FTE_OM_Direct_Annual"
EMPLOYMENT_FTE_TOTAL_DIRECT_ANNUAL_IN_HORIZON = (
    "Employment_FTE_Total_Direct_Annual_InHorizon"
)
EMPLOYMENT_FTEYEAR_OM_DIRECT_CUMULATIVE_IN_HORIZON = (
    "Employment_FTEyear_OM_Direct_Cumulative_InHorizon"
)
EMPLOYMENT_FTEYEAR_TOTAL_DIRECT_CUMULATIVE_IN_HORIZON = (
    "Employment_FTEyear_Total_Direct_Cumulative_InHorizon"
)

EMPLOYMENT_VARIABLE_BY_FACTOR_TYPE = {
    CONSTRUCTION_FACTOR_TYPE: EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT,
    OM_FACTOR_TYPE: EMPLOYMENT_FTE_OM_DIRECT_ANNUAL,
}

DEFAULT_MAPPING_PATH = Path(__file__).with_name("employment_factors_mapping.yaml")


@dataclass(frozen=True)
class EmploymentComponent:
    """One employment-factor technology represented by a model technology."""

    employment_technology: str
    multiplier: float = 1.0
    note: str | None = None


@dataclass(frozen=True)
class TechnologyAssumption:
    """Construction-time and lifetime assumptions for one factor technology."""

    employment_technology: str
    construction_time_years: float
    lifetime_years: float | None = None
    construction_time_source: str | None = None
    construction_time_source_year: int | None = None
    lifetime_source_year: int | None = None


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


def load_technology_assumptions(
    mapping: dict[str, list[EmploymentComponent]] | None = None,
) -> dict[str, TechnologyAssumption]:
    """Load construction-time and lifetime assumptions for mapped technologies."""
    try:
        from colombia_employment_factors import get_technology_assumption
    except ImportError as exc:  # pragma: no cover - exercised only in broken envs
        raise RuntimeError(
            "colombia-employment-factors is required for employment assumptions."
        ) from exc

    resolved_mapping = mapping if mapping is not None else load_technology_mapping()
    technologies = sorted(
        {
            component.employment_technology
            for components in resolved_mapping.values()
            for component in components
        }
    )
    assumptions: dict[str, TechnologyAssumption] = {}
    for technology in technologies:
        raw = get_technology_assumption(technology)

        def _get(name: str):
            if isinstance(raw, dict):
                return raw.get(name)
            return raw.get(name) if hasattr(raw, "get") else getattr(raw, name, None)

        construction_time = _coerce_positive_float(
            _get("construction_time_years"),
            field_name=f"{technology}.construction_time_years",
        )
        lifetime_raw = _get("lifetime_years")
        lifetime = None if pd.isna(lifetime_raw) else float(lifetime_raw)
        assumptions[technology] = TechnologyAssumption(
            employment_technology=technology,
            construction_time_years=construction_time,
            lifetime_years=lifetime,
            construction_time_source=_none_if_nan(_get("construction_time_source")),
            construction_time_source_year=_coerce_optional_int(
                _get("construction_time_source_year")
            ),
            lifetime_source_year=_coerce_optional_int(_get("lifetime_source_year")),
        )
    return assumptions


def _none_if_nan(value):
    if value is None or pd.isna(value):
        return None
    return str(value)


def _coerce_optional_int(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(float(value))


def _coerce_positive_float(value, *, field_name: str) -> float:
    if value is None or pd.isna(value):
        raise ValueError(f"Missing required employment assumption: {field_name}")
    out = float(value)
    if out <= 0:
        raise ValueError(f"Employment assumption must be positive: {field_name}")
    return out


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


def _base_output_row(
    capacity_row: dict[str, Any],
    *,
    variable_name: str,
    value: float,
    source_variable: str,
    factor_type: str | None,
    components: list[dict[str, Any]],
    year: int | None = None,
    job_type: str = DIRECT_JOB_TYPE,
) -> dict[str, Any]:
    out_year = int(capacity_row["year"]) if year is None else int(year)
    return {
        "variable_name": variable_name,
        "region_id": capacity_row.get("region_id"),
        "technology_id": capacity_row.get("technology_id"),
        "region_name": capacity_row.get("region_name"),
        "technology_name": str(capacity_row.get("technology_name") or ""),
        "year": out_year,
        "value": float(value),
        "source_variable": source_variable,
        "factor_type": factor_type,
        "job_type": job_type,
        "commissioning_year": int(capacity_row["year"]),
        "model_capacity_pj_per_year": float(capacity_row.get("capacity_pj_per_year", 0.0) or 0.0),
        "model_capacity_mw": pj_per_year_to_mw(capacity_row.get("capacity_pj_per_year")),
        "components": components,
    }


def _component_factor_records(
    capacity_row: dict[str, Any],
    *,
    factor_type: str,
    mapping: dict[str, list[EmploymentComponent]],
    factors_by_key: dict[tuple[str, int, str], list[dict[str, Any]]],
    assumptions: dict[str, TechnologyAssumption],
) -> list[dict[str, Any]]:
    """Return component-level employment calculations for one capacity row."""
    model_technology = str(capacity_row.get("technology_name") or "")
    components = mapping.get(model_technology)
    if not components:
        return []

    capacity_mw = pj_per_year_to_mw(capacity_row.get("capacity_pj_per_year"))
    records: list[dict[str, Any]] = []
    for component in components:
        assumption = assumptions.get(component.employment_technology)
        if assumption is None:
            raise ValueError(
                f"Missing technology assumptions for {component.employment_technology!r}."
            )
        factor_rows = factors_by_key.get(
            (component.employment_technology, int(capacity_row["year"]), factor_type),
            [],
        )
        component_capacity_mw = capacity_mw * component.multiplier
        for factor in factor_rows:
            factor_value = float(factor["Value_Numeric"])
            employment = component_capacity_mw * factor_value
            records.append(
                {
                    "employment_technology": component.employment_technology,
                    "multiplier": component.multiplier,
                    "capacity_mw": component_capacity_mw,
                    "factor_value": factor_value,
                    "factor_unit": factor.get("Unit"),
                    "source": factor.get("Source"),
                    "employment": employment,
                    "note": component.note,
                    "construction_time_years": assumption.construction_time_years,
                    "lifetime_years": assumption.lifetime_years,
                    "construction_time_source": assumption.construction_time_source,
                    "construction_time_source_year": assumption.construction_time_source_year,
                    "lifetime_source_year": assumption.lifetime_source_year,
                }
            )
    return records


def _construction_year_weights(
    *,
    commissioning_year: int,
    construction_time_years: float,
) -> list[tuple[int, float]]:
    """Allocate a construction interval ending in the commissioning year.

    The returned weight is the number of construction years overlapping each
    calendar/model year. Fractional construction times are supported, and the
    weights sum to ``construction_time_years``.
    """
    duration = _coerce_positive_float(
        construction_time_years,
        field_name="construction_time_years",
    )
    start = float(commissioning_year + 1) - duration
    first_year = floor(start)
    weights: list[tuple[int, float]] = []
    for year in range(first_year, commissioning_year + 1):
        overlap = max(0.0, min(year + 1.0, commissioning_year + 1.0) - max(year * 1.0, start))
        if overlap > 1e-12:
            weights.append((year, overlap))
    return weights


def _sum_components(records: list[dict[str, Any]]) -> float:
    return sum(float(record.get("employment", 0.0) or 0.0) for record in records)


def _append_or_accumulate(
    rows: dict[tuple, dict[str, Any]],
    row: dict[str, Any],
) -> None:
    key = (
        row.get("variable_name"),
        row.get("region_id"),
        row.get("technology_id"),
        row.get("technology_name"),
        row.get("year"),
        row.get("source_variable"),
        row.get("factor_type"),
    )
    existing = rows.get(key)
    if existing is None:
        rows[key] = row
        return
    existing["value"] = float(existing.get("value", 0.0) or 0.0) + float(row.get("value", 0.0) or 0.0)
    existing.setdefault("components", []).extend(row.get("components", []))


def calculate_employment_outputs(
    solution: dict[str, Any],
    *,
    factors: pd.DataFrame | None = None,
    mapping: dict[str, list[EmploymentComponent]] | None = None,
    assumptions: dict[str, TechnologyAssumption] | None = None,
) -> list[dict[str, Any]]:
    """Calculate direct employment outputs from solved capacity variables.

    Construction/manufacturing employment uses ``NewCapacity``. O&M employment
    uses ``AccumulatedNewCapacity`` so residual 2024 capacity is excluded.
    Construction/manufacturing job-years are also spread over construction
    durations to create comparable annual in-horizon FTE outputs.
    """
    resolved_mapping = mapping if mapping is not None else load_technology_mapping()
    resolved_factors = factors if factors is not None else load_model_employment_factors()
    resolved_assumptions = (
        assumptions
        if assumptions is not None
        else load_technology_assumptions(resolved_mapping)
    )
    factors_by_key = _factor_lookup(resolved_factors)

    outputs: list[dict[str, Any]] = []
    annual_rows: dict[tuple, dict[str, Any]] = {}
    om_annual_rows: dict[tuple, dict[str, Any]] = {}

    for row in _new_capacity_rows(solution):
        component_records = _component_factor_records(
            row,
            factor_type=CONSTRUCTION_FACTOR_TYPE,
            mapping=resolved_mapping,
            factors_by_key=factors_by_key,
            assumptions=resolved_assumptions,
        )
        if not component_records:
            continue

        outputs.append(
            _base_output_row(
                row,
                variable_name=EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT,
                value=_sum_components(component_records),
                source_variable="NewCapacity",
                factor_type=CONSTRUCTION_FACTOR_TYPE,
                components=component_records,
            )
        )

        pre_horizon_components: list[dict[str, Any]] = []
        pre_horizon_value = 0.0
        for component_record in component_records:
            duration = float(component_record["construction_time_years"])
            annual_fte_during_construction = float(component_record["employment"]) / duration
            for allocation_year, overlap_years in _construction_year_weights(
                commissioning_year=int(row["year"]),
                construction_time_years=duration,
            ):
                allocated_value = annual_fte_during_construction * overlap_years
                allocation_component = {
                    **component_record,
                    "employment": allocated_value,
                    "construction_overlap_years": overlap_years,
                    "annual_fte_during_construction": annual_fte_during_construction,
                    "allocation_year": allocation_year,
                }
                if allocation_year < OPTIMIZATION_START_YEAR:
                    pre_horizon_value += allocated_value
                    pre_horizon_components.append(allocation_component)
                    continue

                annual_row = _base_output_row(
                    row,
                    variable_name=EMPLOYMENT_FTE_CONSMANU_DIRECT_ANNUALIZED_IN_HORIZON,
                    value=allocated_value,
                    source_variable=EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT,
                    factor_type=CONSTRUCTION_FACTOR_TYPE,
                    components=[allocation_component],
                    year=allocation_year,
                )
                _append_or_accumulate(annual_rows, annual_row)

        if pre_horizon_components:
            outputs.append(
                _base_output_row(
                    row,
                    variable_name=EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT_PRE_HORIZON,
                    value=pre_horizon_value,
                    source_variable=EMPLOYMENT_FTEYEAR_CONSMANU_DIRECT,
                    factor_type=CONSTRUCTION_FACTOR_TYPE,
                    components=pre_horizon_components,
                    year=int(row["year"]),
                )
            )

    for row in _accumulated_new_capacity_rows(solution):
        component_records = _component_factor_records(
            row,
            factor_type=OM_FACTOR_TYPE,
            mapping=resolved_mapping,
            factors_by_key=factors_by_key,
            assumptions=resolved_assumptions,
        )
        if not component_records:
            continue
        result = _base_output_row(
            row,
            variable_name=EMPLOYMENT_FTE_OM_DIRECT_ANNUAL,
            value=_sum_components(component_records),
            source_variable="AccumulatedNewCapacity",
            factor_type=OM_FACTOR_TYPE,
            components=component_records,
        )
        outputs.append(result)
        _append_or_accumulate(om_annual_rows, result)

    outputs.extend(annual_rows.values())

    total_annual_rows: dict[tuple, dict[str, Any]] = {}
    for source_rows in (annual_rows, om_annual_rows):
        for row in source_rows.values():
            total_row = {
                **row,
                "variable_name": EMPLOYMENT_FTE_TOTAL_DIRECT_ANNUAL_IN_HORIZON,
                "source_variable": "DerivedAnnualEmployment",
                "factor_type": "TotalAnnualFTE",
                "components": [
                    {
                        "source_variable": row.get("variable_name"),
                        "employment": row.get("value", 0.0),
                    }
                ],
            }
            _append_or_accumulate(total_annual_rows, total_row)
    outputs.extend(total_annual_rows.values())

    def _append_cumulative(
        source: dict[tuple, dict[str, Any]],
        *,
        variable_name: str,
        source_variable: str,
        factor_type: str,
    ) -> None:
        groups: dict[tuple, list[dict[str, Any]]] = {}
        for row in source.values():
            group_key = (
                row.get("region_id"),
                row.get("technology_id"),
                row.get("technology_name"),
            )
            groups.setdefault(group_key, []).append(row)
        for rows in groups.values():
            cumulative = 0.0
            for row in sorted(rows, key=lambda item: int(item["year"])):
                cumulative += float(row.get("value", 0.0) or 0.0)
                outputs.append(
                    {
                        **row,
                        "variable_name": variable_name,
                        "value": cumulative,
                        "source_variable": source_variable,
                        "factor_type": factor_type,
                        "components": [
                            {
                                "source_variable": row.get("variable_name"),
                                "annual_value": row.get("value", 0.0),
                                "cumulative_value": cumulative,
                            }
                        ],
                    }
                )

    _append_cumulative(
        om_annual_rows,
        variable_name=EMPLOYMENT_FTEYEAR_OM_DIRECT_CUMULATIVE_IN_HORIZON,
        source_variable=EMPLOYMENT_FTE_OM_DIRECT_ANNUAL,
        factor_type="CumulativeOMFTEyear",
    )
    _append_cumulative(
        total_annual_rows,
        variable_name=EMPLOYMENT_FTEYEAR_TOTAL_DIRECT_CUMULATIVE_IN_HORIZON,
        source_variable=EMPLOYMENT_FTE_TOTAL_DIRECT_ANNUAL_IN_HORIZON,
        factor_type="CumulativeTotalFTEyear",
    )

    return outputs


def attach_employment_outputs(solution: dict[str, Any]) -> dict[str, Any]:
    """Mutate ``solution`` with derived employment rows and return it."""
    employment_outputs = calculate_employment_outputs(solution)
    solution["employment_outputs"] = employment_outputs
    logger.info("Calculated %d direct employment output rows.", len(employment_outputs))
    return solution
