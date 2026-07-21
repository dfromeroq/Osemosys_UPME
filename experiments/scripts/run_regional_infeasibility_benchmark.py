#!/usr/bin/env python
"""Benchmark local y acotado: Excel SAND -> CSV -> LP -> certificación HiGHS.

No escribe en BD, Docker, staging ni en el Excel de origen. Los datos de trabajo
viven en tmp/infeasibility-benchmarks/<label>. El watchdog finaliza el proceso
si RSS excede el límite configurado, incluso durante una llamada nativa HiGHS.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Watchdog:
    def __init__(self, limit_gib: float, report: dict[str, Any]) -> None:
        self.limit_bytes = int(limit_gib * 1024**3)
        self.report = report
        self.stop = threading.Event()
        self.process = psutil.Process()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=3)

    def _run(self) -> None:
        peak = 0
        while not self.stop.wait(1):
            try:
                rss = self.process.memory_info().rss
            except psutil.Error:
                return
            peak = max(peak, rss)
            self.report["peak_rss_bytes"] = peak
            self.report["peak_rss_gib"] = round(peak / 1024**3, 3)
            if rss > self.limit_bytes:
                self.report["watchdog_abort"] = {
                    "at": now(),
                    "rss_gib": round(rss / 1024**3, 3),
                    "limit_gib": round(self.limit_bytes / 1024**3, 3),
                }
                print("WATCHDOG: RSS limit exceeded; terminating process", flush=True)
                os._exit(137)


def write_report(path: Path, report: dict[str, Any]) -> None:
    report["updated_at"] = now()
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def base_report(excel: Path, label: str, max_gib: float) -> dict[str, Any]:
    return {
        "label": label,
        "source_excel": str(excel),
        "source_excel_sha256": sha256(excel),
        "source_excel_bytes": excel.stat().st_size,
        "started_at": now(),
        "limits": {"rss_gib_hard_stop": max_gib, "global_timeout_seconds": 2700},
        "phases": {},
    }


def phase(report: dict[str, Any], name: str, fn):
    started = time.perf_counter()
    try:
        value = fn()
        report["phases"][name] = {"status": "PASS", "seconds": round(time.perf_counter() - started, 3), **(value or {})}
    except Exception as exc:
        report["phases"][name] = {"status": "ERROR", "seconds": round(time.perf_counter() - started, 3), "error": repr(exc)}
        raise


def work_paths(work: Path) -> tuple[Path, Path, Path]:
    return work / "baseline_csv", work / "infeasible_csv", work / "artifacts"


def detect_model_flags(csv_dir: Path) -> tuple[bool, bool]:
    has_storage = all((csv_dir / f"{name}.csv").exists() for name in ("STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET"))
    return has_storage, (csv_dir / "UDC.csv").exists()


def csv_summary(csv_dir: Path) -> dict[str, Any]:
    import pandas as pd

    sets = {}
    for name in ("REGION", "TECHNOLOGY", "FUEL", "EMISSION", "YEAR", "TIMESLICE", "MODE_OF_OPERATION", "STORAGE"):
        path = csv_dir / f"{name}.csv"
        if path.exists():
            sets[name] = int(len(pd.read_csv(path)))
    return {"csv_files": len(list(csv_dir.glob("*.csv"))), "sets": sets, "has_storage": detect_model_flags(csv_dir)[0], "has_udc": detect_model_flags(csv_dir)[1]}


def generate(excel: Path, csv_dir: Path) -> dict[str, Any]:
    from app.simulation.core.excel_to_csv import generate_csvs_from_excel
    from app.simulation.core.canonical_csv_order import canonicalize_csv_directory
    from app.simulation.core.data_processing import PARAM_INDEX

    if csv_dir.exists():
        shutil.rmtree(csv_dir)
    csv_dir.mkdir(parents=True)
    generate_csvs_from_excel(excel, csv_dir)
    canonicalize_csv_directory(csv_dir, PARAM_INDEX)
    return csv_summary(csv_dir)


def structural(csv_dir: Path, artifacts: Path, name: str) -> dict[str, Any]:
    from app.simulation.core.structural_infeasibility import analyze_structural_infeasibility

    findings = [item.to_dict() for item in analyze_structural_infeasibility(csv_dir)]
    out = artifacts / f"{name}_structural_findings.json"
    out.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    codes: dict[str, int] = {}
    for finding in findings:
        codes[finding["code"]] = codes.get(finding["code"], 0) + 1
    return {"finding_count": len(findings), "finding_codes": codes, "artifact": str(out)}


def create_infeasible_variant(baseline: Path, target: Path) -> dict[str, Any]:
    import pandas as pd

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(baseline, target)
    technology = str(pd.read_csv(target / "TECHNOLOGY.csv").iloc[0, 0])
    region = str(pd.read_csv(target / "REGION.csv").iloc[0, 0])
    year = int(pd.read_csv(target / "YEAR.csv").iloc[0, 0])
    key = {"REGION": region, "TECHNOLOGY": technology, "YEAR": year}
    for parameter, value in (("TotalAnnualMinCapacity", 1.0), ("TotalAnnualMaxCapacity", 0.0)):
        path = target / f"{parameter}.csv"
        columns = ["REGION", "TECHNOLOGY", "YEAR", "VALUE"]
        frame = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=columns)
        for column in columns:
            if column not in frame:
                frame[column] = None
        mask = (frame["REGION"].astype(str) == region) & (frame["TECHNOLOGY"].astype(str) == technology) & (pd.to_numeric(frame["YEAR"], errors="coerce") == year)
        frame = frame.loc[~mask, columns]
        frame.loc[len(frame)] = [region, technology, year, value]
        frame.to_csv(path, index=False)
    return {"mutation": "TotalAnnualMinCapacity=1 > TotalAnnualMaxCapacity=0", "key": key}


def build_lp(csv_dir: Path, lp_path: Path) -> dict[str, Any]:
    from app.simulation.core.instance_builder import build_instance
    from app.simulation.core.model_definition import create_abstract_model
    from app.simulation.core.solver import write_lp_file
    import pyomo.environ as pyo

    has_storage, has_udc = detect_model_flags(csv_dir)
    model = create_abstract_model(has_storage=has_storage, has_udc=has_udc)
    timings: dict[str, float] = {}
    instance = build_instance(model, str(csv_dir), has_storage=has_storage, has_udc=has_udc, timings_out=timings)
    counts = {"variables": sum(1 for _ in instance.component_data_objects(pyo.Var, active=True)), "constraints": sum(1 for _ in instance.component_data_objects(pyo.Constraint, active=True))}
    write_lp_file(instance, lp_path, symbolic_solver_labels=True)
    del instance, model
    gc.collect()
    return {**counts, "lp_path": str(lp_path), "lp_bytes": lp_path.stat().st_size, "build_timings": timings}


def solve_lp(lp_path: Path, *, method: str) -> dict[str, Any]:
    import highspy

    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("threads", 4)
    h.setOptionValue("solver", method)
    if method == "ipm":
        h.setOptionValue("run_crossover", "on")
    read_status = h.readModel(str(lp_path))
    started = time.perf_counter()
    run_status = h.run()
    elapsed = time.perf_counter() - started
    model_status = h.getModelStatus()
    info = h.getInfo()
    return {"method": method, "read_status": str(read_status), "run_status": str(run_status), "model_status": str(model_status), "solve_seconds": round(elapsed, 3), "objective": float(getattr(info, "objective_function_value", 0.0))}


def diagnose_infeasible(lp_path: Path, component: str) -> dict[str, Any]:
    from app.simulation.core.infeasibility_analysis import (
        try_compute_dual_ray,
        try_compute_iis,
        try_feasibility_relaxation,
    )

    if component == "dual":
        os.environ["OSEMOSYS_DUAL_RAY_TIME_LIMIT_SECONDS"] = "90"
        return {"dual_ray": try_compute_dual_ray(None, "highs", lp_path=lp_path).__dict__}
    if component == "iis":
        # The test mutation is intentionally trivial; if this cannot finish
        # inside the budget, the structural contradiction remains authoritative.
        os.environ["OSEMOSYS_IIS_TIME_LIMIT_SECONDS"] = "90"
        return {"iis": try_compute_iis(None, "highs", lp_path=lp_path).__dict__}
    if component == "relax":
        os.environ["OSEMOSYS_RELAXATION_TIME_LIMIT_SECONDS"] = "90"
        return {"feasibility_relaxation": try_feasibility_relaxation(None, "highs", lp_path=lp_path).__dict__}
    raise ValueError(f"Componente diagnóstico no soportado: {component}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--phase", choices=("prepare", "baseline", "dual", "iis", "relax", "infeasible", "all"), default="all")
    parser.add_argument("--max-rss-gib", type=float, default=12.0)
    args = parser.parse_args()
    excel = args.excel.resolve()
    if not excel.is_file():
        raise SystemExit(f"Excel no encontrado: {excel}")
    work = ROOT / "tmp" / "infeasibility-benchmarks" / args.label
    baseline, mutated, artifacts = work_paths(work)
    artifacts.mkdir(parents=True, exist_ok=True)
    report_path = artifacts / "report.json"
    report = base_report(excel, args.label, args.max_rss_gib)
    if report_path.exists():
        try:
            prior = json.loads(report_path.read_text(encoding="utf-8"))
            if prior.get("source_excel_sha256") == report["source_excel_sha256"]:
                report = prior
                report["limits"] = base_report(excel, args.label, args.max_rss_gib)["limits"]
        except (OSError, ValueError, TypeError):
            pass
    guard = Watchdog(args.max_rss_gib, report)
    guard.start()
    try:
        if args.phase in {"prepare", "all"}:
            phase(report, "excel_to_csv", lambda: generate(excel, baseline))
            write_report(report_path, report)
            phase(report, "baseline_structural", lambda: structural(baseline, artifacts, "baseline"))
            write_report(report_path, report)
        if args.phase in {"baseline", "all"}:
            lp = artifacts / "baseline.lp"
            phase(report, "baseline_build_lp", lambda: build_lp(baseline, lp))
            write_report(report_path, report)
            phase(report, "baseline_highs_ipm_crossover", lambda: solve_lp(lp, method="ipm"))
            write_report(report_path, report)
        if args.phase in {"dual", "iis", "relax"}:
            lp = artifacts / "baseline.lp"
            if not lp.exists():
                raise RuntimeError("No existe baseline.lp; ejecute antes la fase baseline.")
            phase(
                report,
                f"baseline_{args.phase}",
                lambda: diagnose_infeasible(lp, args.phase),
            )
            write_report(report_path, report)
        if args.phase in {"infeasible", "all"}:
            phase(report, "create_infeasible_variant", lambda: create_infeasible_variant(baseline, mutated))
            write_report(report_path, report)
            phase(report, "infeasible_structural", lambda: structural(mutated, artifacts, "infeasible"))
            lp = artifacts / "infeasible.lp"
            phase(report, "infeasible_build_lp", lambda: build_lp(mutated, lp))
            write_report(report_path, report)
            phase(report, "infeasible_highs", lambda: solve_lp(lp, method="ipm"))
            write_report(report_path, report)
            phase(report, "infeasible_diagnostics", lambda: diagnose_infeasible(lp))
            write_report(report_path, report)
    finally:
        guard.close()
        report["finished_at"] = now()
        write_report(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
