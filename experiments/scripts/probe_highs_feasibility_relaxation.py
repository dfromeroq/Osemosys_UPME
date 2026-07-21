"""Prueba feasibilityRelaxation de highspy 1.15.1 sobre LPs sintéticos."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import highspy
import numpy as np


def run(lp_path: Path, rhs_penalties: list[float] | None = None) -> dict:
    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    read_status = highs.readModel(str(lp_path))
    lp = highs.getLp()
    row_names = list(lp.row_names_ or [])
    row_lower = [float(v) for v in lp.row_lower_]
    row_upper = [float(v) for v in lp.row_upper_]
    local_rhs = None if rhs_penalties is None else np.asarray(rhs_penalties, dtype=float)
    relax_status = highs.feasibilityRelaxation(1.0, 1.0, 1.0, None, None, local_rhs)
    solution = highs.getSolution()
    row_values = [float(v) for v in solution.row_value]
    violations = []
    for name, value, lower, upper in zip(row_names, row_values, row_lower, row_upper):
        lower_slack = max(0.0, lower - value) if lower != -highspy.kHighsInf else 0.0
        upper_slack = max(0.0, value - upper) if upper != highspy.kHighsInf else 0.0
        if lower_slack or upper_slack:
            violations.append(
                {
                    "row": name,
                    "activity": value,
                    "lower": lower,
                    "upper": upper,
                    "lower_slack": lower_slack,
                    "upper_slack": upper_slack,
                }
            )
    return {
        "read_status": str(read_status),
        "relax_status": str(relax_status),
        "model_status_after_relaxation": str(highs.getModelStatus()),
        "solution_value_valid": bool(solution.value_valid),
        "relaxation_objective": float(highs.getInfo().objective_function_value),
        "column_values": [float(v) for v in solution.col_value],
        "violations": violations,
        "rhs_penalties": rhs_penalties,
    }


def main() -> None:
    base = Path(sys.argv[1] if len(sys.argv) > 1 else "experiments/results/infeasibility-lab")
    result = {
        "highs_version": highspy.Highs().version(),
        "uniform_infeasible": run(base / "infeasible.lp"),
        "uniform_two_conflicts": run(base / "two_independent_conflicts.lp"),
        "protect_demand_relax_capacity": run(base / "infeasible.lp", [100.0, 1.0]),
        "relax_demand_protect_capacity": run(base / "infeasible.lp", [1.0, 100.0]),
    }
    output = base / "highs-1.15.1-feasibility-relaxation.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nJSON: {output.resolve()}")


if __name__ == "__main__":
    main()
