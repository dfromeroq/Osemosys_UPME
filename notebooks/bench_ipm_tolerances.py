#!/usr/bin/env python3
"""Barrido rápido de tolerancias HiGHS (choose, una pasada) sobre LP regional.

Referencia regional: crossover=on ~26s. Cada config choose suele ~5-12s.
"""
from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

import highspy

LP_CANDIDATES = [
    "/tmp/osemosys_highspy_lp_5ecci77i/model.lp",
    "/tmp/osemosys_highspy_lp_mwl30pe4/model.lp",
]

# kkt_* puede tardar >60s; omitido del barrido rápido (ver plan).
SWEEP = [
    ("baseline", {}),
    ("ipm_1e-10", {"ipm_optimality_tolerance": 1e-10}),
    ("ipm_1e-12", {"ipm_optimality_tolerance": 1e-12}),
    ("cross_1e-10", {"start_crossover_tolerance": 1e-10}),
    ("cross_1e-12", {"start_crossover_tolerance": 1e-12}),
]

MAX_TOTAL_SECONDS = 30.0
DUAL_OK_THRESHOLD = 1e-7


def find_lp() -> Path:
    for p in LP_CANDIDATES:
        path = Path(p)
        if path.is_file():
            return path
    raise FileNotFoundError("No LP regional; ejecuta celda 3 del notebook primero.")


def run_case(label: str, extra: dict, lp: Path, threads: int = 16) -> dict:
    opts = dict(extra)
    h = highspy.Highs()
    h.setOptionValue("log_to_console", False)
    h.setOptionValue("output_flag", False)
    h.setOptionValue("solver", "ipm")
    h.setOptionValue("presolve", "on")
    h.setOptionValue("parallel", "on")
    h.setOptionValue("run_crossover", opts.pop("run_crossover", "choose"))
    h.setOptionValue("threads", threads)
    for key, val in opts.items():
        h.setOptionValue(key, val)
    t0 = perf_counter()
    h.readModel(str(lp))
    read_s = perf_counter() - t0
    t1 = perf_counter()
    h.run()
    run_s = perf_counter() - t1
    info = h.getInfo()
    status = str(h.getModelStatus())
    optimal = "kOptimal" in status or "Optimal" in status
    max_di = float(getattr(info, "max_dual_infeasibility", 0.0))
    total_s = read_s + run_s
    return {
        "label": label,
        "status": status,
        "optimal": optimal,
        "objective": float(getattr(info, "objective_function_value", 0.0)),
        "max_pi": float(getattr(info, "max_primal_infeasibility", 0.0)),
        "max_di": max_di,
        "dual_ok": max_di < DUAL_OK_THRESHOLD,
        "read_s": read_s,
        "run_s": run_s,
        "total_s": total_s,
        "extra": dict(extra),
        "winner": optimal and max_di < DUAL_OK_THRESHOLD and total_s <= MAX_TOTAL_SECONDS,
    }


def main() -> int:
    lp = find_lp()
    print(f"LP: {lp} ({lp.stat().st_size / 1e6:.1f} MB)")
    print(f"Criterio: kOptimal + max_di<{DUAL_OK_THRESHOLD} + total<={MAX_TOTAL_SECONDS}s\n")
    winners: list[dict] = []
    for label, extra in SWEEP:
        row = run_case(label, extra, lp)
        print(
            f"{row['label']:14} optimal={row['optimal']} "
            f"obj={row['objective']:.2f} max_di={row['max_di']:.2e} "
            f"run={row['run_s']:.1f}s total={row['total_s']:.1f}s "
            f"winner={row['winner']}"
        )
        if row["winner"]:
            winners.append(row)
    print()
    if winners:
        w = min(winners, key=lambda r: r["total_s"])
        print(f"WINNER: {w['label']} extra={w['extra']} total={w['total_s']:.1f}s")
        return 0
    print("NO_WINNER: usar fallback retry crossover=on solo si Unknown")
    return 1


if __name__ == "__main__":
    sys.exit(main())
