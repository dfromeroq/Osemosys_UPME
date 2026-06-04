#!/usr/bin/env python3
"""Ejecuta el benchmark (4 años) sin variantes — para validar tiempos."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from time import perf_counter

import pandas as pd
import pyomo.environ as pyo
from pyomo.core import Var

import highspy

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.simulation.core.data_processing import (
    eliminar_valores_fuera_de_indices,
    get_processing_result_from_csv_dir,
    normalize_mode_of_operation_in_csv_dir,
    reorder_activity_ratio_csvs_for_dataportal,
    strip_whitespace_in_set_csvs,
)
from app.simulation.core.instance_builder import build_instance
from app.simulation.core.model_definition import create_abstract_model

CSV_ZIP = Path(
    "/home/jchavez/Documentos/UPME/Datos Simulacion/Regional/Caso 1/CSV.zip"
)
BENCHMARK_YEARS = {2022, 2023, 2024, 2025}
SOLVER_THREADS = int(os.getenv("SIM_SOLVER_THREADS", "0") or 0)


def trim_csvs_to_years(csv_dir: Path, keep_years: set[int]) -> None:
    year_csv = csv_dir / "YEAR.csv"
    if year_csv.is_file():
        df = pd.read_csv(year_csv)
        col = df.columns[0]
        df = df[df[col].astype(int).isin(keep_years)]
        df.to_csv(year_csv, index=False)
    for csv_file in csv_dir.glob("*.csv"):
        if csv_file.name == "YEAR.csv":
            continue
        df = pd.read_csv(csv_file, low_memory=False)
        if "YEAR" in df.columns:
            df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce")
            df = df[df["YEAR"].isin(keep_years)]
            df.to_csv(csv_file, index=False)


def pyomo_name_to_lp(name: str) -> str:
    if "[" in name and name.endswith("]"):
        base, rest = name.split("[", 1)
        return f"{base}({rest[:-1]})"
    return name


def lp_name_to_pyomo(name: str) -> str:
    if "(" in name and name.endswith(")"):
        base, rest = name.split("(", 1)
        return f"{base}[{rest[:-1]}]"
    return name


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="osemosys_benchmark_"))
    csv_dir = work / "csv"
    lp_path = work / "model.lp"
    csv_dir.mkdir(parents=True)

    with zipfile.ZipFile(CSV_ZIP, "r") as zf:
        zf.extractall(work)
    nested = work / "CSV"
    if nested.is_dir():
        for item in nested.iterdir():
            shutil.move(str(item), str(csv_dir / item.name))
        nested.rmdir()

    trim_csvs_to_years(csv_dir, BENCHMARK_YEARS)
    reorder_activity_ratio_csvs_for_dataportal(str(csv_dir))
    normalize_mode_of_operation_in_csv_dir(str(csv_dir))
    strip_whitespace_in_set_csvs(str(csv_dir))
    eliminar_valores_fuera_de_indices(str(csv_dir))

    proc = get_processing_result_from_csv_dir(str(csv_dir))
    print(
        f"sets: YEAR={len(proc.sets.get('YEAR', []))} "
        f"TECH={len(proc.sets.get('TECHNOLOGY', []))} "
        f"has_storage={proc.has_storage} has_udc={proc.has_udc}"
    )

    t0 = perf_counter()
    abstract = create_abstract_model(
        has_storage=proc.has_storage, has_udc=proc.has_udc
    )
    instance = build_instance(
        abstract, str(csv_dir),
        has_storage=proc.has_storage, has_udc=proc.has_udc,
    )
    print(f"build_instance: {perf_counter() - t0:.2f}s")

    t_w = perf_counter()
    instance.write(filename=str(lp_path), io_options={"symbolic_solver_labels": True})
    write_lp = perf_counter() - t_w
    print(f"write_lp: {write_lp:.2f}s, size={lp_path.stat().st_size / 1e6:.1f} MB")

    solver = pyo.SolverFactory("appsi_highs")
    if isinstance(getattr(solver, "highs_options", None), dict) and SOLVER_THREADS > 0:
        solver.highs_options["threads"] = SOLVER_THREADS
    t_s = perf_counter()
    results = solver.solve(instance, tee=False, load_solutions=False)
    appsi_solve = perf_counter() - t_s
    status = str(results.solver.termination_condition)
    obj_appsi = 0.0
    if "optimal" in status.lower():
        instance.solutions.load_from(results)
        obj_appsi = float(pyo.value(instance.OBJ))
    print(f"appsi_highs: status={status} obj={obj_appsi:.4f} solve={appsi_solve:.2f}s")

    h = highspy.Highs()
    h.setOptionValue("log_to_console", False)
    h.setOptionValue("output_flag", False)
    h.setOptionValue("solver", "ipm")
    h.setOptionValue("presolve", "on")
    if SOLVER_THREADS > 0:
        h.setOptionValue("threads", SOLVER_THREADS)
    t_r = perf_counter()
    h.readModel(str(lp_path))
    read_s = perf_counter() - t_r
    t_run = perf_counter()
    h.run()
    run_s = perf_counter() - t_run
    obj_h = float(h.getInfo().objective_function_value)
    print(
        f"highspy_lp: status={h.getModelStatus()} obj={obj_h:.4f} "
        f"read={read_s:.2f}s run={run_s:.2f}s total_read_run={read_s + run_s:.2f}s"
    )
    print(f"WORK_DIR={work}")


if __name__ == "__main__":
    main()
