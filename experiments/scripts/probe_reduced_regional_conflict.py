#!/usr/bin/env python
"""Certifica el conflicto mínimo extraído de un dual ray regional."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.simulation.core.infeasibility_analysis import (  # noqa: E402
    try_compute_dual_ray,
    try_compute_iis,
    try_feasibility_relaxation,
)

out = ROOT / "tmp" / "infeasibility-benchmarks" / "scenario-37-20260717" / "artifacts"
out.mkdir(parents=True, exist_ok=True)
lower = 117.066115414
upper = 2.45769813
lp = out / "reduced_OR_MINBAG_2050.lp"
lp.write_text(
    f"""Minimize
 obj: activity
Subject To
 c_l_TotalAnnualTechnologyActivityLowerlimit(RE1_OR_MINBAG_2050)_: activity >= {lower:.12g}
 c_u_TotalAnnualTechnologyActivityUpperlimit(RE1_OR_MINBAG_2050)_: activity <= {upper:.12g}
Bounds
 activity free
End
""",
    encoding="utf-8",
)
result = {
    "source": {
        "region": "RE1",
        "technology": "OR_MINBAG",
        "year": 2050,
        "lower_parameter": "TotalTechnologyAnnualActivityLowerLimit",
        "lower_value": lower,
        "upper_parameter": "TotalTechnologyAnnualActivityUpperLimit",
        "upper_value": upper,
        "required_change": lower - upper,
    },
    "dual_ray": asdict(try_compute_dual_ray(None, "highs", lp_path=lp)),
    "iis": asdict(try_compute_iis(None, "highs", lp_path=lp)),
    "feasibility_relaxation": asdict(try_feasibility_relaxation(None, "highs", lp_path=lp)),
}
path = out / "reduced_OR_MINBAG_2050_diagnostics.json"
path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
