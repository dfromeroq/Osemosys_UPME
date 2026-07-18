#!/usr/bin/env python
"""Subsistema HiGHS rápido/heurístico; nunca se etiqueta como IIS irreducible."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
LP = ROOT / "tmp/infeasibility-benchmarks/scenario-36-20260717/artifacts/baseline.lp"
LIMIT = 12 * 1024**3
stop = threading.Event()


def watch() -> None:
    process = psutil.Process()
    while not stop.wait(1):
        if process.memory_info().rss > LIMIT:
            print("WATCHDOG: 12 GiB exceeded", flush=True)
            os._exit(137)


threading.Thread(target=watch, daemon=True).start()
try:
    import highspy

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    highs.setOptionValue("time_limit", 90.0)
    highs.setOptionValue("iis_time_limit", 90.0)
    highs.setOptionValue("iis_strategy", highspy.IisStrategy.kIisStrategyFromLp)
    read = highs.readModel(str(LP))
    run = highs.run()
    status = highs.getModelStatus()
    raw = highs.getIis()
    iis = raw[1] if isinstance(raw, tuple) and len(raw) > 1 else raw
    lp = highs.getLp()
    names = list(lp.row_names_ or [])
    rows = [names[int(index)] for index in list(getattr(iis, "row_index_", []) or [])]
    result = {
        "evidence_level": "HEURISTIC",
        "read_status": str(read),
        "run_status": str(run),
        "model_status": str(status),
        "get_iis_status": str(raw[0]) if isinstance(raw, tuple) else None,
        "row_count": len(rows),
        "rows": rows[:200],
        "irreducible": False,
    }
    output = LP.parent / "fast_conflict_subsystem.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
finally:
    stop.set()
