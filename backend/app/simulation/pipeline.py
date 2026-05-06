"""Orquestacion del pipeline completo de simulacion OSeMOSYS.

Coordina el flujo transaccional de una corrida:
  1. Carga datos del escenario desde PostgreSQL (osemosys_param_value).
  2. Preprocesa y construye modelo Pyomo con sets, parametros y restricciones.
  3. Resuelve el modelo con el solver configurado (HiGHS, GLPK, etc.).
  4. Extrae resultados (dispatch, new_capacity, emisiones, etc.).
  5. Persiste resultados en la tabla osemosys_output_param_value y metadatos
     de resumen en simulation_job.

Arquitectura:
  - Ejecuta desde worker Celery (no desde request HTTP).
  - Cancelacion cooperativa entre etapas.
  - Resultados almacenados en BD (no en filesystem).
"""

from __future__ import annotations

import csv
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Final

from sqlalchemy import func, insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import OsemosysParamValue, OsemosysOutputParamValue, SimulationJob
from app.repositories.simulation_repository import SimulationRepository
from app.simulation.core.data_processing import PARAM_INDEX
from app.simulation.core.results_processing import VARIABLE_INDEX_NAMES
from app.simulation.osemosys_core import run_osemosys_from_csv_dir, run_osemosys_from_db


def _safe_slug(text: str | None, *, max_len: int = 60) -> str:
    """Devuelve un fragmento seguro para nombre de archivo. Vacío → 'sim'."""
    if not text:
        return "sim"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("._-")
    return (slug or "sim")[:max_len]


def _lp_dir_for_jobs() -> Path:
    """Carpeta donde se persisten los .lp de simulaciones."""
    settings = get_settings()
    base = Path(getattr(settings, "simulation_artifacts_dir", "/app/tmp"))
    out = base / "lp-files"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _lp_basename_for_job(job: SimulationJob, *, scenario_name: str | None = None) -> str:
    """``sim_<id>_<nombre>_<YYYYMMDDTHHMMSSZ>`` — nombre del .lp generado."""
    name_source = (
        getattr(job, "display_name", None)
        or scenario_name
        or getattr(job, "input_name", None)
        or "sim"
    )
    ts_attr = getattr(job, "queued_at", None) or datetime.now(timezone.utc)
    if isinstance(ts_attr, datetime):
        ts = ts_attr.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"sim_{job.id}_{_safe_slug(name_source)}_{ts}"

logger = logging.getLogger(__name__)

STAGE_EXTRACT_DATA: Final[str] = "extract_data"
STAGE_BUILD_MODEL: Final[str] = "build_model"
STAGE_SOLVE: Final[str] = "solve"
STAGE_PERSIST_RESULTS: Final[str] = "persist_results"
STAGE_CANCEL: Final[str] = "cancel"

BATCH_SIZE: Final[int] = 2000


def _build_csv_inputs_summary(csv_root: str | Path) -> tuple[int, list[dict[str, Any]]]:
    """Resume parámetros CSV para persistir trazabilidad similar al flujo por escenario."""
    csv_root = Path(csv_root)
    total_records = 0
    summary: list[dict[str, Any]] = []

    for param_name in sorted(PARAM_INDEX):
        path = csv_root / f"{param_name}.csv"
        if not path.exists():
            continue

        records = 0
        by_year: dict[int | None, dict[str, float | int]] = {}

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                records += 1
                raw_value = row.get("VALUE")
                try:
                    numeric_value = float(raw_value) if raw_value not in (None, "") else 0.0
                except (TypeError, ValueError):
                    numeric_value = 0.0

                raw_year = row.get("YEAR")
                if raw_year in (None, ""):
                    year = None
                else:
                    try:
                        year = int(float(str(raw_year).strip()))
                    except (TypeError, ValueError):
                        year = None

                bucket = by_year.setdefault(year, {"records": 0, "total_value": 0.0})
                bucket["records"] = int(bucket["records"]) + 1
                bucket["total_value"] = float(bucket["total_value"]) + numeric_value

        total_records += records
        if not by_year:
            by_year[None] = {"records": 0, "total_value": 0.0}
        for year in sorted(by_year, key=lambda value: -1 if value is None else value):
            summary.append(
                {
                    "param_name": param_name,
                    "year": year,
                    "records": int(by_year[year]["records"]),
                    "total_value": float(by_year[year]["total_value"]),
                }
            )

    return total_records, summary


