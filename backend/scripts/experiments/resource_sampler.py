#!/usr/bin/env python3
"""Sampler de recursos para experimentos OSeMOSYS.

Puede ejecutarse desde el host con Docker disponible o dentro de un contenedor.
Escribe CSV append-only con métricas de host/proceso/contenedores.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

FIELDNAMES = [
    "ts",
    "scope",
    "name",
    "cpu_percent",
    "cpu_cores",
    "mem_used_bytes",
    "mem_limit_bytes",
    "mem_percent",
    "pids",
    "host_mem_total_bytes",
    "host_mem_available_bytes",
    "host_swap_total_bytes",
    "host_swap_free_bytes",
    "disk_free_bytes",
]


def _parse_bytes(value: str) -> float:
    value = (value or "").strip()
    if not value:
        return 0.0
    number = ""
    suffix = ""
    for ch in value:
        if ch.isdigit() or ch == ".":
            number += ch
        elif not ch.isspace():
            suffix += ch
    try:
        base = float(number)
    except ValueError:
        return 0.0
    suffix = suffix.lower()
    factors = {
        "b": 1,
        "kb": 1000,
        "kib": 1024,
        "mb": 1000**2,
        "mib": 1024**2,
        "gb": 1000**3,
        "gib": 1024**3,
        "tb": 1000**4,
        "tib": 1024**4,
    }
    return base * factors.get(suffix, 1)


def _host_mem() -> dict[str, int]:
    data: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            parts = raw.strip().split()
            if parts:
                data[key] = int(parts[0]) * 1024
    except Exception:
        return {}
    return {
        "host_mem_total_bytes": data.get("MemTotal", 0),
        "host_mem_available_bytes": data.get("MemAvailable", 0),
        "host_swap_total_bytes": data.get("SwapTotal", 0),
        "host_swap_free_bytes": data.get("SwapFree", 0),
    }


def _proc_sample(pid: int) -> dict[str, object]:
    status: dict[str, str] = {}
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                status[k] = v.strip()
    except Exception:
        return {}
    rss_kb = int((status.get("VmRSS", "0 kB").split() or ["0"])[0])
    hwm_kb = int((status.get("VmHWM", "0 kB").split() or ["0"])[0])
    threads = int(status.get("Threads", "0") or 0)
    return {
        "scope": "process",
        "name": str(pid),
        "mem_used_bytes": rss_kb * 1024,
        "mem_limit_bytes": hwm_kb * 1024,
        "pids": threads,
    }


def _docker_stats(project: str, services: list[str]) -> list[dict[str, object]]:
    if not shutil.which("docker"):
        return []
    try:
        ps_cmd = ["docker", "ps", "--format", "{{json .}}"]
        out = subprocess.check_output(ps_cmd, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    names: list[str] = []
    for line in out.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = str(item.get("Names") or item.get("Names", ""))
        if project and not name.startswith(f"{project}-"):
            continue
        if services and not any(f"-{svc}-" in name or name.endswith(f"-{svc}-1") for svc in services):
            continue
        names.append(name)
    if not names:
        return []
    try:
        fmt = "{{json .}}"
        out = subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format", fmt, *names],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    rows: list[dict[str, object]] = []
    for line in out.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        mem_usage = str(item.get("MemUsage", ""))
        used_s, _, limit_s = mem_usage.partition("/")
        cpu_percent = float(str(item.get("CPUPerc", "0")).replace("%", "") or 0)
        mem_percent = float(str(item.get("MemPerc", "0")).replace("%", "") or 0)
        pids = int(str(item.get("PIDs", "0") or "0"))
        rows.append(
            {
                "scope": "docker",
                "name": item.get("Name") or item.get("Container"),
                "cpu_percent": cpu_percent,
                "cpu_cores": cpu_percent / 100.0,
                "mem_used_bytes": int(_parse_bytes(used_s)),
                "mem_limit_bytes": int(_parse_bytes(limit_s)),
                "mem_percent": mem_percent,
                "pids": pids,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Samplea recursos host/proceso/docker a CSV")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--duration", type=float, default=0.0, help="0 = infinito")
    parser.add_argument("--project", default="osemosys")
    parser.add_argument("--services", default="api,simulation-worker,db,redis,frontend")
    parser.add_argument("--pid", type=int, default=os.getpid())
    args = parser.parse_args()

    services = [s.strip() for s in args.services.split(",") if s.strip()]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_header = not args.out.exists()
    start = time.time()
    with args.out.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        while True:
            ts = time.time()
            base = {"ts": ts, **_host_mem()}
            try:
                base["disk_free_bytes"] = shutil.disk_usage(".").free
            except Exception:
                base["disk_free_bytes"] = 0
            rows = []
            proc = _proc_sample(args.pid)
            if proc:
                rows.append({**base, **proc})
            rows.extend({**base, **row} for row in _docker_stats(args.project, services))
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
            f.flush()
            if args.duration and (time.time() - start) >= args.duration:
                break
            time.sleep(max(0.1, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
