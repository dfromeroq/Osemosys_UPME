#!/usr/bin/env python3
"""Runner local de benchmarks OSeMOSYS con historial JSONL/CSV.

Ejecutar dentro del contenedor API o en un entorno con DATABASE_URL válido:

  python scripts/experiments/run_benchmark.py --mode csv-dir --csv-dir /app/tmp/foo --solver highs --label foo
  SIMULATION_MODE=sync python scripts/experiments/run_benchmark.py --mode scenario --scenario-id 1 --solver highs
  SIMULATION_MODE=sync python scripts/experiments/run_benchmark.py --mode excel --excel /app/tmp/model.xlsx --solver highs
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import Scenario, SimulationJob, User  # noqa: E402
from app.services.official_import_service import OfficialImportService  # noqa: E402
from app.services.scenario_service import ScenarioService  # noqa: E402
from app.services.simulation_service import SimulationService  # noqa: E402
from app.simulation.osemosys_core import run_osemosys_from_csv_dir  # noqa: E402

SUMMARY_FIELDS = [
    "label",
    "run_index",
    "mode",
    "solver",
    "simulation_type",
    "status",
    "wall_seconds",
    "objective_value",
    "solver_status",
    "total_demand",
    "total_dispatch",
    "total_unmet",
    "coverage_ratio",
    "solver_backend",
    "solver_threads_used",
    "solver_threads_configured",
    "solver_run_seconds",
    "create_instance_seconds",
    "data_processing_seconds",
    "results_processing_seconds",
    "peak_rss_mb",
    "max_cpu_cores",
    "job_id",
    "scenario_id",
    "error",
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_proc(pid: int) -> tuple[float, int, int]:
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
    cpu_seconds = (int(stat[13]) + int(stat[14])) / ticks
    rss_bytes = 0
    threads = 0
    for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            rss_bytes = int(line.split()[1]) * 1024
        elif line.startswith("Threads:"):
            threads = int(line.split()[1])
    return cpu_seconds, rss_bytes, threads


class ProcessSampler:
    def __init__(self, out: Path, interval: float = 1.0, pid: int | None = None) -> None:
        self.out = out
        self.interval = interval
        self.pid = pid or os.getpid()
        self._stop = threading.Event()
        self.max_rss = 0
        self.max_cpu_cores = 0.0
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _run(self) -> None:
        prev_t = time.time()
        prev_cpu, _, _ = _read_proc(self.pid)
        with self.out.open("w", newline="", encoding="utf-8") as f:
            fieldnames = ["ts", "pid", "cpu_cores", "rss_mb", "threads"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            while not self._stop.is_set():
                time.sleep(self.interval)
                now = time.time()
                try:
                    cpu, rss, threads = _read_proc(self.pid)
                except Exception:
                    continue
                cpu_cores = max(0.0, (cpu - prev_cpu) / max(now - prev_t, 1e-9))
                prev_t, prev_cpu = now, cpu
                rss_mb = rss / 1024 / 1024
                self.max_rss = max(self.max_rss, rss)
                self.max_cpu_cores = max(self.max_cpu_cores, cpu_cores)
                writer.writerow(
                    {"ts": now, "pid": self.pid, "cpu_cores": cpu_cores, "rss_mb": rss_mb, "threads": threads}
                )
                f.flush()


def _write_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _utc(), **event}, ensure_ascii=False, default=str) + "\n")


def _append_summary(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in SUMMARY_FIELDS})


def _result_summary(result: dict[str, Any], timings: dict[str, Any] | None = None) -> dict[str, Any]:
    mt = result.get("model_timings") or timings or {}
    highs_cfg = mt.get("solver_highs_config") if isinstance(mt, dict) else None
    return {
        "objective_value": result.get("objective_value"),
        "solver_status": result.get("solver_status"),
        "total_demand": result.get("total_demand"),
        "total_dispatch": result.get("total_dispatch"),
        "total_unmet": result.get("total_unmet"),
        "coverage_ratio": result.get("coverage_ratio"),
        "solver_backend": mt.get("solver_backend") if isinstance(mt, dict) else None,
        "solver_threads_used": result.get("solver_threads_used"),
        "solver_threads_configured": result.get("solver_threads_configured"),
        "solver_run_seconds": mt.get("solver_run_seconds") or mt.get("solver_seconds") if isinstance(mt, dict) else None,
        "create_instance_seconds": mt.get("create_instance_seconds") if isinstance(mt, dict) else None,
        "data_processing_seconds": mt.get("data_processing_seconds") if isinstance(mt, dict) else None,
        "results_processing_seconds": mt.get("results_processing_seconds") if isinstance(mt, dict) else None,
        "solver_highs_config": highs_cfg,
    }


def _run_csv_dir(args: argparse.Namespace) -> dict[str, Any]:
    if not args.csv_dir:
        raise ValueError("--csv-dir es requerido para mode=csv-dir")
    return run_osemosys_from_csv_dir(args.csv_dir, solver_name=args.solver)


def _get_seed_user(db, username: str) -> User:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        raise RuntimeError(f"Usuario {username!r} no existe. Ejecuta scripts/seed.py")
    return user


def _run_scenario(args: argparse.Namespace) -> dict[str, Any]:
    if not args.scenario_id:
        raise ValueError("--scenario-id es requerido para mode=scenario")
    with SessionLocal() as db:
        user = _get_seed_user(db, args.seed_user)
        payload = SimulationService.submit(db, current_user=user, scenario_id=args.scenario_id, solver_name=args.solver)
        job_id = int(payload["id"])
        job = db.get(SimulationJob, job_id)
        if job is None or job.status != "SUCCEEDED":
            raise RuntimeError(f"Job {job_id} terminó en estado {getattr(job, 'status', None)}: {getattr(job, 'error_message', None)}")
        return SimulationService.get_result(db, current_user=user, job_id=job_id)


def _run_excel(args: argparse.Namespace) -> dict[str, Any]:
    if not args.excel:
        raise ValueError("--excel es requerido para mode=excel")
    excel = Path(args.excel)
    with SessionLocal() as db:
        user = _get_seed_user(db, args.seed_user)
        name = args.scenario_name or f"BENCH_{excel.stem[:35]}_{datetime.now():%Y%m%d_%H%M%S}"
        created = ScenarioService.create(
            db,
            current_user=user,
            name=name,
            description="Benchmark importado desde Excel",
            edit_policy="OWNER_ONLY",
            is_template=False,
            simulation_type=args.simulation_type,
            skip_populate_defaults=True,
        )
        sid = int(created["id"])
        OfficialImportService.import_xlsm(
            db,
            filename=excel.name,
            content=excel.read_bytes(),
            imported_by=user.username,
            selected_sheet_name=args.sheet,
            scenario_id_override=sid,
            use_default_scenario=False,
            collapse_timeslices=not args.preserve_timeslices,
        )
        payload = SimulationService.submit(db, current_user=user, scenario_id=sid, solver_name=args.solver)
        job_id = int(payload["id"])
        job = db.get(SimulationJob, job_id)
        if job is None or job.status != "SUCCEEDED":
            raise RuntimeError(f"Job {job_id} terminó en estado {getattr(job, 'status', None)}: {getattr(job, 'error_message', None)}")
        return SimulationService.get_result(db, current_user=user, job_id=job_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Runner local de benchmarks OSeMOSYS")
    parser.add_argument("--mode", choices=["csv-dir", "scenario", "excel"], required=True)
    parser.add_argument("--label", default="benchmark")
    parser.add_argument("--solver", choices=["highs", "glpk", "gurobi"], default="highs")
    parser.add_argument("--simulation-type", choices=["NATIONAL", "REGIONAL"], default="NATIONAL")
    parser.add_argument("--csv-dir")
    parser.add_argument("--scenario-id", type=int)
    parser.add_argument("--excel")
    parser.add_argument("--sheet", default="Parameters")
    parser.add_argument("--scenario-name")
    parser.add_argument("--preserve-timeslices", action="store_true")
    parser.add_argument("--seed-user", default="seed")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--out-root", type=Path, default=Path("experiments/runs"))
    parser.add_argument("--sample-interval", type=float, default=1.0)
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.out_root / f"{stamp}_{args.label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": _utc(),
        "label": args.label,
        "mode": args.mode,
        "solver": args.solver,
        "simulation_type": args.simulation_type,
        "settings": get_settings().model_dump(mode="json"),
        "env_subset": {k: os.environ.get(k) for k in sorted(os.environ) if k.startswith(("SIM_", "OSEMOSYS_", "OMP_", "OPENBLAS_", "MKL_"))},
    }
    try:
        import subprocess
        manifest["git_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        manifest["git_branch"] = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        manifest["git_commit"] = os.environ.get("APP_GIT_SHA", "")
        manifest["git_branch"] = os.environ.get("APP_GIT_BRANCH", "")
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    funcs = {"csv-dir": _run_csv_dir, "scenario": _run_scenario, "excel": _run_excel}
    status = 0
    for i in range(1, args.repetitions + 1):
        _write_jsonl(run_dir / "experiment.jsonl", {"event": "run_start", "run_index": i})
        sampler = ProcessSampler(run_dir / f"resources_run_{i}.csv", interval=args.sample_interval)
        sampler.start()
        start = time.perf_counter()
        row: dict[str, Any] = {
            "label": args.label,
            "run_index": i,
            "mode": args.mode,
            "solver": args.solver,
            "simulation_type": args.simulation_type,
        }
        try:
            result = funcs[args.mode](args)
            wall = time.perf_counter() - start
            summary = _result_summary(result)
            out_json = run_dir / f"result_run_{i}.json"
            out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            row.update(summary)
            row.update({"status": "SUCCEEDED", "wall_seconds": wall, "peak_rss_mb": sampler.max_rss / 1024 / 1024, "max_cpu_cores": sampler.max_cpu_cores, "job_id": result.get("job_id"), "scenario_id": result.get("scenario_id")})
            _write_jsonl(run_dir / "experiment.jsonl", {"event": "run_finished", "run_index": i, **row})
        except Exception as exc:
            wall = time.perf_counter() - start
            row.update({"status": "FAILED", "wall_seconds": wall, "error": repr(exc), "peak_rss_mb": sampler.max_rss / 1024 / 1024, "max_cpu_cores": sampler.max_cpu_cores})
            _write_jsonl(run_dir / "experiment.jsonl", {"event": "run_failed", "run_index": i, **row})
            status = 1
        finally:
            sampler.stop()
            _append_summary(run_dir / "summary.csv", row)
    print(run_dir)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