def _check_cancel_requested(db: Session, *, job_id: int) -> None:
    """Evalua cancelacion cooperativa y corta la ejecucion si aplica."""
    job = SimulationRepository.get_job_by_id(db, job_id=job_id)
    if job and job.cancel_requested and job.status in ("QUEUED", "RUNNING"):
        job.status = "CANCELLED"
        job.finished_at = func.now()
        SimulationRepository.add_event(
            db,
            job_id=job_id,
            event_type="INFO",
            stage=STAGE_CANCEL,
            message="Simulacion cancelada por el usuario.",
            progress=job.progress,
        )
        db.commit()
        raise RuntimeError("JOB_CANCELLED")


def _empty_row_template(job_id: int, variable_name: str) -> dict[str, Any]:
    """Fila con todas las columnas nullables de osemosys_output_param_value inicializadas a None."""
    return {
        "id_simulation_job": job_id,
        "variable_name": variable_name,
        "id_region": None,
        "id_technology": None,
        "id_fuel": None,
        "id_emission": None,
        "id_timeslice": None,
        "id_mode_of_operation": None,
        "id_storage": None,
        "id_season": None,
        "id_daytype": None,
        "id_dailytimebracket": None,
        "technology_name": None,
        "fuel_name": None,
        "emission_name": None,
        "year": None,
        "value": 0.0,
        "value2": None,
        "index_json": None,
    }


def _build_output_rows(
    solution: dict[str, Any],
    job_id: int,
) -> list[dict]:
    """Construye la lista de dicts para bulk insert en osemosys_output_param_value."""
    rows: list[dict] = []
    lookups: dict[str, dict[str, int]] = solution.get("dimension_lookups", {}) or {}
    fuel_lookup = lookups.get("FUEL", {})

    for row in solution.get("dispatch", []):
        r = _empty_row_template(job_id, "Dispatch")
        r["id_region"] = row.get("region_id")
        r["id_technology"] = row.get("technology_id")
        r["technology_name"] = row.get("technology_name")
        r["fuel_name"] = row.get("fuel_name")
        if row.get("fuel_name") and fuel_lookup:
            fid = fuel_lookup.get(row["fuel_name"])
            if fid is not None:
                r["id_fuel"] = int(fid)
        r["year"] = row.get("year")
        r["value"] = float(row.get("dispatch", 0.0))
        r["value2"] = float(row.get("cost", 0.0))
        rows.append(r)

    for row in solution.get("new_capacity", []):
        r = _empty_row_template(job_id, "NewCapacity")
        r["id_region"] = row.get("region_id")
        r["id_technology"] = row.get("technology_id")
        r["technology_name"] = row.get("technology_name")
        r["year"] = row.get("year")
        r["value"] = float(row.get("new_capacity", 0.0))
        rows.append(r)

    for row in solution.get("unmet_demand", []):
        r = _empty_row_template(job_id, "UnmetDemand")
        r["id_region"] = row.get("region_id")
        r["year"] = row.get("year")
        r["value"] = float(row.get("unmet_demand", 0.0))
        rows.append(r)

    for row in solution.get("annual_emissions", []):
        r = _empty_row_template(job_id, "AnnualEmissions")
        r["id_region"] = row.get("region_id")
        r["year"] = row.get("year")
        r["value"] = float(row.get("annual_emissions", 0.0))
        rows.append(r)


    # Mapeo de nombre de dimensión del registry → columna de OsemosysOutputParamValue.
    _DIM_TO_ID_COL = {
        "REGION": "id_region",
        "TECHNOLOGY": "id_technology",
        "FUEL": "id_fuel",
        "EMISSION": "id_emission",
        "TIMESLICE": "id_timeslice",
        "MODE_OF_OPERATION": "id_mode_of_operation",
        "SEASON": "id_season",
        "DAYTYPE": "id_daytype",
        "DAILYTIMEBRACKET": "id_dailytimebracket",
        "STORAGE": "id_storage",
    }
    _DIM_TO_NAME_COL = {
        "TECHNOLOGY": "technology_name",
        "FUEL": "fuel_name",
        "EMISSION": "emission_name",
    }

    for var_name, entries in solution.get("intermediate_variables", {}).items():
        index_names = VARIABLE_INDEX_NAMES.get(var_name, ())
        for entry in entries:
            idx = entry.get("index") or []
            row = _empty_row_template(job_id, var_name)
            row["value"] = float(entry.get("value", 0.0))
            row["index_json"] = idx
            if index_names and len(idx) == len(index_names):
                for dim, raw_val in zip(index_names, idx):
                    if raw_val is None:
                        continue
                    if dim == "YEAR":
                        try:
                            row["year"] = int(raw_val)
                        except (TypeError, ValueError):
                            pass
                        continue
                    name = str(raw_val) if raw_val != "" else None
                    id_col = _DIM_TO_ID_COL.get(dim)
                    if id_col and name is not None:
                        lk = lookups.get(dim, {})
                        found = lk.get(name)
                        if found is not None:
                            row[id_col] = int(found)
                    name_col = _DIM_TO_NAME_COL.get(dim)
                    if name_col and name is not None:
                        row[name_col] = name
            rows.append(row)

    return rows


