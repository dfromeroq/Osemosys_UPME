#!/usr/bin/env python
"""Audita rutas de fuels OSeMOSYS por región/año con pandas y cierre de grafo.

No resuelve el LP. Una demanda no alcanzable desde ningún proceso sin input es
una imposibilidad estructural necesaria, incluso si existe OutputActivityRatio
local: los productores pueden formar un ciclo sin fuente primaria.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter
from typing import DefaultDict

import pandas as pd

EPS = 1e-12
PROC = tuple[str, str, str, str]


def read(root: Path, name: str, columns: list[str]) -> pd.DataFrame:
    path = root / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame(columns=[*columns, "VALUE"])
    frame = pd.read_csv(path)
    if not set([*columns, "VALUE"]).issubset(frame.columns):
        return pd.DataFrame(columns=[*columns, "VALUE"])
    frame = frame[[*columns, "VALUE"]].copy()
    for column in columns:
        frame[column] = frame[column].astype(str).str.strip()
    frame["VALUE"] = pd.to_numeric(frame["VALUE"], errors="coerce").fillna(0.0)
    return frame[frame["VALUE"] > EPS]


def demand_keys(root: Path) -> set[tuple[str, str, str]]:
    accumulated = read(root, "AccumulatedAnnualDemand", ["REGION", "FUEL", "YEAR"])
    return {
        (row.REGION, row.FUEL, row.YEAR)
        for row in accumulated.itertuples(index=False)
    }


def audit(root: Path) -> dict:
    started = perf_counter()
    cols = ["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "FUEL", "YEAR"]
    inputs = read(root, "InputActivityRatio", cols)
    outputs = read(root, "OutputActivityRatio", cols)
    process_inputs: DefaultDict[PROC, set[str]] = defaultdict(set)
    process_outputs: DefaultDict[PROC, set[str]] = defaultdict(set)
    for row in inputs.itertuples(index=False):
        process_inputs[(row.REGION, row.TECHNOLOGY, row.MODE_OF_OPERATION, row.YEAR)].add(row.FUEL)
    for row in outputs.itertuples(index=False):
        process_outputs[(row.REGION, row.TECHNOLOGY, row.MODE_OF_OPERATION, row.YEAR)].add(row.FUEL)

    by_region_year: DefaultDict[tuple[str, str], list[PROC]] = defaultdict(list)
    for process in process_outputs:
        by_region_year[(process[0], process[3])].append(process)

    demanded_keys = demand_keys(root)
    unreachable: list[dict] = []
    reachability_summary: list[dict] = []
    for region_year, processes in by_region_year.items():
        reachable: set[str] = set()
        primary_processes = 0
        for process in processes:
            if not process_inputs.get(process):
                reachable.update(process_outputs[process])
                primary_processes += 1
        changed = True
        iterations = 0
        while changed:
            changed = False
            iterations += 1
            for process in processes:
                if process_inputs.get(process, set()).issubset(reachable):
                    before = len(reachable)
                    reachable.update(process_outputs[process])
                    changed = changed or len(reachable) > before
        region, year = region_year
        demanded = sorted(
            fuel for r, fuel, y in demanded_keys if r == region and y == year
        )
        missing = [fuel for fuel in demanded if fuel not in reachable]
        reachability_summary.append(
            {
                "REGION": region,
                "YEAR": year,
                "processes_with_output": len(processes),
                "primary_processes": primary_processes,
                "reachable_fuels": len(reachable),
                "demanded_fuels": len(demanded),
                "unreachable_demanded_fuels": missing,
                "iterations": iterations,
            }
        )
        for fuel in missing:
            candidate_processes = [
                process for process in processes if fuel in process_outputs[process]
            ]
            unreachable.append(
                {
                    "code": "DEMAND_FUEL_WITHOUT_PRIMARY_INPUT_ROUTE",
                    "evidence_level": "STRUCTURAL",
                    "dimensions": {"REGION": region, "FUEL": fuel, "YEAR": year},
                    "candidate_processes": [
                        {
                            "TECHNOLOGY": process[1],
                            "MODE_OF_OPERATION": process[2],
                            "required_inputs": sorted(process_inputs.get(process, set())),
                        }
                        for process in candidate_processes[:25]
                    ],
                }
            )
    return {
        "seconds": round(perf_counter() - started, 3),
        "finding_count": len(unreachable),
        "finding_codes": dict(Counter(item["code"] for item in unreachable)),
        "findings": unreachable,
        "region_year_summary": reachability_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.csv_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "findings" and key != "region_year_summary"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
