#!/usr/bin/env python3
"""Resuelve un CSV-dir y reporta residuos de restricciones/variables.

Sirve para distinguir una diferencia de objetivo por múltiples óptimos de una
solución que sólo parece óptima debido a tolerancias/escalamiento del solver.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
import time
from pathlib import Path

import pyomo.environ as pyo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.simulation.osemosys_core import run_osemosys_from_csv_dir  # noqa: E402


def _finite(value) -> float | None:
    if value is None:
        return None
    try:
        result = float(pyo.value(value))
    except Exception:
        return None
    return result if math.isfinite(result) else None


def analyze_instance(instance, *, top_n: int = 30) -> dict:
    started = time.perf_counter()
    top: list[tuple[float, int, dict]] = []
    checked = 0
    eval_errors = 0
    violation_counts = {"gt_1e-9": 0, "gt_1e-7": 0, "gt_1e-6": 0, "gt_1e-4": 0}
    max_abs = 0.0
    max_rel = 0.0
    serial = 0

    for con in instance.component_data_objects(pyo.Constraint, active=True, descend_into=True):
        body = _finite(con.body)
        if body is None:
            eval_errors += 1
            continue
        lower = _finite(con.lower)
        upper = _finite(con.upper)
        violation = 0.0
        side = ""
        bound = None
        if lower is not None and body < lower:
            violation = lower - body
            side = "lower"
            bound = lower
        if upper is not None and body > upper and body - upper > violation:
            violation = body - upper
            side = "upper"
            bound = upper
        checked += 1
        scale = max(1.0, abs(body), abs(bound or 0.0))
        rel = violation / scale
        max_abs = max(max_abs, violation)
        max_rel = max(max_rel, rel)
        for label, threshold in (
            ("gt_1e-9", 1e-9),
            ("gt_1e-7", 1e-7),
            ("gt_1e-6", 1e-6),
            ("gt_1e-4", 1e-4),
        ):
            if violation > threshold:
                violation_counts[label] += 1
        if violation > 0:
            item = {
                "name": con.name,
                "body": body,
                "lower": lower,
                "upper": upper,
                "side": side,
                "abs_violation": violation,
                "rel_violation": rel,
            }
            serial += 1
            entry = (violation, serial, item)
            if len(top) < top_n:
                heapq.heappush(top, entry)
            elif violation > top[0][0]:
                heapq.heapreplace(top, entry)

    var_checked = 0
    var_violations = 0
    max_var_violation = 0.0
    for var in instance.component_data_objects(pyo.Var, active=True, descend_into=True):
        value = _finite(var)
        if value is None:
            continue
        var_checked += 1
        violation = 0.0
        if var.lb is not None and value < float(var.lb):
            violation = max(violation, float(var.lb) - value)
        if var.ub is not None and value > float(var.ub):
            violation = max(violation, value - float(var.ub))
        if violation > 1e-9:
            var_violations += 1
            max_var_violation = max(max_var_violation, violation)

    return {
        "constraint_count": checked,
        "constraint_eval_errors": eval_errors,
        "violation_counts": violation_counts,
        "max_abs_constraint_violation": max_abs,
        "max_rel_constraint_violation": max_rel,
        "top_constraint_violations": [item for _, _, item in sorted(top, reverse=True)],
        "variable_count": var_checked,
        "variable_bound_violations_gt_1e-9": var_violations,
        "max_variable_bound_violation": max_var_violation,
        "analysis_seconds": time.perf_counter() - started,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", type=Path, required=True)
    parser.add_argument("--solver", choices=["glpk", "highs"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    residual_report: dict = {}

    def hook(instance, solver, solver_result, solution) -> None:  # noqa: ARG001
        nonlocal residual_report
        residual_report = analyze_instance(instance, top_n=args.top)
        residual_report["solver_status_at_hook"] = solution.get("solver_status")
        residual_report["objective_at_hook"] = solution.get("objective_value")

    result = run_osemosys_from_csv_dir(
        args.csv_dir,
        solver_name=args.solver,
        on_solver_finished=hook,
        materialize_intermediate=False,
    )
    payload = {
        "solver": args.solver,
        "csv_dir": str(args.csv_dir),
        "result": {
            key: result.get(key)
            for key in (
                "objective_value",
                "solver_status",
                "total_demand",
                "total_dispatch",
                "total_unmet",
                "coverage_ratio",
                "solver_threads_used",
            )
        },
        "residuals": residual_report,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
