"""Publica escenarios/jobs de validación en PostgreSQL para verlos en frontend.

Crea escenarios OPEN bajo el usuario seed, ejecuta secuencialmente los jobs y
compara Excel vs CSV usando métricas y agregados persistidos en la BD.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from sqlalchemy import func, select, text

from app.db.session import SessionLocal
from app.models import OsemosysOutputParamValue, Scenario, SimulationJob, User
from app.services.csv_scenario_import_service import CsvScenarioImportService
from app.services.official_import_service import OfficialImportService
from app.services.scenario_operation_service import ScenarioOperationService
from app.services.scenario_service import ScenarioService
from app.services.simulation_service import SimulationService
from app.simulation.core.data_processing import run_data_processing, run_data_processing_from_excel

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


def _user(db, username: str) -> User:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        raise RuntimeError(f"No existe el usuario {username!r}")
    return user


def _existing_scenario(db, name: str) -> Scenario | None:
    return db.execute(select(Scenario).where(Scenario.name == name)).scalar_one_or_none()


def _create_excel_scenario(
    db,
    *,
    user: User,
    name: str,
    description: str,
    simulation_type: str,
    excel: Path,
    collapse_timeslices: bool,
) -> int:
    existing = _existing_scenario(db, name)
    if existing is not None:
        print(f"Escenario existente: {name} (id={existing.id})", flush=True)
        return int(existing.id)
    created = ScenarioService.create(
        db,
        current_user=user,
        name=name,
        description=description,
        edit_policy="OPEN",
        is_template=False,
        simulation_type=simulation_type,
        skip_populate_defaults=True,
    )
    scenario_id = int(created["id"])
    print(f"Importando Excel en escenario {scenario_id}: {name}", flush=True)
    OfficialImportService.import_xlsm(
        db,
        filename=excel.name,
        content=excel.read_bytes(),
        imported_by=user.username,
        selected_sheet_name="Parameters",
        scenario_id_override=scenario_id,
        use_default_scenario=False,
        collapse_timeslices=collapse_timeslices,
    )
    scenario = db.get(Scenario, scenario_id)
    if scenario is not None:
        scenario.edit_policy = "OPEN"
        db.commit()
    return scenario_id


def _create_csv_scenario(
    db,
    *,
    user: User,
    name: str,
    description: str,
    simulation_type: str,
    csv_root: Path,
) -> int:
    existing = _existing_scenario(db, name)
    if existing is not None:
        print(f"Escenario existente: {name} (id={existing.id})", flush=True)
        return int(existing.id)
    print(f"Importando CSV en escenario: {name}", flush=True)
    created = CsvScenarioImportService.import_from_directory(
        db,
        current_user=user,
        csv_root=csv_root,
        scenario_name=name,
        description=description,
        edit_policy="OPEN",
        simulation_type=simulation_type,
    )
    return int(created["id"])


def _export_canonical_csv(db, scenario_id: int, output: Path, *, force: bool) -> Path:
    marker = output / ".source_scenario_id"
    if output.exists() and not force and marker.exists():
        if marker.read_text(encoding="utf-8").strip() == str(scenario_id):
            print(f"CSV canónico existente: {output}", flush=True)
            return output
    if output.exists():
        shutil.rmtree(output)
    run_data_processing(db, scenario_id=scenario_id, csv_dir=str(output))
    marker.write_text(str(scenario_id), encoding="utf-8")
    print(f"CSV canónico exportado desde escenario {scenario_id}: {output}", flush=True)
    return output


def _delete_validation_scenario(db, user: User, name: str) -> None:
    scenario = _existing_scenario(db, name)
    if scenario is None:
        return
    print(f"Eliminando escenario de validación obsoleto: {name} (id={scenario.id})", flush=True)
    payload = ScenarioOperationService.submit_delete(
        db, scenario_id=int(scenario.id), current_user=user
    )
    # La tarea queda encolada, pero la ejecutamos ahora para no esperar al solver
    # regional. Cuando Celery la reciba verá estado terminal y será no-op.
    ScenarioOperationService.execute_job(db, job_id=int(payload["id"]))
    if _existing_scenario(db, name) is not None:
        raise RuntimeError(f"No fue posible eliminar el escenario {name}")


def _build_four_seasons(excel: Path, output: Path, *, force: bool) -> Path:
    if output.exists() and not force:
        ts = pd.read_csv(output / "TIMESLICE.csv")
        if len(ts) == 4:
            print(f"CSV 4 estaciones existente: {output}", flush=True)
            return output
    if output.exists():
        shutil.rmtree(output)
    run_data_processing_from_excel(excel, str(output), sheet_name="Parameters", div=24)
    ts_path = output / "TIMESLICE.csv"
    ts = pd.read_csv(ts_path)
    codes = ts["VALUE"].astype(str).tolist()
    if len(codes) != 4:
        raise RuntimeError(f"Se esperaban 4 timeslices y se obtuvieron {len(codes)}: {codes}")
    mapping = {code: f"ESTACION_{index}" for index, code in enumerate(codes, start=1)}
    for csv_path in output.glob("*.csv"):
        df = pd.read_csv(csv_path)
        if csv_path.name == "TIMESLICE.csv":
            df["VALUE"] = df["VALUE"].astype(str).replace(mapping)
        if "TIMESLICE" in df.columns:
            df["TIMESLICE"] = df["TIMESLICE"].astype(str).replace(mapping)
        df.to_csv(csv_path, index=False)
    year_split = pd.read_csv(output / "YearSplit.csv")
    sums = year_split.groupby("YEAR", dropna=False)["VALUE"].sum()
    if ((sums - 1.0).abs() > 1e-9).any():
        raise RuntimeError("YearSplit de cuatro estaciones no suma 1 por año")
    print(f"CSV 4 estaciones generado: {mapping}", flush=True)
    return output


def _find_existing_job(db, *, scenario_id: int, solver: str, display_name: str) -> SimulationJob | None:
    return db.execute(
        select(SimulationJob)
        .where(
            SimulationJob.scenario_id == scenario_id,
            SimulationJob.solver_name == solver,
            SimulationJob.display_name == display_name,
            SimulationJob.status.in_(("SUCCEEDED", "RUNNING", "QUEUED")),
        )
        .order_by(SimulationJob.id.desc())
    ).scalars().first()


def _wait_job(job_id: int, timeout_seconds: float) -> SimulationJob:
    started = time.monotonic()
    last_line = None
    while True:
        with SessionLocal() as db:
            job = db.get(SimulationJob, job_id)
            if job is None:
                raise RuntimeError(f"Job {job_id} desapareció")
            timings = job.model_timings_json if isinstance(job.model_timings_json, dict) else {}
            sample = (timings.get("runtime_resource_samples") or [{}])[-1]
            stage = sample.get("stage") if isinstance(sample, dict) else None
            line = (job.status, round(float(job.progress or 0), 1), stage)
            if line != last_line:
                print(f"  job={job_id} status={line[0]} progress={line[1]} stage={line[2]}", flush=True)
                last_line = line
            if job.status in TERMINAL:
                db.expunge(job)
                return job
        if time.monotonic() - started > timeout_seconds:
            raise TimeoutError(f"Job {job_id} excedió {timeout_seconds}s")
        time.sleep(5)


def _run_job(
    *,
    username: str,
    scenario_id: int,
    solver: str,
    display_name: str,
    description: str,
    timeout_seconds: float,
) -> SimulationJob:
    with SessionLocal() as db:
        existing = _find_existing_job(
            db, scenario_id=scenario_id, solver=solver, display_name=display_name
        )
        if existing is not None:
            print(f"Job existente: {display_name} (id={existing.id}, status={existing.status})", flush=True)
            existing_id = int(existing.id)
            existing_status = str(existing.status)
            db.expunge(existing)
            if existing_status in ("RUNNING", "QUEUED"):
                return _wait_job(existing_id, timeout_seconds)
            return existing
        user = _user(db, username)
        payload = SimulationService.submit(
            db,
            current_user=user,
            scenario_id=scenario_id,
            solver_name=solver,
            display_name=display_name,
            description=description,
        )
        job_id = int(payload["id"])
    job = _wait_job(job_id, timeout_seconds)
    if job.status != "SUCCEEDED":
        raise RuntimeError(f"Job {job.id} terminó {job.status}: {job.error_message}")
    return job


def _aggregates(db, job_id: int, variable: str) -> dict[str, float]:
    rows = db.execute(
        select(
            OsemosysOutputParamValue.year,
            func.sum(OsemosysOutputParamValue.value),
        )
        .where(
            OsemosysOutputParamValue.id_simulation_job == job_id,
            OsemosysOutputParamValue.variable_name == variable,
        )
        .group_by(OsemosysOutputParamValue.year)
        .order_by(OsemosysOutputParamValue.year)
    ).all()
    return {str(year): float(value or 0) for year, value in rows}


def _compare_pair(db, left: SimulationJob, right: SimulationJob) -> dict:
    def rel(a: float, b: float) -> float:
        return abs(a - b) / max(abs(a), abs(b), 1.0)

    series = {}
    for variable in ("Dispatch", "NewCapacity", "AnnualEmissions"):
        a = _aggregates(db, int(left.id), variable)
        b = _aggregates(db, int(right.id), variable)
        years = sorted(set(a) | set(b))
        diffs = [abs(a.get(y, 0.0) - b.get(y, 0.0)) for y in years]
        rels = [rel(a.get(y, 0.0), b.get(y, 0.0)) for y in years]
        series[variable] = {
            "years": len(years),
            "max_abs_difference": max(diffs, default=0.0),
            "max_relative_difference": max(rels, default=0.0),
        }
    objective_a = float(left.objective_value or 0)
    objective_b = float(right.objective_value or 0)
    demand_a = float(left.total_demand or 0)
    demand_b = float(right.total_demand or 0)
    unmet_a = float(left.total_unmet or 0)
    unmet_b = float(right.total_unmet or 0)
    objective_abs = abs(objective_a - objective_b)
    objective_rel = rel(objective_a, objective_b)
    return {
        "left_job_id": int(left.id),
        "right_job_id": int(right.id),
        "solver": left.solver_name,
        "status_equal": left.status == right.status == "SUCCEEDED",
        "objective": {
            "left": objective_a,
            "right": objective_b,
            "abs_difference": objective_abs,
            "relative_difference": objective_rel,
            "passes": objective_abs <= 1e-4 or objective_rel <= 1e-7,
        },
        "total_demand": {
            "left": demand_a,
            "right": demand_b,
            "relative_difference": rel(demand_a, demand_b),
            "passes": rel(demand_a, demand_b) <= 1e-9,
        },
        "total_unmet": {
            "left": unmet_a,
            "right": unmet_b,
            "abs_difference": abs(unmet_a - unmet_b),
            "passes": abs(unmet_a - unmet_b) <= 1e-6,
        },
        "annual_aggregates": series,
    }


def _compare_exact_output_rows(db, left_job_id: int, right_job_id: int) -> dict:
    """Compara el multiconjunto completo persistido, sin depender del orden SQL."""
    columns = """
        variable_name, id_region, id_technology, id_fuel, id_emission,
        id_timeslice, id_mode_of_operation, id_storage, id_season, id_daytype,
        id_dailytimebracket, technology_name, fuel_name, emission_name, year,
        value, value2, index_json::text
    """
    row = db.execute(
        text(
            f"""
            WITH left_rows AS (
                SELECT {columns}
                FROM osemosys.osemosys_output_param_value
                WHERE id_simulation_job = :left_job_id
            ), right_rows AS (
                SELECT {columns}
                FROM osemosys.osemosys_output_param_value
                WHERE id_simulation_job = :right_job_id
            ), only_left AS (
                SELECT * FROM left_rows EXCEPT ALL SELECT * FROM right_rows
            ), only_right AS (
                SELECT * FROM right_rows EXCEPT ALL SELECT * FROM left_rows
            )
            SELECT
                (SELECT count(*) FROM left_rows),
                (SELECT count(*) FROM right_rows),
                (SELECT count(*) FROM only_left),
                (SELECT count(*) FROM only_right)
            """
        ),
        {"left_job_id": left_job_id, "right_job_id": right_job_id},
    ).one()
    return {
        "left_job_id": left_job_id,
        "right_job_id": right_job_id,
        "rows_left": int(row[0]),
        "rows_right": int(row[1]),
        "only_left": int(row[2]),
        "only_right": int(row[3]),
        "identical": int(row[2]) == 0 and int(row[3]) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="seed")
    parser.add_argument("--national-excel", default="/app/tmp/validation_inputs/sand_base_v10.xlsx")
    parser.add_argument("--regional-excel", default="/app/tmp/validation_inputs/regional_parameters_sand.xlsx")
    parser.add_argument("--national-csv", default="/app/tmp/experiments/canonical_national_excel_export")
    parser.add_argument("--regional-csv", default="/app/tmp/experiments/canonical_regional_excel_export")
    parser.add_argument("--four-seasons-csv", default="/app/tmp/experiments/national_csv_4seasons")
    parser.add_argument("--manifest", default="/app/tmp/experiments/frontend_publication_manifest.json")
    parser.add_argument("--timeout", type=float, default=7200)
    parser.add_argument("--force-four-seasons", action="store_true")
    parser.add_argument("--replace-csv-scenarios", action="store_true")
    args = parser.parse_args()

    national_excel = Path(args.national_excel)
    regional_excel = Path(args.regional_excel)
    national_csv = Path(args.national_csv)
    regional_csv = Path(args.regional_csv)
    four_csv = _build_four_seasons(
        national_excel, Path(args.four_seasons_csv), force=args.force_four_seasons
    )

    with SessionLocal() as db:
        user = _user(db, args.username)
        national_excel_id = _create_excel_scenario(
            db, user=user,
            name="VALIDACIÓN Nacional · Excel",
            description="Caso nacional SAND BASE v10 importado desde Excel. Visible para todos.",
            simulation_type="NATIONAL", excel=national_excel, collapse_timeslices=True,
        )
        regional_excel_id = _create_excel_scenario(
            db, user=user,
            name="VALIDACIÓN Regional · Excel",
            description="Modelo regional UPME importado desde Excel. Visible para todos.",
            simulation_type="REGIONAL", excel=regional_excel, collapse_timeslices=True,
        )
        national_csv = _export_canonical_csv(
            db, national_excel_id, national_csv, force=args.replace_csv_scenarios
        )
        regional_csv = _export_canonical_csv(
            db, regional_excel_id, regional_csv, force=args.replace_csv_scenarios
        )
        if args.replace_csv_scenarios:
            _delete_validation_scenario(db, user, "VALIDACIÓN Nacional · CSV")
            _delete_validation_scenario(db, user, "VALIDACIÓN Regional · CSV")
        scenario_ids = {
            "national_excel": national_excel_id,
            "national_csv": _create_csv_scenario(
                db, user=user,
                name="VALIDACIÓN Nacional · CSV",
                description="Export canónico del mismo Excel nacional, reimportado como CSV para certificar equivalencia.",
                simulation_type="NATIONAL", csv_root=national_csv,
            ),
            "regional_excel": regional_excel_id,
            "regional_csv": _create_csv_scenario(
                db, user=user,
                name="VALIDACIÓN Regional · CSV",
                description="Export canónico del mismo Excel regional, reimportado como CSV para certificar equivalencia.",
                simulation_type="REGIONAL", csv_root=regional_csv,
            ),
            "national_4seasons": _create_csv_scenario(
                db, user=user,
                name="VALIDACIÓN Nacional · 4 estaciones",
                description="Modelo nacional agregado desde 96 segmentos a cuatro estaciones de 24 segmentos.",
                simulation_type="NATIONAL", csv_root=four_csv,
            ),
        }

    specs = [
        ("national_excel_highs", "national_excel", "highs", "Nacional Excel · HiGHS canónico"),
        ("national_csv_highs", "national_csv", "highs", "Nacional CSV · HiGHS canónico"),
        ("regional_excel_highs", "regional_excel", "highs", "Regional Excel · HiGHS canónico"),
        ("regional_csv_highs", "regional_csv", "highs", "Regional CSV · HiGHS canónico"),
        ("national_4seasons_highs", "national_4seasons", "highs", "Nacional 4 estaciones · HiGHS"),
        ("national_excel_glpk", "national_excel", "glpk", "Nacional Excel · GLPK A canónico"),
        ("national_csv_glpk", "national_csv", "glpk", "Nacional CSV · GLPK A canónico"),
        ("regional_excel_glpk", "regional_excel", "glpk", "Regional Excel · GLPK A"),
    ]
    jobs: dict[str, SimulationJob] = {}
    failures: dict[str, str] = {}
    for key, scenario_key, solver, display in specs:
        print(f"\n=== {display} ===", flush=True)
        try:
            jobs[key] = _run_job(
                username=args.username,
                scenario_id=scenario_ids[scenario_key],
                solver=solver,
                display_name=display,
                description="Resultado público de validación reproducible Excel/CSV.",
                timeout_seconds=args.timeout,
            )
        except Exception as exc:
            failures[key] = str(exc)
            print(f"ERROR {key}: {exc}", flush=True)

    with SessionLocal() as db:
        comparisons = {}
        exact_comparisons = {}
        pairs = {
            "national_highs_excel_vs_csv": ("national_excel_highs", "national_csv_highs"),
            "regional_highs_excel_vs_csv": ("regional_excel_highs", "regional_csv_highs"),
            "national_glpk_excel_vs_csv": ("national_excel_glpk", "national_csv_glpk"),
        }
        for name, (left_key, right_key) in pairs.items():
            if left_key in jobs and right_key in jobs:
                left = db.get(SimulationJob, int(jobs[left_key].id))
                right = db.get(SimulationJob, int(jobs[right_key].id))
                if left is not None and right is not None:
                    comparisons[name] = _compare_pair(db, left, right)
                    exact_comparisons[name] = _compare_exact_output_rows(
                        db, int(left.id), int(right.id)
                    )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "username": args.username,
        "canonical_order": True,
        "scenario_ids": scenario_ids,
        "jobs": {
            key: {
                "id": int(job.id),
                "status": job.status,
                "solver": job.solver_name,
                "objective_value": float(job.objective_value or 0),
                "total_demand": float(job.total_demand or 0),
                "total_dispatch": float(job.total_dispatch or 0),
                "total_unmet": float(job.total_unmet or 0),
            }
            for key, job in jobs.items()
        },
        "failures": failures,
        "comparisons": comparisons,
        "exact_multiset_comparison": exact_comparisons,
    }
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
