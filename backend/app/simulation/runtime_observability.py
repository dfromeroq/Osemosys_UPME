"""Lightweight runtime snapshots for simulation jobs."""

from __future__ import annotations

import os
import resource
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_ENV_KEYS = (
    "APP_DEPLOY_ENV",
    "APP_GIT_BRANCH",
    "APP_GIT_SHA",
    "COMPOSE_PROJECT_NAME",
    "HIGHS_BUILD_FROM_SOURCE",
    "HIGHS_ENABLE_HIPO",
    "HIGHS_GIT_REF",
    "HOSTNAME",
    "MKL_NUM_THREADS",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "OSEMOSYS_CONSTRAINT_DIAGNOSTICS",
    "OSEMOSYS_FAST_DATAPORTAL",
    "OSEMOSYS_SELECTIVE_SOLUTION_MAP",
    "SIM_MAX_CONCURRENCY",
    "SIM_SOLVER_HIGHS_DIRECT",
    "SIM_SOLVER_THREADS",
    "SIM_TOTAL_WEIGHT_LIMIT",
    "SIM_USER_ACTIVE_LIMIT",
    "SIM_WEIGHT_NATIONAL",
    "SIM_WEIGHT_REGIONAL",
    "SIM_WORKER_REPLICAS",
)


def _read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _read_int(path: str) -> int | None:
    raw = _read_text(path)
    if raw is None or raw in ("", "max"):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _read_proc_status() -> dict[str, str]:
    raw = _read_text("/proc/self/status")
    if not raw:
        return {}
    data: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _status_kb(status: dict[str, str], key: str) -> int | None:
    raw = status.get(key)
    if not raw:
        return None
    try:
        return int(raw.split()[0])
    except (IndexError, ValueError):
        return None


def _kb_to_mb(value: int | None) -> float | None:
    if value is None:
        return None
    return round(value / 1024, 3)


def _bytes_to_mb(value: int | None) -> float | None:
    if value is None:
        return None
    return round(value / (1024 * 1024), 3)


def _cpu_quota() -> dict[str, Any]:
    raw = _read_text("/sys/fs/cgroup/cpu.max")
    if not raw:
        return {}
    parts = raw.split()
    if len(parts) < 2:
        return {"raw": raw}
    quota_raw, period_raw = parts[0], parts[1]
    result: dict[str, Any] = {"raw": raw}
    try:
        period = int(period_raw)
        result["period_us"] = period
        if quota_raw != "max":
            quota = int(quota_raw)
            result["quota_us"] = quota
            if period > 0:
                result["quota_cpus"] = round(quota / period, 3)
    except ValueError:
        pass
    return result


def _cpuset_effective() -> str | None:
    return _read_text("/sys/fs/cgroup/cpuset.cpus.effective") or _read_text(
        "/sys/fs/cgroup/cpuset.cpus"
    )


def _affinity_count() -> int | None:
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return None


def _open_fd_count() -> int | None:
    try:
        return len(os.listdir("/proc/self/fd"))
    except OSError:
        return None


def _memory_context() -> dict[str, Any]:
    mem_current = _read_int("/sys/fs/cgroup/memory.current")
    mem_max = _read_int("/sys/fs/cgroup/memory.max")
    swap_current = _read_int("/sys/fs/cgroup/memory.swap.current")
    swap_max = _read_int("/sys/fs/cgroup/memory.swap.max")
    return {
        "cgroup_memory_current_mb": _bytes_to_mb(mem_current),
        "cgroup_memory_max_mb": _bytes_to_mb(mem_max),
        "cgroup_swap_current_mb": _bytes_to_mb(swap_current),
        "cgroup_swap_max_mb": _bytes_to_mb(swap_max),
    }


def collect_runtime_context() -> dict[str, Any]:
    """Collect stable-ish runtime context that helps compare two executions."""
    return {
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "python": sys.version.split()[0],
        "env": {key: os.environ[key] for key in _ENV_KEYS if key in os.environ},
        "cpu": {
            "os_cpu_count": os.cpu_count(),
            "affinity_count": _affinity_count(),
            "cgroup": _cpu_quota(),
            "cpuset_effective": _cpuset_effective(),
        },
        "memory": _memory_context(),
    }


@dataclass
class ResourceTrace:
    """Per-process resource samples keyed by simulation stage transitions."""

    start_wall: float = field(default_factory=time.monotonic)
    _last_wall: float = field(default_factory=time.monotonic)
    _last_cpu: float = field(default_factory=time.process_time)
    samples: list[dict[str, Any]] = field(default_factory=list)

    def sample(self, stage: str) -> list[dict[str, Any]]:
        now_wall = time.monotonic()
        now_cpu = time.process_time()
        wall_delta = max(0.0, now_wall - self._last_wall)
        cpu_delta = max(0.0, now_cpu - self._last_cpu)
        status = _read_proc_status()
        ru = resource.getrusage(resource.RUSAGE_SELF)
        sample = {
            "stage": stage,
            "elapsed_seconds": round(now_wall - self.start_wall, 3),
            "delta_seconds": round(wall_delta, 3),
            "process_cpu_percent": round((cpu_delta / wall_delta) * 100, 2)
            if wall_delta > 0
            else 0.0,
            "rss_mb": _kb_to_mb(_status_kb(status, "VmRSS")),
            "vms_mb": _kb_to_mb(_status_kb(status, "VmSize")),
            "peak_rss_mb": _kb_to_mb(int(ru.ru_maxrss)),
            "threads": int(status.get("Threads", "0").split()[0] or 0),
            "open_fds": _open_fd_count(),
            **_memory_context(),
        }
        self._last_wall = now_wall
        self._last_cpu = now_cpu
        self.samples.append(sample)
        return [dict(item) for item in self.samples]
