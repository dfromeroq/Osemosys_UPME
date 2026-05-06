"""Façade del núcleo OSEMOSYS: PostgreSQL → CSVs → DataPortal → solve → results.

Pipeline que replica el flujo del notebook OPT_YA_20260220:
  1. Lee datos del escenario desde PostgreSQL y genera CSVs temporales.
  2. Crea el AbstractModel (definición completa de OSeMOSYS).
  3. Carga CSVs via DataPortal y crea instancia concreta.
  4. (Opcional) Genera archivo LP con symbolic_solver_labels.
  5. Resuelve con HiGHS o GLPK (con diagnósticos de infactibilidad).
  6. Procesa y retorna resultados.
"""

from __future__ import annotations

import gc
import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.simulation.core.data_processing import (
    eliminar_valores_fuera_de_indices,
    get_processing_result_from_csv_dir,
    normalize_mode_of_operation_in_csv_dir,
    reorder_activity_ratio_csvs_for_dataportal,
    run_data_processing,
    run_data_processing_from_excel,
    strip_whitespace_in_set_csvs,
)
from app.simulation.core.instance_builder import build_instance
from app.simulation.core.model_definition import create_abstract_model
from app.simulation.core.results_processing import process_results
from app.simulation.core.solver import solve_model

logger = logging.getLogger(__name__)


