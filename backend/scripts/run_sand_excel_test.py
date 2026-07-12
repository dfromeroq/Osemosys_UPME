"""Runner CLI local: Excel -> importación -> simulación -> artefactos.

No requiere frontend ni levantar uvicorn. Ejecuta contra la base local
configurada en `DATABASE_URL` (recomendado SQLite en `.env.local`).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import OsemosysParamValue, Scenario, SimulationJob, User
from app.repositories.simulation_repository import SimulationRepository
from app.services.official_import_service import OfficialImportService
from app.services.scenario_service import ScenarioService
from app.services.simulation_service import SimulationService

DEFAULT_EXCEL = (
    r"C:\Users\jchav\OneDrive - Universidad de los Andes\Documentos\Trabajo UPME\Archivos osmosys\Excel\SAND_04_02_2026.xlsm"
)
DEFAULT_SCENARIO_NAME = "SAND_04_02_2026"
DEFAULT_SHEET_NAME = "Parameters"
DEFAULT_SEED_USERNAME = "seed"


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Importar Excel Parameters, ejecutar simulación y exportar artefactos JSON/CSV"
    )
    parser.add_argument(
        "--excel",
        type=Path,
        required=True,
        help=f"Ruta al archivo .xlsm/.xlsx (default: {DEFAULT_EXCEL})",
    )
    parser.add_argument(
        "--scenario-name",
        type=str,
        default=DEFAULT_SCENARIO_NAME,
        help=f"Nombre del escenario destino (default: {DEFAULT_SCENARIO_NAME})",
    )
    parser.add_argument(
        "--sheet-name",
        type=str,
        default=DEFAULT_SHEET_NAME,
        help=f"Nombre de hoja a importar (default: {DEFAULT_SHEET_NAME})",
    )
    parser.add_argument(
        "--seed-username",
        type=str,
        default=DEFAULT_SEED_USERNAME,
        help=f"Usuario que ejecuta/importa (default: {DEFAULT_SEED_USERNAME})",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Si el escenario ya existe, borrar sus datos OSeMOSYS y reimportar",
    )
    parser.add_argument(
        "--solver",
        choices=("highs", "glpk"),
        default="highs",
        help="Solver a usar (glpk para alinear con notebook por defecto)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "tmp" / "local",
        help="Directorio de salida para artefactos (default: backend/tmp/local)",
    )
    parser.add_argument(
        "--preserve-timeslices",
        action="store_true",
        help="Importar sin colapsar timeslices (equivalente a desmarcar el checkbox en la UI).",
    )
    parser.add_argument(
        "--extra-notebook-preprocess",
        action="store_true",
        help=(
            "Forzar un preprocesamiento notebook adicional después del import. "
            "Por defecto NO se ejecuta para evitar doble procesamiento; "
            "OfficialImportService ya aplica el preprocess requerido en hojas SAND."
        ),
    )
    parser.add_argument(
        "--extra-emission-ratios-at-input",
        action="store_true",
        help="Si se fuerza --extra-notebook-preprocess, también multiplica emisiones por InputActivityRatio.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    excel_path = args.excel
    if not excel_path.is_file():
        print(f"[ERROR] No existe el archivo Excel: {excel_path}")
        print("        Usa --excel para indicar la ruta correcta.")
        return 1

    settings = get_settings()
    print(f"  DATABASE_URL      : {settings.database_url}")
    print(f"  SIMULATION_MODE   : {settings.simulation_mode}")
    if not settings.is_sync_simulation_mode():
        print("  [aviso] SIMULATION_MODE no es 'sync'; la ejecución dependerá de broker/worker si está en async.")

    content = excel_path.read_bytes()
    filename = excel_path.name
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / "simulation_result.json"
    out_kpis_csv = output_dir / "simulation_kpis.csv"
    out_events_csv = output_dir / "simulation_events.csv"

    with SessionLocal() as session:
        user = session.execute(select(User).where(User.username == args.seed_username)).scalar_one_or_none()
        if not user:
            print(f"[ERROR] No existe usuario '{args.seed_username}'. Ejecuta scripts/seed.py primero.")
            return 1

        scenario = session.execute(
            select(Scenario).where(
                Scenario.name == args.scenario_name,
                Scenario.is_template.is_(False),
            )
        ).scalar_one_or_none()

        if scenario and args.replace:
            sid = scenario.id
            deleted = session.query(OsemosysParamValue).filter(OsemosysParamValue.id_scenario == sid).delete()
            session.commit()
            scenario = session.execute(select(Scenario).where(Scenario.id == sid)).scalar_one()
            print(f"  Datos OSeMOSYS del escenario existente borrados ({deleted} filas).")

        if not scenario:
            created = ScenarioService.create(
                session,
                current_user=user,
                name=args.scenario_name,
                description=f"Importado desde Excel ({args.sheet_name}) en modo local CLI",
                edit_policy="OWNER_ONLY",
                is_template=False,
            )
            sid = int(created["id"])
            scenario = session.get(Scenario, sid)
            if scenario is None:
                raise RuntimeError(f"No se pudo cargar el escenario recién creado (id={sid}).")
            print(f"  Escenario creado: {scenario.name} (id={scenario.id})")
        else:
            print(f"  Usando escenario existente: {scenario.name} (id={scenario.id})")

        print(f"  Importando hoja '{args.sheet_name}' desde {filename}...")
        import_result = OfficialImportService.import_xlsm(
            session,
            filename=filename,
            content=content,
            imported_by=user.username,
            selected_sheet_name=args.sheet_name,
            scenario_id_override=scenario.id,
            collapse_timeslices=not args.preserve_timeslices,
        )
        print(f"  Import: {import_result.get('inserted', 0)} insertados, {import_result.get('updated', 0)} actualizados, {import_result.get('skipped', 0)} omitidos.")
        if import_result.get("warnings"):
            for w in import_result["warnings"][:10]:
                print(f"    [aviso] {w}")
            if len(import_result["warnings"]) > 10:
                print(f"    ... y {len(import_result['warnings']) - 10} avisos más.")

        if args.extra_notebook_preprocess:
            from app.services.sand_notebook_preprocess import run_notebook_preprocess

            print("  Aplicando preprocesamiento notebook adicional (modo diagnóstico)...")
            run_notebook_preprocess(
                session,
                scenario.id,
                filter_by_sets=True,
                complete_matrices=False,
                emission_ratios_at_input=bool(args.extra_emission_ratios_at_input),
                generate_udc_matrices=False,
            )
            session.commit()
        else:
            print(
                "  Preprocess adicional omitido: el import oficial ya aplica el "
                "preprocesamiento SAND necesario."
            )
        print(f"  Ejecutando simulación (solver={args.solver})...")
        job_payload = SimulationService.submit(
            session,
            current_user=user,
            scenario_id=scenario.id,
            solver_name=args.solver,
        )
        job_id = int(job_payload["id"])
        job = session.get(SimulationJob, job_id)
        if job and job.status == "SUCCEEDED":
            result = SimulationService.get_result(
                session,
                current_user=user,
                job_id=job_id,
            )
        else:
            result = {
                "job_id": job_id,
                "scenario_id": int(scenario.id),
                "solver_name": args.solver,
                "records_used": int(job.records_used or 0) if job else 0,
                "osemosys_param_records": int(job.osemosys_param_records or 0) if job else 0,
                "objective_value": float(job.objective_value or 0.0) if job else 0.0,
                "solver_status": (job.model_timings_json or {}).get("solver_status", "unknown")
                if job
                else "unknown",
                "coverage_ratio": float(job.coverage_ratio or 0.0) if job else 0.0,
                "total_demand": float(job.total_demand or 0.0) if job else 0.0,
                "total_dispatch": float(job.total_dispatch or 0.0) if job else 0.0,
                "total_unmet": float(job.total_unmet or 0.0) if job else 0.0,
                "dispatch": [],
                "unmet_demand": [],
                "new_capacity": [],
                "annual_emissions": [],
                "sol": {},
                "intermediate_variables": {},
                "osemosys_inputs_summary": job.inputs_summary_json if job else [],
                "stage_times": job.stage_times_json if job else {},
                "model_timings": job.model_timings_json if job else {},
                "job_status": job.status if job else "UNKNOWN",
                "error_message": job.error_message if job else "No se pudo recuperar el job",
            }
        events, _ = SimulationRepository.list_events(session, job_id=job_id, row_offset=0, limit=100000)
        kpi_rows = [
            {
                "job_id": result.get("job_id"),
                "scenario_id": result.get("scenario_id"),
                "solver_name": result.get("solver_name"),
                "solver_status": result.get("solver_status"),
                "objective_value": result.get("objective_value"),
                "coverage_ratio": result.get("coverage_ratio"),
                "total_demand": result.get("total_demand"),
                "total_dispatch": result.get("total_dispatch"),
                "total_unmet": result.get("total_unmet"),
                "records_used": result.get("records_used"),
                "osemosys_param_records": result.get("osemosys_param_records"),
                "job_status": job.status if job else None,
                "queued_at": str(job.queued_at) if job else None,
                "started_at": str(job.started_at) if job else None,
                "finished_at": str(job.finished_at) if job else None,
            }
        ]
        event_rows = [
            {
                "id": ev.id,
                "job_id": ev.job_id,
                "event_type": ev.event_type,
                "stage": ev.stage,
                "message": ev.message,
                "progress": ev.progress,
                "created_at": str(ev.created_at),
            }
            for ev in events
        ]

    obj = float(result.get("objective_value", 0.0))
    total_demand = float(result.get("total_demand", 0.0))
    total_dispatch = float(result.get("total_dispatch", 0.0))
    total_unmet = float(result.get("total_unmet", 0.0))
    coverage = float(result.get("coverage_ratio", 0.0))
    status = result.get("solver_status", "?")

    print("\n--- Resumen (comparar con notebook) ---")
    print(f"  objective_value : {obj}")
    print(f"  total_demand    : {total_demand}")
    print(f"  total_dispatch  : {total_dispatch}")
    print(f"  total_unmet     : {total_unmet}")
    print(f"  coverage_ratio  : {coverage}")
    print(f"  solver_status   : {status}")
    print("--------------------------------------\n")

    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_csv(
        out_kpis_csv,
        kpi_rows,
        [
            "job_id",
            "scenario_id",
            "solver_name",
            "solver_status",
            "objective_value",
            "coverage_ratio",
            "total_demand",
            "total_dispatch",
            "total_unmet",
            "records_used",
            "osemosys_param_records",
            "job_status",
            "queued_at",
            "started_at",
            "finished_at",
        ],
    )
    _write_csv(
        out_events_csv,
        event_rows,
        ["id", "job_id", "event_type", "stage", "message", "progress", "created_at"],
    )

    print("Artefactos generados:")
    print(f"  JSON resultado : {out_json}")
    print(f"  CSV KPI        : {out_kpis_csv}")
    print(f"  CSV eventos    : {out_events_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