def _persist_infeasibility_event(
    db: Session,
    *,
    job_id: int,
    progress: float,
    solution: dict[str, Any],
) -> None:
    diag = solution.get("infeasibility_diagnostics")
    if not diag:
        return

    lines: list[str] = []
    cv = diag.get("constraint_violations", [])
    vbc = diag.get("var_bound_conflicts", [])
    if cv:
        lines.append(f"{len(cv)} restricciones violadas (top 10):")
        for i, c in enumerate(cv[:10]):
            lb_t = f"{c['lower']:.2e}" if c["lower"] is not None else "-inf"
            ub_t = f"{c['upper']:.2e}" if c["upper"] is not None else "+inf"
            lines.append(
                f"  {i+1}. {c['name']}: Body={c['body']:.6e}, "
                f"Bounds=[{lb_t}, {ub_t}], Side={c['side']}, "
                f"Violation={c['violation']:.2e}"
            )
    if vbc:
        lines.append(f"{len(vbc)} variables con bounds infactibles (top 10):")
        for i, v in enumerate(vbc[:10]):
            lines.append(
                f"  {i+1}. {v['name']}: LB={v['lb']:.2e}, "
                f"UB={v['ub']:.2e}, Gap={v['gap']:.2e}"
            )
    if lines:
        SimulationRepository.add_event(
            db,
            job_id=job_id,
            event_type="WARNING",
            stage="infeasibility",
            message="\n".join(lines)[:4000],
            progress=progress,
        )


def _persist_solution(
    db: Session,
    *,
    job: SimulationJob,
    solution: dict[str, Any],
    records_used: int,
    inputs_summary: list[dict[str, Any]],
    stage_times: dict[str, float],
) -> int:
    """Persiste resumen y filas de salida para cualquier tipo de job."""
    job.objective_value = solution.get("objective_value")
    job.solver_threads_used = solution.get("solver_threads_used")
    job.coverage_ratio = solution.get("coverage_ratio")
    job.total_demand = solution.get("total_demand")
    job.total_dispatch = solution.get("total_dispatch")
    job.total_unmet = solution.get("total_unmet")
    job.records_used = records_used
    job.osemosys_param_records = records_used
    job.stage_times_json = stage_times
    _model_timings = dict(solution.get("model_timings", {}))
    _model_timings["solver_status"] = solution.get("solver_status", "unknown")
    job.model_timings_json = _model_timings
    job.inputs_summary_json = inputs_summary
    job.infeasibility_diagnostics_json = solution.get("infeasibility_diagnostics")

    output_rows = _build_output_rows(solution, job_id=job.id)
    for i in range(0, len(output_rows), BATCH_SIZE):
        batch = output_rows[i : i + BATCH_SIZE]
        db.execute(insert(OsemosysOutputParamValue), batch)
        db.flush()
    return len(output_rows)