def run_osemosys_from_db(
    db: Session,
    *,
    scenario_id: int,
    solver_name: str = "glpk",
    on_stage: Callable[[str, float], None] | None = None,
    generate_lp: bool = False,
    lp_dir: str | Path | None = None,
    lp_basename: str | None = None,
    on_solver_finished: Callable[[Any, Any, Any, dict], None] | None = None,
    run_iis_analysis: bool = False,
    job_id: int | None = None,
) -> dict:
    """Pipeline completo: DB → CSVs temporales → DataPortal → solve → results.

    Parameters
    ----------
    generate_lp : bool
        Si True, genera archivo LP con symbolic_solver_labels antes de resolver.
    lp_dir : str | Path | None
        Directorio para archivos LP. Si None, usa un directorio temporal.
    on_solver_finished :
        Hook opcional con firma ``(instance, solver, results, solution_dict)``
        invocado justo después del ``solve``. Pensado para análisis locales
        (ej. IIS); el pipeline productivo no lo usa.
    run_iis_analysis : bool
        Si ``True`` y el modelo resulta infactible, se corre **inline** el
        análisis enriquecido (IIS + mapeo a parámetros OSeMOSYS) aprovechando
        que ``instance`` y ``csv_dir`` siguen vivos. El resultado se añade al
        dict devuelto en ``infeasibility_diagnostics``. Por defecto ``False``.
    """
    timings: dict[str, float] = {}

    with tempfile.TemporaryDirectory(prefix="osemosys_csv_") as csv_dir:

        # =============================================================
        # 1. BD → CSVs temporales (celdas 5-20 del notebook)
        # =============================================================
        if on_stage:
            on_stage("data_loading", 30.0)

        t = perf_counter()
        proc_result = run_data_processing(
            db, scenario_id=scenario_id, csv_dir=csv_dir,
        )
        timings["data_processing_seconds"] = perf_counter() - t

        if not proc_result.sets.get("YEAR") or not proc_result.sets.get("REGION"):
            return {
                "objective_value": 0.0,
                "solver_name": solver_name,
                "solver_status": "NO_DATA",
                "coverage_ratio": 1.0,
                "total_demand": 0.0,
                "total_dispatch": 0.0,
                "total_unmet": 0.0,
                "dispatch": [],
                "unmet_demand": [],
                "new_capacity": [],
                "annual_emissions": [],
                "sol": {},
                "intermediate_variables": {},
            }

        if on_stage:
            on_stage("data_loaded", 40.0)

        # =============================================================
        # 2. Crear AbstractModel (celda 3 del notebook)
        # =============================================================
        t = perf_counter()
        model = create_abstract_model(
            has_storage=proc_result.has_storage,
            has_udc=proc_result.has_udc,
        )
        timings["declare_model_seconds"] = perf_counter() - t

        if on_stage:
            on_stage("declare_model", 45.0)

        # =============================================================
        # 3. DataPortal + create_instance (celda 23 del notebook)
        # =============================================================
        t = perf_counter()
        instance = build_instance(
            model,
            csv_dir,
            has_storage=proc_result.has_storage,
            has_udc=proc_result.has_udc,
        )
        timings["create_instance_seconds"] = perf_counter() - t
        del model
        gc.collect()

        if on_stage:
            on_stage("create_instance", 70.0)

        # =============================================================
        # 4. Solve (celdas 27-28 del notebook)
        # =============================================================
        if on_stage:
            on_stage("solver_start", 75.0)

        lp_path = None
        if generate_lp:
            effective_lp_dir = Path(lp_dir) if lp_dir else Path(csv_dir)
            effective_lp_dir.mkdir(parents=True, exist_ok=True)
            base = lp_basename or f"osemosys_scenario_{scenario_id}"
            lp_path = effective_lp_dir / f"{base}.lp"

        t = perf_counter()
        solver_result = solve_model(
            instance,
            solver_name=solver_name,
            lp_path=lp_path,
            on_solver_finished=on_solver_finished,
        )
        timings["solver_seconds"] = perf_counter() - t

        # Análisis enriquecido de infactibilidad INLINE solo si el usuario
        # optó por `run_iis_analysis=True` al encolar la simulación. En ese
        # caso corremos `enrich_solution_dict` aprovechando que instance y
        # csv_dir aún están vivos. Por defecto el diagnóstico queda para
        # dispararse on-demand desde la UI (no se paga tiempo extra aquí).
        if run_iis_analysis:
            ss = str(solver_result.get("solver_status", "")).lower()
            if "infeasible" in ss or "infactible" in ss:
                if on_stage:
                    on_stage("infeasibility_analysis_start", 86.0)
                _t_infeas = perf_counter()
                try:
                    # Import local para evitar coste de arranque cuando el flag está apagado.
                    from app.simulation.core.infeasibility_analysis import (  # noqa: WPS433
                        enrich_solution_dict,
                    )
                    enrich_solution_dict(
                        solver_result,
                        instance=instance,
                        csv_dir=csv_dir,
                        job_id=job_id,
                    )
                    diag = solver_result.get("infeasibility_diagnostics")
                    if isinstance(diag, dict):
                        diag["diagnostic_status"] = "SUCCEEDED"
                except Exception:  # pragma: no cover - best effort
                    logger.exception(
                        "Falló el análisis enriquecido de infactibilidad inline; "
                        "se continúa sin él."
                    )
                    diag = solver_result.get("infeasibility_diagnostics")
                    if isinstance(diag, dict):
                        diag["diagnostic_status"] = "FAILED"
                        diag["diagnostic_error"] = "error durante análisis inline"
                timings["infeasibility_analysis_seconds"] = perf_counter() - _t_infeas
                if on_stage:
                    on_stage("infeasibility_analysis_complete", 87.0)

        if on_stage:
            on_stage("solver", 88.0)

        # =============================================================
        # 5. Procesar resultados (celda 31 del notebook)
        # =============================================================
        t = perf_counter()
        sets = proc_result.sets
        results = process_results(
            instance,
            solver_result,
            regions=sets.get("REGION", []),
            technologies=sets.get("TECHNOLOGY", []),
            years=sets.get("YEAR", []),
            emissions=sets.get("EMISSION", []),
            has_storage=proc_result.has_storage,
            region_id_by_name=proc_result.region_id_by_name,
            technology_id_by_name=proc_result.technology_id_by_name,
            region_name_by_id=proc_result.region_name_by_id,
            fuel_id_by_name=proc_result.fuel_id_by_name,
            emission_id_by_name=proc_result.emission_id_by_name,
            timeslice_id_by_name=proc_result.timeslice_id_by_name,
            mode_of_operation_id_by_name=proc_result.mode_of_operation_id_by_name,
            season_id_by_name=proc_result.season_id_by_name,
            daytype_id_by_name=proc_result.daytype_id_by_name,
            dailytimebracket_id_by_name=proc_result.dailytimebracket_id_by_name,
            storage_id_by_name=proc_result.storage_id_by_name,
        )
        timings["results_processing_seconds"] = perf_counter() - t

        results["model_timings"] = {**timings, **results.get("model_timings", {})}

        if on_stage:
            on_stage("complete", 95.0)

        return results


