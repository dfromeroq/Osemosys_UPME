#!/usr/bin/env python
"""Intento acotado de Farkas ray sin presolve; no modifica el LP de entrada."""
from __future__ import annotations

import os
import threading
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
LP = ROOT / "tmp/infeasibility-benchmarks/scenario-36-20260717/artifacts/baseline.lp"
LIMIT = 12 * 1024**3
stop = threading.Event()


def watch() -> None:
    proc = psutil.Process()
    while not stop.wait(1):
        rss = proc.memory_info().rss
        print(f"rss_gib={rss / 1024**3:.3f}", flush=True)
        if rss > LIMIT:
            print("WATCHDOG: 12 GiB exceeded", flush=True)
            os._exit(137)


threading.Thread(target=watch, daemon=True).start()
try:
    import highspy

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", True)
    highs.setOptionValue("solver", "simplex")
    highs.setOptionValue("presolve", "off")
    highs.setOptionValue("time_limit", 90.0)
    print("read", highs.readModel(str(LP)), flush=True)
    print("run", highs.run(), flush=True)
    print("model", highs.getModelStatus(), flush=True)
    print("ray_exist", highs.getDualRayExist(), flush=True)
    print("ray", highs.getDualRay(), flush=True)
finally:
    stop.set()
