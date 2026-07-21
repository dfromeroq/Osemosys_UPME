#!/usr/bin/env python
"""Auditoría pandas de imposibilidades necesarias en CSVs OSeMOSYS.

No resuelve LP ni modifica entradas. Es deliberadamente conservadora: sólo
reporta un hallazgo cuando un mínimo de actividad positivo no puede obtener
capacidad utilizable bajo cotas explícitas, residual, vida útil e inversión.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

INF = 9_999_999.0
# No convertir ruido de doble precisión/subnormal en una causa física.
ZERO_TOL = 1e-12
ACTIVITY_TOL = 1e-6


def read(root: Path, name: str, columns: list[str]) -> pd.DataFrame:
    path = root / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame(columns=[*columns, "VALUE"])
    frame = pd.read_csv(path)
    if not set([*columns, "VALUE"]).issubset(frame.columns):
        return pd.DataFrame(columns=[*columns, "VALUE"])
    frame = frame[[*columns, "VALUE"]].copy()
    for col in columns:
        frame[col] = frame[col].astype(str).str.strip()
    frame["VALUE"] = pd.to_numeric(frame["VALUE"], errors="coerce").fillna(0.0)
    return frame


def build_capacity_upper_bound(root: Path) -> dict[tuple[str, str, str], float]:
    """Cota superior conservadora de capacidad por (región, tecnología, año).

    Una celda de máximo de inversión ausente usa el default OSeMOSYS 9,999,999;
    por tanto sólo produce una cota finita cuando todos los años de inversión
    vivos están explícitamente acotados.
    """
    key3 = ["REGION", "TECHNOLOGY", "YEAR"]
    residual = read(root, "ResidualCapacity", key3)
    max_investment = read(root, "TotalAnnualMaxCapacityInvestment", key3)
    max_capacity = read(root, "TotalAnnualMaxCapacity", key3)
    life = read(root, "OperationalLife", ["REGION", "TECHNOLOGY"])
    # YEAR.csv is a one-column set rather than a VALUE parameter.
    year_path = root / "YEAR.csv"
    years = sorted(pd.read_csv(year_path).iloc[:, 0].astype(int).tolist()) if year_path.exists() else []

    residual_map = {
        (row.REGION, row.TECHNOLOGY, row.YEAR): float(row.VALUE)
        for row in residual.itertuples(index=False)
    }
    investment_map = {
        (row.REGION, row.TECHNOLOGY, row.YEAR): float(row.VALUE)
        for row in max_investment.itertuples(index=False)
    }
    capacity_map = {
        (row.REGION, row.TECHNOLOGY, row.YEAR): float(row.VALUE)
        for row in max_capacity.itertuples(index=False)
    }
    life_map = {
        (row.REGION, row.TECHNOLOGY): float(row.VALUE)
        for row in life.itertuples(index=False)
    }
    universe = set(residual_map) | set(investment_map) | set(capacity_map)
    result: dict[tuple[str, str, str], float] = {}
    for region, technology, raw_year in universe:
        year = int(raw_year)
        operational_life = life_map.get((region, technology), 1.0)
        new_capacity = 0.0
        for investment_year in years:
            if investment_year > year or year - investment_year >= operational_life:
                continue
            maximum = investment_map.get((region, technology, str(investment_year)), INF)
            if maximum >= INF:
                new_capacity = INF
                break
            new_capacity += max(0.0, maximum)
        upper = residual_map.get((region, technology, raw_year), 0.0) + new_capacity
        upper = min(upper, capacity_map.get((region, technology, raw_year), INF))
        result[(region, technology, raw_year)] = upper
    return result


def audit(root: Path) -> dict[str, Any]:
    started = perf_counter()
    key3 = ["REGION", "TECHNOLOGY", "YEAR"]
    annual_min = read(root, "TotalTechnologyAnnualActivityLowerLimit", key3)
    horizon_min = read(root, "TotalTechnologyModelPeriodActivityLowerLimit", ["REGION", "TECHNOLOGY"])
    capacity_upper = build_capacity_upper_bound(root)
    availability = read(root, "AvailabilityFactor", key3)
    c2a = read(root, "CapacityToActivityUnit", ["REGION", "TECHNOLOGY"])
    capacity_factor = read(root, "CapacityFactor", ["REGION", "TECHNOLOGY", "TIMESLICE", "YEAR"])
    year_split = read(root, "YearSplit", ["TIMESLICE", "YEAR"])

    availability_map = {
        (row.REGION, row.TECHNOLOGY, row.YEAR): float(row.VALUE)
        for row in availability.itertuples(index=False)
    }
    c2a_map = {
        (row.REGION, row.TECHNOLOGY): float(row.VALUE)
        for row in c2a.itertuples(index=False)
    }
    all_capacity_factor_zero = {
        (str(region), str(technology), str(year))
        for (region, technology, year), values in capacity_factor.groupby(
            ["REGION", "TECHNOLOGY", "YEAR"]
        )["VALUE"]
        if bool((values <= ZERO_TOL).all())
    }
    capacity_factor_map = {
        (row.REGION, row.TECHNOLOGY, row.TIMESLICE, row.YEAR): float(row.VALUE)
        for row in capacity_factor.itertuples(index=False)
    }
    year_split_map = {
        (row.TIMESLICE, row.YEAR): float(row.VALUE)
        for row in year_split.itertuples(index=False)
    }
    timeslices_by_year: dict[str, list[str]] = {}
    for timeslice, year in year_split_map:
        timeslices_by_year.setdefault(year, []).append(timeslice)

    findings: list[dict[str, Any]] = []
    annual_positive = annual_min[annual_min["VALUE"] > ACTIVITY_TOL]
    for row in annual_positive.itertuples(index=False):
        key = (row.REGION, row.TECHNOLOGY, row.YEAR)
        reasons: list[str] = []
        capacity = capacity_upper.get(key, INF)
        if capacity <= ZERO_TOL:
            reasons.append("capacity_upper_bound_zero")
        if availability_map.get(key, 1.0) <= ZERO_TOL:
            reasons.append("availability_factor_zero")
        if c2a_map.get((row.REGION, row.TECHNOLOGY), 1.0) <= ZERO_TOL:
            reasons.append("capacity_to_activity_unit_zero")
        if key in all_capacity_factor_zero:
            reasons.append("all_capacity_factors_zero")
        capacity_activity_upper = capacity
        if capacity < INF:
            annual_factor = sum(
                year_split_map[(timeslice, row.YEAR)]
                * capacity_factor_map.get(
                    (row.REGION, row.TECHNOLOGY, timeslice, row.YEAR), 1.0
                )
                for timeslice in timeslices_by_year.get(row.YEAR, [])
            )
            capacity_activity_upper *= (
                c2a_map.get((row.REGION, row.TECHNOLOGY), 1.0)
                * availability_map.get(key, 1.0)
                * annual_factor
            )
        if reasons or row.VALUE > capacity_activity_upper + ACTIVITY_TOL:
            if row.VALUE > capacity_activity_upper + ACTIVITY_TOL:
                reasons.append("annual_activity_minimum_exceeds_capacity_activity_upper")
            findings.append(
                {
                    "code": "MANDATED_ANNUAL_ACTIVITY_WITHOUT_USABLE_CAPACITY",
                    "evidence_level": "STRUCTURAL",
                    "dimensions": {
                        "REGION": row.REGION,
                        "TECHNOLOGY": row.TECHNOLOGY,
                        "YEAR": row.YEAR,
                    },
                    "required_activity": float(row.VALUE),
                    "capacity_upper_bound": capacity,
                    "capacity_activity_upper_bound": capacity_activity_upper,
                    "gap": max(0.0, float(row.VALUE) - capacity_activity_upper),
                    "reasons": reasons,
                }
            )

    annual_by_tech: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for finding in findings:
        key = (finding["dimensions"]["REGION"], finding["dimensions"]["TECHNOLOGY"])
        annual_by_tech.setdefault(key, []).append(finding)
    for row in horizon_min[horizon_min["VALUE"] > ACTIVITY_TOL].itertuples(index=False):
        key = (row.REGION, row.TECHNOLOGY)
        if key not in annual_by_tech:
            continue
        findings.append(
            {
                "code": "MANDATED_HORIZON_ACTIVITY_WITHOUT_USABLE_CAPACITY",
                "evidence_level": "STRUCTURAL",
                "dimensions": {"REGION": row.REGION, "TECHNOLOGY": row.TECHNOLOGY},
                "required_activity": float(row.VALUE),
                "blocked_years": [item["dimensions"]["YEAR"] for item in annual_by_tech[key]],
            }
        )

    return {
        "csv_dir": str(root),
        "seconds": round(perf_counter() - started, 3),
        "finding_count": len(findings),
        "finding_codes": dict(Counter(item["code"] for item in findings)),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.csv_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "findings"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