def run_osemosys_from_csv_dir(
    csv_dir: str | Path,
    *,
    solver_name: str = "glpk",
    on_stage: Callable[[str, float], None] | None = None,
    generate_lp: bool = False,
    lp_dir: str | Path | None = None,
    lp_basename: str = "osemosys",
    on_solver_finished: Callable[[Any, Any, Any, dict], None] | None = None,
    run_iis_analysis: bool = False,
    job_id: int | None = None,
) -> dict:
    """Pipeline desde directorio de CSVs: lee sets del directorio y ejecuta solve → results.

    No usa BD ni Excel. El directorio debe contener los CSVs ya generados y procesados
    (sets + parámetros en el formato que espera DataPortal). Útil cuando ya tienes
    CSVs temporales (p. ej. de compare_notebook_vs_app o de una exportación previa).

    Parameters
    ----------
    csv_dir : str | Path
        Ruta al directorio con los CSVs (REGION.csv, TECHNOLOGY.csv, YEAR.csv, etc.).
    solver_name : str
        Solver a usar ("glpk" o "highs").
    on_stage : callable | None
        Callback (stage_name, progress_0_100) para progreso.
    generate_lp : bool
        Si True, genera archivo LP antes de resolver.
    lp_dir : str | Path | None
        Directorio para el archivo LP (si None, se usa csv_dir).
    lp_basename : str
        Nombre base del archivo .lp (default "osemosys").

    Returns
    -------
    dict
        Misma estructura que run_osemosys_from_db: objective_value, solver_status,
        dispatch, new_capacity, unmet_demand, annual_emissions, sol, etc.
    """
    timings: dict[str, float] = {}
    csv_dir = str(Path(csv_dir).resolve())
    if not os.path.isdir(csv_dir):
        return {
            "objective_value": 0.0,
            "solver_name": solver_name,
            "solver_status": "NO_DATA",
            "coverage_ratio": 1.0,
            "total_demand": 0.0,
            "total_dispatch": 0.0,
            "total_unmet": 0.0,
            "dispatch": [],
            "unmet_demand": [],
            "new_capacity": [],
            "annual_emissions": [],
            "sol": {},
            "intermediate_variables": {},
        }

    reorder_activity_ratio_csvs_for_dataportal(csv_dir)
    normalize_mode_of_operation_in_csv_dir(csv_dir)
    strip_whitespace_in_set_csvs(csv_dir)
    eliminar_valores_fuera_de_indices(csv_dir)

    if on_stage:
        on_stage("data_loaded", 40.0)

    proc_result = get_processing_result_from_csv_dir(csv_dir)

    if not proc_result.sets.get("YEAR") or not proc_result.sets.get("REGION"):
        return {
            "objective_value": 0.0,
            "solver_name": solver_name,
            "solver_status": "NO_DATA",
            "coverage_ratio": 1.0,
            "total_demand": 0.0,
            "total_dispatch": 0.0,
            "total_unmet": 0.0,
            "dispatch": [],
            "unmet_demand": [],
            "new_capacity": [],
            "annual_emissions": [],
            "sol": {},
            "intermediate_variables": {},
        }

    if on_stage:
        on_stage("declare_model", 45.0)

    t = perf_counter()
    model = create_abstract_model(
        has_storage=proc_result.has_storage,
        has_udc=proc_result.has_udc,
    )
    timings["declare_model_seconds"] = perf_counter() - t

    t = perf_counter()
    instance = build_instance(
        model,
        csv_dir,
        has_storage=proc_result.has_storage,
        has_udc=proc_result.has_udc,
    )
    timings["create_instance_seconds"] = perf_counter() - t
    del model
    gc.collect()

    if on_stage:
        on_stage("create_instance", 70.0)

    if on_stage:
        on_stage("solver_start", 75.0)

    lp_path = None
    if generate_lp:
        effective_lp_dir = Path(lp_dir) if lp_dir else Path(csv_dir)
        effective_lp_dir.mkdir(parents=True, exist_ok=True)
        lp_path = effective_lp_dir / f"{lp_basename}.lp"

    t = perf_counter()
    solver_result = solve_model(
        instance,
        solver_name=solver_name,
        lp_path=lp_path,
        on_solver_finished=on_solver_finished,
    )
    timings["solver_seconds"] = perf_counter() - t

    # Análisis enriquecido inline solo si el usuario optó por run_iis_analysis.
    if run_iis_analysis:
        ss = str(solver_result.get("solver_status", "")).lower()
        if "infeasible" in ss or "infactible" in ss:
            if on_stage:
                on_stage("infeasibility_analysis_start", 86.0)
            _t_infeas = perf_counter()
            try:
                from app.simulation.core.infeasibility_analysis import (  # noqa: WPS433
                    enrich_solution_dict,
                )
                enrich_solution_dict(
                    solver_result,
                    instance=instance,
                    csv_dir=csv_dir,
                    job_id=job_id,
                )
                diag = solver_result.get("infeasibility_diagnostics")
                if isinstance(diag, dict):
                    diag["diagnostic_status"] = "SUCCEEDED"
            except Exception:  # pragma: no cover
                logger.exception(
                    "Falló el análisis enriquecido de infactibilidad inline; "
                    "se continúa sin él."
                )
                diag = solver_result.get("infeasibility_diagnostics")
                if isinstance(diag, dict):
                    diag["diagnostic_status"] = "FAILED"
                    diag["diagnostic_error"] = "error durante análisis inline"
            timings["infeasibility_analysis_seconds"] = perf_counter() - _t_infeas
            if on_stage:
                on_stage("infeasibility_analysis_complete", 87.0)

    if on_stage:
        on_stage("solver", 88.0)

    sets = proc_result.sets
    t = perf_counter()
    results = process_results(
        instance,
        solver_result,
        regions=sets.get("REGION", []),
        technologies=sets.get("TECHNOLOGY", []),
        years=sets.get("YEAR", []),
        emissions=sets.get("EMISSION", []),
        has_storage=proc_result.has_storage,
        region_id_by_name=proc_result.region_id_by_name,
        technology_id_by_name=proc_result.technology_id_by_name,
        region_name_by_id=proc_result.region_name_by_id,
        fuel_id_by_name=proc_result.fuel_id_by_name,
        emission_id_by_name=proc_result.emission_id_by_name,
        timeslice_id_by_name=proc_result.timeslice_id_by_name,
        mode_of_operation_id_by_name=proc_result.mode_of_operation_id_by_name,
        season_id_by_name=proc_result.season_id_by_name,
        daytype_id_by_name=proc_result.daytype_id_by_name,
        dailytimebracket_id_by_name=proc_result.dailytimebracket_id_by_name,
        storage_id_by_name=proc_result.storage_id_by_name,
    )
    timings["results_processing_seconds"] = perf_counter() - t

    results["model_timings"] = {**timings, **results.get("model_timings", {})}

    if on_stage:
        on_stage("complete", 95.0)

    return results


