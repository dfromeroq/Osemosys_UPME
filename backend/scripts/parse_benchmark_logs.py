"""Agrega resultados de logs HiGHS del benchmark."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.benchmark_highs_lp import parse_highs_log  # noqa: E402

RUNS = [
    ("A local (Windows)", PROJECT_ROOT / "tmp/benchmark/logs/local.txt", "1.13.1", None),
    ("B docker (OMP=4)", PROJECT_ROOT / "tmp/benchmark/logs/docker.txt", "1.14.0", "4"),
    ("C docker (OMP=1)", PROJECT_ROOT / "tmp/benchmark/logs/docker-omp1.txt", "1.14.0", "1"),
]


def main() -> int:
    rows = []
    for label, log_path, version, omp in RUNS:
        p = parse_highs_log(log_path)
        rows.append(
            {
                "run": label,
                "highs_version": version,
                "omp_num_threads": omp,
                "lp_rows": int(p["lp_rows"]) if p.get("lp_rows") else None,
                "presolve_s": round(p["presolve_seconds"], 1) if p.get("presolve_seconds") else None,
                "simplex_s": round(p["simplex_seconds"], 1) if p.get("simplex_seconds") else None,
                "postsolve_s": round(p["postsolve_seconds"], 1) if p.get("postsolve_seconds") else None,
                "total_s": round(p["highs_run_time_reported"], 1) if p.get("highs_run_time_reported") else None,
                "simplex_iterations": int(p["simplex_iterations"]) if p.get("simplex_iterations") else None,
            }
        )
    out = PROJECT_ROOT / "tmp/benchmark/results/summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
