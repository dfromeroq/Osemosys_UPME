"""Barrido de OMP/OPENBLAS threads en Docker worker (invocado desde host)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CONTAINER = "osemosys-simulation-worker-1"
LP_PATH = "/app/tmp/benchmark/model.lp"
OUT_DIR = Path(__file__).resolve().parents[1] / "tmp" / "benchmark" / "threads_sweep"

# Resultados previos (no re-ejecutar)
KNOWN = {
    1: {"run_seconds": 218.52, "highs_run_time_reported": 218.49, "presolve_s": 145.9},
    4: {"run_seconds": 186.52, "highs_run_time_reported": 186.49, "presolve_s": 114.4},
}

TO_RUN = [2, 3, 6, 8]


def run_one(threads: int) -> dict:
    label = f"omp{threads}"
    json_out = f"/app/tmp/benchmark/threads_sweep/{label}.json"
    log_file = f"/app/tmp/benchmark/threads_sweep/{label}.txt"

    cmd = [
        "docker",
        "exec",
        "-e",
        f"OMP_NUM_THREADS={threads}",
        "-e",
        f"OPENBLAS_NUM_THREADS={threads}",
        "-e",
        f"MKL_NUM_THREADS={threads}",
        CONTAINER,
        "sh",
        "-c",
        (
            f"mkdir -p /app/tmp/benchmark/threads_sweep && "
            f"python scripts/benchmark_highs_lp.py --lp {LP_PATH} --run-label {label} "
            f"--log-file {log_file} --json-out {json_out}"
        ),
    ]

    print(f"\n>>> OMP={threads} ...", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        print(stderr, file=sys.stderr)
        raise RuntimeError(f"Run omp={threads} failed (exit {proc.returncode})")

    run_s = _parse_float(stdout, r"h\.run\(\):\s+([\d.]+)")
    total_s = _parse_float(stdout, r"Total:\s+([\d.]+)")
    highs_log_s = _parse_float(stdout, r"HiGHS run time \(log\):\s+([\d.]+)")
    presolve_s = _parse_float(stdout, r"Presolve \(log\):\s+([\d.]+)")

    return {
        "threads": threads,
        "run_seconds": run_s,
        "total_seconds": total_s,
        "highs_run_time_reported": highs_log_s,
        "presolve_s": presolve_s,
        "stdout_tail": "\n".join(stdout.strip().splitlines()[-8:]),
    }


def _parse_float(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for t, data in sorted(KNOWN.items()):
        results.append({"threads": t, "source": "previous_benchmark", **data})

    for threads in TO_RUN:
        try:
            row = run_one(threads)
            row["source"] = "sweep"
            results.append(row)
        except Exception as exc:
            results.append({"threads": threads, "source": "sweep", "error": str(exc)})

    results.sort(key=lambda r: r.get("run_seconds") or float("inf"))

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "container_cpus": 4,
        "lp_path": LP_PATH,
        "runs": sorted(
            [r for r in results if "error" not in r],
            key=lambda r: r.get("run_seconds") or float("inf"),
        ),
        "best": None,
    }
    valid = [r for r in summary["runs"] if r.get("run_seconds") is not None]
    if valid:
        summary["best"] = min(valid, key=lambda r: r["run_seconds"])

    out_path = OUT_DIR / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n=== RESUMEN (ordenado por h.run()) ===")
    print(f"{'OMP':>4}  {'h.run()':>8}  {'presolve':>9}  {'fuente':>8}")
    for r in sorted(summary["runs"], key=lambda x: x["threads"]):
        rs = r.get("run_seconds")
        ps = r.get("presolve_s")
        src = r.get("source", "?")[:8]
        rs_s = f"{rs:.1f}s" if rs else "ERR"
        ps_s = f"{ps:.1f}s" if ps else "—"
        mark = " <-- mejor" if summary["best"] and r.get("threads") == summary["best"].get("threads") else ""
        print(f"{r['threads']:>4}  {rs_s:>8}  {ps_s:>9}  {src:>8}{mark}")

    print(f"\nJSON: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
