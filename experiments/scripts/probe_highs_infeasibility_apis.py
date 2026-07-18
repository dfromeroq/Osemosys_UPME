"""Probe reproducible de IIS y rays en highspy 1.15.1 con LPs mínimos.

No importa código de la aplicación ni modifica escenarios. Escribe LPs y un JSON
con respuestas crudas normalizadas para poder comparar versiones de HiGHS.
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Any

import highspy


IIS_STRATEGIES = (0, 1, 2, 3, 4, 6, 8, 10, 12, 16, 18)


MODELS = {
    "infeasible": """Minimize
 obj: x
Subject To
 demand_floor: x >= 1
 capacity_ceiling: x <= 0
Bounds
 x free
End
""",
    "infeasible_with_redundant_row": """Minimize
 obj: x
Subject To
 demand_floor: x >= 1
 capacity_ceiling: x <= 0
 irrelevant_ceiling: x <= 10
Bounds
 x free
End
""",
    "two_independent_conflicts": """Minimize
 obj: x + y
Subject To
 x_floor: x >= 1
 x_ceiling: x <= 0
 y_floor: y >= 2
 y_ceiling: y <= 1
Bounds
 x free
 y free
End
""",
    "variable_bound_infeasible": """Minimize
 obj: x
Subject To
 anchor: x = 0
Bounds
 1 <= x <= 0
End
""",
    "feasible": """Minimize
 obj: x
Subject To
 demand_floor: x >= 1
 capacity_ceiling: x <= 2
Bounds
 x free
End
""",
    "unbounded": """Minimize
 obj: - x
Subject To
 nonnegative_floor: x >= 0
Bounds
 x free
End
""",
}


def enum_text(value: Any) -> str:
    return str(value)


def iis_payload(iis: Any, row_names: list[str], col_names: list[str]) -> dict[str, Any]:
    row_indices = [int(v) for v in list(getattr(iis, "row_index_", []) or [])]
    col_indices = [int(v) for v in list(getattr(iis, "col_index_", []) or [])]
    info = getattr(iis, "info_", None)
    info_payload = {
        name: getattr(info, name, None)
        for name in (
            "num_lp_solved",
            "min_simplex_time",
            "max_simplex_time",
            "sum_simplex_times",
            "min_simplex_iteration_count",
            "max_simplex_iteration_count",
            "sum_simplex_iteration_counts",
        )
    }
    return {
        "valid": bool(getattr(iis, "valid_", False)),
        "strategy": enum_text(getattr(iis, "strategy_", None)),
        "status": enum_text(getattr(iis, "status_", None)),
        "info": info_payload,
        "row_indices": row_indices,
        "row_names": [row_names[i] if 0 <= i < len(row_names) else f"<idx:{i}>" for i in row_indices],
        "row_bound": [int(v) for v in list(getattr(iis, "row_bound_", []) or [])],
        "row_status": [enum_text(v) for v in list(getattr(iis, "row_status_", []) or [])],
        "col_indices": col_indices,
        "col_names": [col_names[i] if 0 <= i < len(col_names) else f"<idx:{i}>" for i in col_indices],
        "col_bound": [int(v) for v in list(getattr(iis, "col_bound_", []) or [])],
        "col_status": [enum_text(v) for v in list(getattr(iis, "col_status_", []) or [])],
    }


def run_probe(lp_path: Path, strategy: int) -> dict[str, Any]:
    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    option_status = highs.setOptionValue("iis_strategy", strategy)
    read_status = highs.readModel(str(lp_path))
    run_status = highs.run()
    model_status = highs.getModelStatus()
    lp = highs.getLp()
    row_names = list(lp.row_names_ or [])
    col_names = list(lp.col_names_ or [])

    dual_exist_status, dual_exists = highs.getDualRayExist()
    dual_status, dual_has_ray, dual_ray = highs.getDualRay()
    primal_exist_status, primal_exists = highs.getPrimalRayExist()
    primal_status, primal_has_ray, primal_ray = highs.getPrimalRay()
    iis_status, iis = highs.getIis()

    return {
        "iis_strategy_requested": strategy,
        "iis_strategy_option_status": enum_text(option_status),
        "read_status": enum_text(read_status),
        "run_status": enum_text(run_status),
        "model_status": enum_text(model_status),
        "row_names": row_names,
        "col_names": col_names,
        "dual_ray_exist": {
            "status": enum_text(dual_exist_status),
            "exists": bool(dual_exists),
        },
        "dual_ray": {
            "status": enum_text(dual_status),
            "exists": bool(dual_has_ray),
            "values": [float(v) for v in dual_ray],
        },
        "primal_ray_exist": {
            "status": enum_text(primal_exist_status),
            "exists": bool(primal_exists),
        },
        "primal_ray": {
            "status": enum_text(primal_status),
            "exists": bool(primal_has_ray),
            "values": [float(v) for v in primal_ray],
        },
        "iis_call_status": enum_text(iis_status),
        "iis": iis_payload(iis, row_names, col_names),
    }


def main() -> None:
    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "experiments/results/infeasibility-lab")
    output_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "python": sys.version,
        "platform": platform.platform(),
        "highs_version": highspy.Highs().version(),
        "models": {},
    }
    for model_name, text in MODELS.items():
        lp_path = output_dir / f"{model_name}.lp"
        lp_path.write_text(text, encoding="utf-8")
        result["models"][model_name] = {
            str(strategy): run_probe(lp_path, strategy) for strategy in IIS_STRATEGIES
        }

    json_path = output_dir / "highs-1.15.1-api-probe.json"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nJSON: {json_path.resolve()}")


if __name__ == "__main__":
    main()