def _persist_critical_solver_metadata(
    db: Session,
    *,
    job: SimulationJob,
    solution: dict[str, Any],
) -> None:
    """Persiste metadata crítica del solve antes de insertar filas de salida.

    Esto permite conservar `solver_status` y diagnósticos de infactibilidad
    aunque el worker muera durante la etapa posterior de persistencia pesada.
    """
    job.infeasibility_diagnostics_json = solution.get("infeasibility_diagnostics")
    model_timings = dict(solution.get("model_timings", {}))
    model_timings["solver_status"] = solution.get("solver_status", "unknown")
    job.model_timings_json = model_timings
    db.commit()


def run_pipeline(db: Session, *, job_id: int) -> None:
    """Ejecuta una corrida completa de simulacion para un job especifico.

    Persiste resultados en BD (simulation_job + osemosys_output_param_value).
    """
    stage_times: dict[str, float] = {}
    t0 = perf_counter()
    job = SimulationRepository.get_job_by_id(db, job_id=job_id)
    if not job:
        raise RuntimeError("SIMULATION_JOB_NOT_FOUND")

    # ------------------------------------------------------------------
    # ETAPA 1: EXTRACCION DE DATOS DE ENTRADA
    # ------------------------------------------------------------------
    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="STAGE",
        stage=STAGE_EXTRACT_DATA,
        message="Extrayendo datos de entrada del escenario.",
        progress=5.0,
    )
    db.commit()
    _check_cancel_requested(db, job_id=job_id)

    osemosys_agg_rows = (
        db.query(
            OsemosysParamValue.param_name,
            OsemosysParamValue.year,
            func.count().label("records"),
            func.sum(OsemosysParamValue.value).label("total_value"),
        )
        .filter(OsemosysParamValue.id_scenario == job.scenario_id)
        .group_by(OsemosysParamValue.param_name, OsemosysParamValue.year)
        .all()
    )
    osemosys_total_count = sum(r.records for r in osemosys_agg_rows)
    osemosys_inputs_summary = sorted(
        [
            {
                "param_name": str(r.param_name),
                "year": int(r.year) if r.year is not None else None,
                "records": int(r.records),
                "total_value": float(r.total_value or 0.0),
            }
            for r in osemosys_agg_rows
        ],
        key=lambda x: (x["param_name"], x["year"] if x["year"] is not None else -1),
    )

    job.progress = 15.0
    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="STAGE",
        stage=STAGE_EXTRACT_DATA,
        message=f"Se cargaron {osemosys_total_count} registros de osemosys_param_value.",
        progress=job.progress,
    )
    db.commit()
    stage_times[f"{STAGE_EXTRACT_DATA}_seconds"] = perf_counter() - t0

    # ------------------------------------------------------------------
    # ETAPA 2: CONSTRUCCION DEL MODELO
    # ------------------------------------------------------------------
    t1 = perf_counter()
    _check_cancel_requested(db, job_id=job_id)

    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="STAGE",
        stage=STAGE_BUILD_MODEL,
        message="Construyendo estructura de datos para optimizacion.",
        progress=20.0,
    )
    
    db.commit()
    job.progress = 40.0
    db.commit()
    stage_times[f"{STAGE_BUILD_MODEL}_seconds"] = perf_counter() - t1

    # ------------------------------------------------------------------
    # ETAPA 3: RESOLUCION DEL MODELO (SOLVE)
    # ------------------------------------------------------------------
    t2 = perf_counter()
    _check_cancel_requested(db, job_id=job_id)
    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="STAGE",
        stage=STAGE_SOLVE,
        message="Ejecutando optimizacion OSEMOSYS.",
        progress=45.0,
    )
    db.commit()

    def _on_stage(stage_name: str, stage_progress: float) -> None:
        job.progress = stage_progress
        if stage_name == "infeasibility_analysis_start":
            msg = (
                "Modelo infactible detectado. Iniciando análisis de infactibilidad "
                "(IIS + mapeo a parámetros). Esto puede tomar varios segundos."
            )
            evt = "WARN"
        elif stage_name == "infeasibility_analysis_complete":
            msg = "Análisis de infactibilidad finalizado."
            evt = "INFO"
        else:
            msg = f"Bloque {stage_name} ejecutado."
            evt = "STAGE"
        SimulationRepository.add_event(
            db,
            job_id=job_id,
            event_type=evt,
            stage=stage_name,
            message=msg,
            progress=stage_progress,
        )
        db.commit()
        _check_cancel_requested(db, job_id=job_id)

    _gen_lp = bool(getattr(job, "generate_lp", False))
    _scenario_name = getattr(getattr(job, "scenario", None), "name", None)
    _lp_dir_eff = _lp_dir_for_jobs() if _gen_lp else None
    _lp_basename_eff = (
        _lp_basename_for_job(job, scenario_name=_scenario_name) if _gen_lp else None
    )
    solution = run_osemosys_from_db(
        db,
        scenario_id=job.scenario_id,
        solver_name=job.solver_name,
        on_stage=_on_stage,
        run_iis_analysis=bool(getattr(job, "run_iis_analysis", False)),
        generate_lp=_gen_lp,
        lp_dir=str(_lp_dir_eff) if _lp_dir_eff else None,
        lp_basename=_lp_basename_eff,
        job_id=job_id,
    )

    # Persistimos la ruta del .lp si se generó: habilita descarga vía
    # GET /simulations/{id}/lp-file. El path queda estable aunque después
    # se renombre el job (`display_name`).
    if _gen_lp and _lp_dir_eff and _lp_basename_eff:
        candidate = _lp_dir_eff / f"{_lp_basename_eff}.lp"
        if candidate.is_file():
            job.lp_path = str(candidate)

    job.progress = 85.0
    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="INFO",
        stage=STAGE_SOLVE,
        message=(
            f"Solver: {solution['solver_status']} | "
            f"Coverage: {solution['coverage_ratio']:.2%}"
        ),
        progress=job.progress,
    )

    _persist_infeasibility_event(
        db,
        job_id=job_id,
        progress=job.progress,
        solution=solution,
    )

    db.commit()
    _persist_critical_solver_metadata(db, job=job, solution=solution)
    stage_times[f"{STAGE_SOLVE}_seconds"] = perf_counter() - t2

    # ------------------------------------------------------------------
    # ETAPA 4: PERSISTENCIA DE RESULTADOS EN BD
    # ------------------------------------------------------------------
    t3 = perf_counter()
    _check_cancel_requested(db, job_id=job_id)
    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="STAGE",
        stage=STAGE_PERSIST_RESULTS,
        message="Persistiendo resultados en base de datos.",
        progress=90.0,
    )
    db.commit()

    output_count = _persist_solution(
        db,
        job=job,
        solution=solution,
        records_used=osemosys_total_count,
        inputs_summary=osemosys_inputs_summary,
        stage_times=stage_times,
    )

    stage_times[f"{STAGE_PERSIST_RESULTS}_seconds"] = perf_counter() - t3
    job.stage_times_json = stage_times

    logger.info(
        "Job %s: %d filas de resultado insertadas en osemosys_output_param_value",
        job_id,
        output_count,
    )

    job.progress = 100.0
    db.commit()