def run_osemosys_from_excel(
    excel_path: str | Path,
    *,
    solver_name: str = "glpk",
    on_stage: Callable[[str, float], None] | None = None,
    generate_lp: bool = False,
    lp_dir: str | Path | None = None,
    sheet_name: str = "Parameters",
    div: int = 1,
) -> dict:
    """Pipeline completo desde archivo Excel: Excel → CSVs temporales → solve → results.

    No usa base de datos. La ruta del Excel debe ser un archivo .xlsm o .xlsx con hoja
    tipo SAND (p. ej. hoja 'Parameters'). El resto del flujo es idéntico a
    run_osemosys_from_db: create_abstract_model → build_instance → solve → process_results.

    Parameters
    ----------
    excel_path : str | Path
        Ruta al archivo Excel SAND (.xlsm o .xlsx).
    solver_name : str
        Solver a usar ("glpk" o "highs").
    on_stage : callable | None
        Callback (stage_name, progress_0_100) para progreso.
    generate_lp : bool
        Si True, genera archivo LP antes de resolver.
    lp_dir : str | Path | None
        Directorio para archivos LP (si None, se usa directorio temporal).
    sheet_name : str
        Nombre de la hoja del Excel (default "Parameters").
    div : int
        Divisor para timeslices en la generación de CSVs (default 1).

    Returns
    -------
    dict
        Misma estructura que run_osemosys_from_db: objective_value, solver_status,
        dispatch, new_capacity, unmet_demand, annual_emissions, sol, etc.
    """
    timings: dict[str, float] = {}
    excel_path = Path(excel_path)

    with tempfile.TemporaryDirectory(prefix="osemosys_csv_") as csv_dir:

        if on_stage:
            on_stage("data_loading", 30.0)

        t = perf_counter()
        proc_result = run_data_processing_from_excel(
            excel_path,
            csv_dir,
            sheet_name=sheet_name,
            div=div,
        )
        timings["data_processing_seconds"] = perf_counter() - t

        if not proc_result.sets.get("YEAR") or not proc_result.sets.get("REGION"):
            return {
                "objective_value": 0.0,
                "solver_name": solver_name,
                "solver_status": "NO_DATA",
                "coverage_ratio": 1.0,
                "total_demand": 0.0,
                "total_dispatch": 0.0,
                "total_unmet": 0.0,
                "dispatch": [],
                "unmet_demand": [],
                "new_capacity": [],
                "annual_emissions": [],
                "sol": {},
                "intermediate_variables": {},
            }

        if on_stage:
            on_stage("data_loaded", 40.0)

        t = perf_counter()
        model = create_abstract_model(
            has_storage=proc_result.has_storage,
            has_udc=proc_result.has_udc,
        )
        timings["declare_model_seconds"] = perf_counter() - t

        if on_stage:
            on_stage("declare_model", 45.0)

        t = perf_counter()
        instance = build_instance(
            model,
            csv_dir,
            has_storage=proc_result.has_storage,
            has_udc=proc_result.has_udc,
        )
        timings["create_instance_seconds"] = perf_counter() - t
        del model
        gc.collect()

        if on_stage:
            on_stage("create_instance", 70.0)

        if on_stage:
            on_stage("solver_start", 75.0)

        lp_path = None
        if generate_lp:
            effective_lp_dir = Path(lp_dir) if lp_dir else Path(csv_dir)
            effective_lp_dir.mkdir(parents=True, exist_ok=True)
            lp_path = effective_lp_dir / f"osemosys_excel_{excel_path.stem}.lp"

        t = perf_counter()
        solver_result = solve_model(
            instance, solver_name=solver_name, lp_path=lp_path,
        )
        timings["solver_seconds"] = perf_counter() - t

        if on_stage:
            on_stage("solver", 85.0)

        t = perf_counter()
        sets = proc_result.sets
        results = process_results(
            instance,
            solver_result,
            regions=sets.get("REGION", []),
            technologies=sets.get("TECHNOLOGY", []),
            years=sets.get("YEAR", []),
            emissions=sets.get("EMISSION", []),
            has_storage=proc_result.has_storage,
            region_id_by_name=proc_result.region_id_by_name,
            technology_id_by_name=proc_result.technology_id_by_name,
            region_name_by_id=proc_result.region_name_by_id,
            fuel_id_by_name=proc_result.fuel_id_by_name,
            emission_id_by_name=proc_result.emission_id_by_name,
            timeslice_id_by_name=proc_result.timeslice_id_by_name,
            mode_of_operation_id_by_name=proc_result.mode_of_operation_id_by_name,
            season_id_by_name=proc_result.season_id_by_name,
            daytype_id_by_name=proc_result.daytype_id_by_name,
            dailytimebracket_id_by_name=proc_result.dailytimebracket_id_by_name,
            storage_id_by_name=proc_result.storage_id_by_name,
        )
        timings["results_processing_seconds"] = perf_counter() - t

        results["model_timings"] = {**timings, **results.get("model_timings", {})}

        if on_stage:
            on_stage("complete", 95.0)

        return results
        