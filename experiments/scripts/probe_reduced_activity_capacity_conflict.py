#!/usr/bin/env python
"""Certifica una contradicción de actividad mínima vs capacidad disponible."""
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

out = ROOT / "tmp/infeasibility-benchmarks/scenario-36-20260717/artifacts"
out.mkdir(parents=True, exist_ok=True)
region, technology, year = "RE1", "AN_DEMRESNGSCKN_LOW_URB", 2025
minimum = 4.25975009764
residual = 3.938600997713
investment_limits = {2022: 0.0, 2023: 0.0, 2024: 0.0, 2025: 0.0696922}
maximum_activity = residual + sum(investment_limits.values())
lp = out / "reduced_activity_capacity_2025.lp"
new_vars = [f"n_{investment_year}" for investment_year in investment_limits]
capacity_terms = " - ".join(new_vars)
upper_rows = "\n".join(
    " c_u_TotalAnnualMaxNewCapacityConstraint"
    f"({region}_{technology}_{investment_year})_: n_{investment_year} <= {limit:.14g}"
    for investment_year, limit in investment_limits.items()
)
lp.write_text(
    f"""Minimize
 obj: activity
Subject To
 c_l_TotalAnnualTechnologyActivityLowerlimit({region}_{technology}_{year})_: activity >= {minimum:.14g}
 c_u_ConstraintCapacity({region}_TS_0_{technology}_{year})_: activity - {capacity_terms} <= {residual:.14g}
{upper_rows}
Bounds
 activity free
 n_2022 >= 0
 n_2023 >= 0
 n_2024 >= 0
 n_2025 >= 0
End
""",
    encoding="utf-8",
)
result = {
    "source": {
        "region": region,
        "technology": technology,
        "year": year,
        "annual_activity_minimum": minimum,
        "residual_capacity": residual,
        "maximum_new_capacity_by_year": investment_limits,
        "maximum_activity_from_capacity": maximum_activity,
        "required_change": minimum - maximum_activity,
    },
    "dual_ray": asdict(try_compute_dual_ray(None, "highs", lp_path=lp)),
    "iis": asdict(try_compute_iis(None, "highs", lp_path=lp)),
    "feasibility_relaxation": asdict(try_feasibility_relaxation(None, "highs", lp_path=lp)),
}
path = out / "reduced_activity_capacity_2025_diagnostics.json"
path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