def run_pipeline_from_csv(db: Session, *, job_id: int) -> None:
    """Ejecuta una corrida completa de simulación a partir de un directorio CSV persistido."""
    stage_times: dict[str, float] = {}
    t0 = perf_counter()
    job = SimulationRepository.get_job_by_id(db, job_id=job_id)
    if not job:
        raise RuntimeError("SIMULATION_JOB_NOT_FOUND")
    if not job.input_ref:
        raise RuntimeError("SIMULATION_CSV_INPUT_NOT_FOUND")

    csv_root = Path(str(job.input_ref)).resolve()
    if not csv_root.is_dir():
        raise RuntimeError(f"SIMULATION_CSV_INPUT_NOT_FOUND: {csv_root}")

    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="STAGE",
        stage=STAGE_EXTRACT_DATA,
        message="Leyendo datos de entrada desde CSV persistidos.",
        progress=5.0,
    )
    db.commit()
    _check_cancel_requested(db, job_id=job_id)

    csv_total_count, csv_inputs_summary = _build_csv_inputs_summary(csv_root)
    job.progress = 15.0
    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="STAGE",
        stage=STAGE_EXTRACT_DATA,
        message=f"Se cargaron {csv_total_count} registros de parámetros CSV.",
        progress=job.progress,
    )
    db.commit()
    stage_times[f"{STAGE_EXTRACT_DATA}_seconds"] = perf_counter() - t0

    t1 = perf_counter()
    _check_cancel_requested(db, job_id=job_id)
    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="STAGE",
        stage=STAGE_BUILD_MODEL,
        message="Preparando estructura de datos desde directorio CSV.",
        progress=20.0,
    )
    db.commit()
    job.progress = 40.0
    db.commit()
    stage_times[f"{STAGE_BUILD_MODEL}_seconds"] = perf_counter() - t1

    t2 = perf_counter()
    _check_cancel_requested(db, job_id=job_id)
    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="STAGE",
        stage=STAGE_SOLVE,
        message="Ejecutando optimizacion OSEMOSYS desde CSV.",
        progress=45.0,
    )
    db.commit()

    def _on_stage(stage_name: str, stage_progress: float) -> None:
        job.progress = stage_progress
        if stage_name == "infeasibility_analysis_start":
            msg = (
                "Modelo infactible detectado. Iniciando análisis de infactibilidad "
                "(IIS + mapeo a parámetros). Esto puede tomar varios segundos."
            )
            evt = "WARN"
        elif stage_name == "infeasibility_analysis_complete":
            msg = "Análisis de infactibilidad finalizado."
            evt = "INFO"
        else:
            msg = f"Bloque {stage_name} ejecutado."
            evt = "STAGE"
        SimulationRepository.add_event(
            db,
            job_id=job_id,
            event_type=evt,
            stage=stage_name,
            message=msg,
            progress=stage_progress,
        )
        db.commit()
        _check_cancel_requested(db, job_id=job_id)

    _gen_lp = bool(getattr(job, "generate_lp", False))
    _lp_dir_eff = _lp_dir_for_jobs() if _gen_lp else None
    _lp_basename_eff = _lp_basename_for_job(job) if _gen_lp else "osemosys"
    solution = run_osemosys_from_csv_dir(
        csv_root,
        solver_name=job.solver_name,
        on_stage=_on_stage,
        run_iis_analysis=bool(getattr(job, "run_iis_analysis", False)),
        generate_lp=_gen_lp,
        lp_dir=str(_lp_dir_eff) if _lp_dir_eff else None,
        lp_basename=_lp_basename_eff,
        job_id=job_id,
    )

    if _gen_lp and _lp_dir_eff:
        candidate = _lp_dir_eff / f"{_lp_basename_eff}.lp"
        if candidate.is_file():
            job.lp_path = str(candidate)

    job.progress = 85.0
    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="INFO",
        stage=STAGE_SOLVE,
        message=(
            f"Solver: {solution['solver_status']} | "
            f"Coverage: {solution['coverage_ratio']:.2%}"
        ),
        progress=job.progress,
    )
    # Misma secuencia que run_pipeline: evento WARNING de diagnóstico + commit +
    # metadata crítica antes de la persistencia masiva de filas.
    _persist_infeasibility_event(
        db,
        job_id=job_id,
        progress=job.progress,
        solution=solution,
    )
    db.commit()
    _persist_critical_solver_metadata(db, job=job, solution=solution)
    stage_times[f"{STAGE_SOLVE}_seconds"] = perf_counter() - t2

    t3 = perf_counter()
    _check_cancel_requested(db, job_id=job_id)
    SimulationRepository.add_event(
        db,
        job_id=job_id,
        event_type="STAGE",
        stage=STAGE_PERSIST_RESULTS,
        message="Persistiendo resultados CSV en base de datos.",
        progress=90.0,
    )
    db.commit()

    output_count = _persist_solution(
        db,
        job=job,
        solution=solution,
        records_used=csv_total_count,
        inputs_summary=csv_inputs_summary,
        stage_times=stage_times,
    )
    stage_times[f"{STAGE_PERSIST_RESULTS}_seconds"] = perf_counter() - t3
    job.stage_times_json = stage_times

    logger.info(
        "Job CSV %s: %d filas de resultado insertadas en osemosys_output_param_value",
        job_id,
        output_count,
    )

    job.progress = 100.0
    db.commit()
