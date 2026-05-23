"""Endpoints REST para ciclo de vida de simulaciones.

Expone: submit (crear job), list (listar jobs del usuario), get (detalle), cancel,
logs (eventos de ejecución), result (artefacto JSON de resultados).
Todos requieren usuario autenticado; delegan a SimulationService.
"""

from __future__ import annotations

import io
import json
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.db.session import get_db
def _parse_tag_ids_csv_sim(value: str | None) -> list[int]:
    if not value:
        return []
    cleaned = value.strip().strip("[]")
    if not cleaned:
        return []
    out: list[int] = []
    for piece in cleaned.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.append(int(piece))
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=f"tag_ids inválido: '{piece}'"
            ) from exc
    return out


from app.models import (
    DeletionLog,
    OsemosysOutputParamValue,
    SimulationJob,
    SimulationJobEvent,
    SimulationJobFavorite,
    User,
)
from app.schemas.pagination import PaginatedResponse
from app.schemas.simulation import (
    SimulationJobDisplayNamePatch,
    SimulationJobFavoritePatch,
    SimulationJobPublic,
    SimulationLogPublic,
    SimulationOverviewPublic,
    SimulationResultPublic,
    SimulationSubmit,
)
from app.schemas.simulation_results import (
    OutputValuesTotals,
    OutputValuesWidePage,
    OutputWideFacets,
)
from app.services.csv_scenario_import_service import (
    CsvScenarioImportService,
    extract_zip_to_dir,
    find_csv_root,
    validate_csv_root,
)
from app.repositories.simulation_repository import SimulationRepository
from app.services.simulation_results_service import SimulationResultsService
from app.services.simulation_service import SimulationService

router = APIRouter(prefix="/simulations")


@router.post("", response_model=SimulationJobPublic, status_code=201)
def submit_simulation(
    payload: SimulationSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Crea un job de simulación (HTTP POST).

    Se usa `POST` porque la operación crea un nuevo recurso en cola y no es idempotente.

    Validaciones delegadas al servicio:
    - escenario existente;
    - autorización del usuario sobre escenario;
    - límite de jobs activos por usuario.

    Respuestas:
    - 201: job encolado.
    - 404: escenario no encontrado.
    - 403: usuario sin acceso al escenario.
    - 409: límite de concurrencia por usuario excedido.
    """
    try:
        return SimulationService.submit(
            db,
            current_user=current_user,
            scenario_id=payload.scenario_id,
            solver_name=payload.solver_name,
            run_iis_analysis=payload.run_iis_analysis,
            generate_lp=payload.generate_lp,
            display_name=payload.display_name,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.post("/from-csv", response_model=SimulationJobPublic, status_code=201)
async def submit_simulation_from_csv(
    csv_zip: UploadFile = File(...),
    solver_name: str = Form("highs"),
    run_iis_analysis: bool = Form(False),
    generate_lp: bool = Form(False),
    input_name: str | None = Form(default=None),
    simulation_type: str = Form(default="NATIONAL"),
    save_as_scenario: bool = Form(default=False),
    scenario_name: str | None = Form(default=None),
    description: str | None = Form(default=None),
    edit_policy: str = Form(default="OWNER_ONLY"),
    tag_ids: str | None = Form(default=None),
    display_name: str | None = Form(
        default=None,
        description="Nombre opcional para esta corrida; si se omite, se usa el nombre del archivo ZIP.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Encola una simulación desde un ZIP con CSV procesados."""
    if solver_name not in {"highs", "glpk", "gurobi"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solver inválido. Usa 'highs', 'glpk' o 'gurobi'.",
        )
    if not csv_zip.filename or not csv_zip.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes cargar un archivo ZIP con los CSV de entrada.",
        )
    if save_as_scenario and not (scenario_name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="scenario_name es obligatorio cuando save_as_scenario=true.",
        )
    if edit_policy not in {"OWNER_ONLY", "OPEN", "RESTRICTED"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="edit_policy inválido.",
        )
    settings = get_settings()
    artifact_root = Path(settings.simulation_artifacts_dir).resolve() / "csv_upload_jobs" / str(uuid.uuid4())
    keep_artifacts = False

    try:
        artifact_root.mkdir(parents=True, exist_ok=True)
        extract_zip_to_dir(csv_zip, artifact_root)
        csv_root = find_csv_root(artifact_root)
        if csv_root is None:
            shutil.rmtree(artifact_root, ignore_errors=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No se encontró un directorio válido con CSV de entrada. "
                    "El ZIP debe contener al menos "
                    + ", ".join(("YEAR.csv", "REGION.csv", "TECHNOLOGY.csv", "TIMESLICE.csv", "MODE_OF_OPERATION.csv"))
                    + "."
                ),
            )
        validation_errors = validate_csv_root(csv_root)
        if validation_errors:
            shutil.rmtree(artifact_root, ignore_errors=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=" ".join(validation_errors),
            )
        if save_as_scenario:
            created_scenario = CsvScenarioImportService.import_from_directory(
                db,
                current_user=current_user,
                csv_root=csv_root,
                scenario_name=(scenario_name or csv_zip.filename or "CSV import"),
                description=description,
                edit_policy=edit_policy,
                tag_ids=_parse_tag_ids_csv_sim(tag_ids),
                simulation_type=simulation_type,
            )
            return SimulationService.submit(
                db,
                current_user=current_user,
                scenario_id=int(created_scenario["id"]),
                solver_name=solver_name,
                run_iis_analysis=run_iis_analysis,
                generate_lp=generate_lp,
                display_name=display_name,
            )
        keep_artifacts = True
        return SimulationService.submit_from_csv(
            db,
            current_user=current_user,
            solver_name=solver_name,
            input_name=(input_name or csv_zip.filename or "CSV upload"),
            input_ref=str(csv_root),
            run_iis_analysis=run_iis_analysis,
            generate_lp=generate_lp,
            simulation_type=simulation_type,
            display_name=display_name,
        )
    except HTTPException:
        raise
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except Exception:
        raise
    finally:
        if not keep_artifacts:
            shutil.rmtree(artifact_root, ignore_errors=True)


@router.get("", response_model=PaginatedResponse[SimulationJobPublic])
def list_simulations(
    scope: str = "mine",
    status_filter: str | None = None,
    username: str | None = None,
    scenario_id: int | None = None,
    solver_name: str | None = None,
    cantidad: int | None = 25,
    offset: int | None = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Lista jobs del usuario autenticado con paginación estándar.

    Respuestas:
    - 200: listado paginado.

    Seguridad:
    - Solo retorna jobs pertenecientes al usuario autenticado.
    """
    return SimulationService.list_jobs(
        db,
        current_user=current_user,
        scope=scope,
        status=status_filter,
        username=username,
        scenario_id=scenario_id,
        solver_name=solver_name,
        cantidad=cantidad,
        offset=offset,
    )


@router.get("/overview", response_model=SimulationOverviewPublic)
def get_simulation_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Resumen global del tablero operativo de simulaciones."""
    return SimulationService.overview(db, current_user=current_user)


@router.get("/{job_id}", response_model=SimulationJobPublic)
def get_simulation(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Consulta un job puntual por `job_id` (HTTP GET).

    Respuestas:
    - 200: job encontrado y autorizado.
    - 404: job inexistente o no perteneciente al usuario.
    """
    try:
        return SimulationService.get_by_id(db, current_user=current_user, job_id=job_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{job_id}", response_model=SimulationJobPublic)
def patch_simulation(
    job_id: int,
    payload: SimulationJobDisplayNamePatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Actualiza metadatos editables del job (nombre visible, visibilidad).

    Solo el dueño puede cambiar estos campos. Campos no enviados no se tocan.
    """
    data = payload.model_dump(exclude_unset=True)
    try:
        return SimulationService.patch_metadata(
            db,
            current_user=current_user,
            job_id=job_id,
            display_name=data.get("display_name", ...),
            is_public=data.get("is_public"),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{job_id}/favorite", response_model=SimulationJobPublic)
def patch_simulation_favorite(
    job_id: int,
    payload: SimulationJobFavoritePatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Marca/desmarca el resultado como favorito del usuario actual."""
    try:
        return SimulationService.set_favorite(
            db,
            current_user=current_user,
            job_id=job_id,
            favorite=payload.is_favorite,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{job_id}/cancel", response_model=SimulationJobPublic)
def cancel_simulation(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Solicita cancelación de un job (HTTP POST).

    Se usa `POST` porque representa una transición de estado con efecto lateral
    (acción de dominio), no una actualización parcial genérica del recurso.

    Respuestas:
    - 200: cancelación registrada/aplicada.
    - 404: job inexistente o no autorizado.
    - 409: job no cancelable por estado.
    """
    try:
        return SimulationService.cancel(db, current_user=current_user, job_id=job_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.delete("/{job_id}", status_code=204)
def delete_simulation(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Elimina un job de simulación junto con sus outputs, logs y favoritos.

    Reglas:
    - Solo el dueño del job puede eliminarlo.
    - El job no puede estar QUEUED/RUNNING (hay que cancelarlo primero para
      que el worker no escriba sobre una fila inexistente).
    - La eliminación queda registrada en ``osemosys.deletion_log`` con
      ``entity_type='SIMULATION_JOB'`` y snapshot de los campos clave.
    - Las tablas hijas (output_param_value, simulation_job_event,
      simulation_job_favorite) tienen ``ON DELETE CASCADE`` en sus FK: se
      limpian automáticamente al borrar la fila del job.
    """
    job = db.get(SimulationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Simulación no encontrada.")
    is_scenario_admin = bool(getattr(current_user, "can_manage_scenarios", False))
    if job.user_id != current_user.id and not is_scenario_admin:
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para eliminar esta simulación.",
        )
    if job.status in ("QUEUED", "RUNNING"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El job está en cola o ejecución. Cancela primero antes de "
                "eliminarlo para evitar que el worker escriba sobre una fila "
                "inexistente."
            ),
        )

    label = job.display_name or job.input_name or f"Job #{job.id}"
    snapshot = {
        "scenario_id": job.scenario_id,
        "display_name": job.display_name,
        "input_name": job.input_name,
        "input_mode": job.input_mode,
        "solver_name": job.solver_name,
        "status": job.status,
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_message": job.error_message,
        "is_infeasible_result": bool(getattr(job, "is_infeasible_result", False)),
    }

    db.add(
        DeletionLog(
            entity_type="SIMULATION_JOB",
            entity_id=job.id,
            entity_name=label[:400],
            deleted_by_user_id=current_user.id,
            deleted_by_username=current_user.username,
            details_json=snapshot,
        )
    )
    db.delete(job)
    db.commit()


@router.get("/{job_id}/logs", response_model=PaginatedResponse[SimulationLogPublic])
def get_simulation_logs(
    job_id: int,
    cantidad: int | None = 50,
    offset: int | None = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Lista eventos de ejecución del job para trazabilidad operativa.

    Respuestas:
    - 200: logs paginados.
    - 404: job inexistente o no autorizado.
    """
    try:
        return SimulationService.list_logs(
            db,
            current_user=current_user,
            job_id=job_id,
            cantidad=cantidad,
            offset=offset,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{job_id}/result", response_model=SimulationResultPublic)
def get_simulation_result(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Retorna artefacto final de resultados de un job exitoso.

    Respuestas:
    - 200: resultado disponible.
    - 404: job no encontrado o artefacto no disponible.
    - 409: job aún no finaliza en estado exitoso.
    """
    try:
        return SimulationService.get_result(db, current_user=current_user, job_id=job_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


# ─────────────────────────────────────────────────────────────────────────────
#  Data Explorer — wide-format access to osemosys_output_param_value
# ─────────────────────────────────────────────────────────────────────────────

def _parse_csv_list_sim(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or None


def _parse_year_rules_sim(
    raw: str | None,
) -> list[tuple[int, str, float | None]]:
    """Parsea `"2025:gt:0.5,2030:nonzero"` a [(2025,"gt",0.5),(2030,"nonzero",None)]."""
    if not raw:
        return []
    out: list[tuple[int, str, float | None]] = []
    for part in raw.split(","):
        tokens = [t.strip() for t in part.split(":") if t.strip()]
        if len(tokens) < 2:
            continue
        try:
            year = int(tokens[0])
        except ValueError:
            continue
        op = tokens[1].lower()
        val: float | None = None
        if len(tokens) >= 3:
            try:
                val = float(tokens[2])
            except ValueError:
                val = None
        out.append((year, op, val))
    return out


@router.get(
    "/{job_id}/output-values/wide",
    response_model=OutputValuesWidePage,
)
def list_output_values_wide(
    job_id: int,
    variable_name: str | None = None,
    variable_names: str | None = None,
    region_names: str | None = None,
    technology_names: str | None = None,
    fuel_names: str | None = None,
    emission_names: str | None = None,
    timeslice_names: str | None = None,
    mode_names: str | None = None,
    storage_names: str | None = None,
    year_rules: str | None = None,
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Resultados en formato wide (años como columnas).

    Filtros por columna: listas CSV con valores por dimensión.
    `year_rules`: `year:op[:value]` separados por coma (ops: gt/lt/gte/lte/
    eq/ne/nonzero/zero).
    """
    try:
        return SimulationResultsService.list_output_values_wide(
            db,
            job_id=job_id,
            current_user=current_user,
            variable_name=variable_name,
            variable_names=_parse_csv_list_sim(variable_names),
            region_names=_parse_csv_list_sim(region_names),
            technology_names=_parse_csv_list_sim(technology_names),
            fuel_names=_parse_csv_list_sim(fuel_names),
            emission_names=_parse_csv_list_sim(emission_names),
            timeslice_names=_parse_csv_list_sim(timeslice_names),
            mode_names=_parse_csv_list_sim(mode_names),
            storage_names=_parse_csv_list_sim(storage_names),
            year_rules=_parse_year_rules_sim(year_rules),
            offset=offset,
            limit=limit,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e)
        ) from e


@router.get(
    "/{job_id}/output-values/wide/facets",
    response_model=OutputWideFacets,
)
def list_output_wide_facets(
    job_id: int,
    variable_name: str | None = None,
    variable_names: str | None = None,
    region_names: str | None = None,
    technology_names: str | None = None,
    fuel_names: str | None = None,
    emission_names: str | None = None,
    timeslice_names: str | None = None,
    mode_names: str | None = None,
    storage_names: str | None = None,
    year_rules: str | None = None,
    limit_per_column: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Valores únicos por columna para popovers de filtros."""
    try:
        return SimulationResultsService.list_output_wide_facets(
            db,
            job_id=job_id,
            current_user=current_user,
            variable_name=variable_name,
            variable_names=_parse_csv_list_sim(variable_names),
            region_names=_parse_csv_list_sim(region_names),
            technology_names=_parse_csv_list_sim(technology_names),
            fuel_names=_parse_csv_list_sim(fuel_names),
            emission_names=_parse_csv_list_sim(emission_names),
            timeslice_names=_parse_csv_list_sim(timeslice_names),
            mode_names=_parse_csv_list_sim(mode_names),
            storage_names=_parse_csv_list_sim(storage_names),
            year_rules=_parse_year_rules_sim(year_rules),
            limit_per_column=limit_per_column,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e)
        ) from e


@router.get(
    "/{job_id}/output-values/totals",
    response_model=OutputValuesTotals,
)
def get_output_totals(
    job_id: int,
    variable_name: str | None = None,
    variable_names: str | None = None,
    region_names: str | None = None,
    technology_names: str | None = None,
    fuel_names: str | None = None,
    emission_names: str | None = None,
    timeslice_names: str | None = None,
    mode_names: str | None = None,
    storage_names: str | None = None,
    year_rules: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Suma de ``value`` por año con los mismos filtros que wide."""
    try:
        return SimulationResultsService.get_output_totals(
            db,
            job_id=job_id,
            current_user=current_user,
            variable_name=variable_name,
            variable_names=_parse_csv_list_sim(variable_names),
            region_names=_parse_csv_list_sim(region_names),
            technology_names=_parse_csv_list_sim(technology_names),
            fuel_names=_parse_csv_list_sim(fuel_names),
            emission_names=_parse_csv_list_sim(emission_names),
            timeslice_names=_parse_csv_list_sim(timeslice_names),
            mode_names=_parse_csv_list_sim(mode_names),
            storage_names=_parse_csv_list_sim(storage_names),
            year_rules=_parse_year_rules_sim(year_rules),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e)
        ) from e


@router.get("/{job_id}/output-values/export")
def export_output_values(
    job_id: int,
    variable_name: str | None = None,
    variable_names: str | None = None,
    region_names: str | None = None,
    technology_names: str | None = None,
    fuel_names: str | None = None,
    emission_names: str | None = None,
    timeslice_names: str | None = None,
    mode_names: str | None = None,
    storage_names: str | None = None,
    year_rules: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Descarga todos los resultados filtrados en formato wide (Excel)."""
    try:
        payload = SimulationResultsService.export_output_values_xlsx(
            db,
            job_id=job_id,
            current_user=current_user,
            variable_name=variable_name,
            variable_names=_parse_csv_list_sim(variable_names),
            region_names=_parse_csv_list_sim(region_names),
            technology_names=_parse_csv_list_sim(technology_names),
            fuel_names=_parse_csv_list_sim(fuel_names),
            emission_names=_parse_csv_list_sim(emission_names),
            timeslice_names=_parse_csv_list_sim(timeslice_names),
            mode_names=_parse_csv_list_sim(mode_names),
            storage_names=_parse_csv_list_sim(storage_names),
            year_rules=_parse_year_rules_sim(year_rules),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e)
        ) from e

    filename = f"simulation_{job_id}_results.xlsx"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{job_id}/diagnose-infeasibility", response_model=SimulationJobPublic)
def diagnose_infeasibility(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Encola el análisis de infactibilidad (IIS + mapeo a parámetros) para
    un job infactible hecho con HiGHS. Devuelve el job actualizado con
    ``diagnostic_status='QUEUED'``.

    Respuestas:
    - 200: solicitud aceptada; el análisis se ejecuta asincrónicamente.
    - 404: job no encontrado o sin acceso.
    - 409: el job no es infactible, o fue corrido con GLPK (no soporta IIS),
           o el diagnóstico ya está en curso.
    """
    try:
        return SimulationService.request_infeasibility_diagnostic(
            db, current_user=current_user, job_id=job_id
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.post("/{job_id}/cancel-diagnostic", response_model=SimulationJobPublic)
def cancel_infeasibility_diagnostic(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Cancela el análisis de infactibilidad que esté en cola o corriendo
    para el job indicado. Marca la bandera en BD (para que la task
    coopere al siguiente chequeo) y revoca la task en Celery (para
    interrumpir si está atrapada en cálculos largos).

    Respuestas:
    - 200: cancelación aplicada; el job sigue en ``SUCCEEDED`` pero el
           ``diagnostic_status`` pasa a ``FAILED`` con error
           "Cancelado por el usuario".
    - 404: job no encontrado / sin acceso.
    - 409: no hay diagnóstico en cola ni en ejecución (nada para cancelar).
    """
    try:
        return SimulationService.cancel_infeasibility_diagnostic(
            db, current_user=current_user, job_id=job_id
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.get("/{job_id}/infeasibility-report")
def download_infeasibility_report(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Descarga el diagnóstico enriquecido de infactibilidad como JSON.

    Respuestas:
    - 200: archivo JSON (``Content-Disposition: attachment``).
    - 404: job no encontrado o sin diagnóstico disponible.
    """
    try:
        result = SimulationService.get_result(
            db, current_user=current_user, job_id=job_id
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    diagnostics = result.get("infeasibility_diagnostics")
    if not diagnostics:
        raise HTTPException(
            status_code=404,
            detail="El job no tiene diagnóstico de infactibilidad disponible.",
        )

    # Armado del payload descargable: overview y top sospechosos primero, luego
    # IIS, luego detalle. Se EXCLUYE `constraint_violations` (heurística
    # post-solve ruidosa); sigue en BD por compatibilidad interna pero no viaja
    # en el archivo al usuario.
    diag = diagnostics if isinstance(diagnostics, dict) else {}
    cleaned_diagnostics = {
        "overview": diag.get("overview"),
        "iis": diag.get("iis"),
        "top_suspects": diag.get("top_suspects", []),
        "constraint_analyses": diag.get("constraint_analyses", []),
        "var_bound_conflicts": diag.get("var_bound_conflicts", []),
        "unmapped_constraint_prefixes": diag.get("unmapped_constraint_prefixes", []),
        "csv_dir": diag.get("csv_dir"),
    }
    payload = {
        "job_id": result.get("job_id"),
        "scenario_id": result.get("scenario_id"),
        "solver_name": result.get("solver_name"),
        "solver_status": result.get("solver_status"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "infeasibility_diagnostics": cleaned_diagnostics,
    }
    buf = io.BytesIO(json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8"))
    filename = f"infeasibility_report_job_{job_id}.json"
    return StreamingResponse(
        buf,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/lp-file")
def download_lp_file(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Descarga el archivo ``.lp`` del modelo Pyomo escrito durante la corrida.

    Solo disponible cuando la simulación se lanzó con ``generate_lp=True``
    y el archivo persiste en ``simulation_job.lp_path``.

    Respuestas:
    - 200: archivo ``.lp`` (``Content-Disposition: attachment``).
    - 404: job sin acceso, sin ``lp_path``, o archivo borrado del disco.
    """
    from pathlib import Path as _Path

    job = SimulationRepository.get_job_for_user(
        db, job_id=job_id, user_id=current_user.id
    )
    if not job:
        raise HTTPException(status_code=404, detail="Simulación no encontrada.")
    lp_path = getattr(job, "lp_path", None)
    if not lp_path:
        raise HTTPException(
            status_code=404,
            detail=(
                "Esta simulación no tiene un archivo .lp asociado. "
                "Vuelve a lanzarla activando 'Guardar archivo .lp del modelo'."
            ),
        )
    p = _Path(lp_path)
    if not p.is_file():
        raise HTTPException(
            status_code=404,
            detail="El archivo .lp ya no existe en el servidor.",
        )
    filename = p.name
    return FileResponse(
        path=str(p),
        media_type="text/plain",
        filename=filename,
    )


@router.get("/{job_id}/iis-ilp")
def download_iis_ilp(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Descarga el archivo ``.ilp`` del IIS calculado por Gurobi.

    Solo disponible cuando el job se corrió con Gurobi y el análisis de
    infactibilidad finalizó (``infeasibility_diagnostics.iis.ilp_path``
    apunta a un archivo existente).

    Respuestas:
    - 200: archivo ``.ilp`` (``Content-Disposition: attachment``).
    - 404: job sin acceso, sin diagnóstico, sin ``.ilp`` o archivo borrado.
    """
    try:
        result = SimulationService.get_result(
            db, current_user=current_user, job_id=job_id
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    diagnostics = result.get("infeasibility_diagnostics") or {}
    iis_section = diagnostics.get("iis") or {}
    ilp_path = iis_section.get("ilp_path")
    if not ilp_path:
        raise HTTPException(
            status_code=404,
            detail=(
                "El job no tiene un archivo .ilp disponible. Solo se genera "
                "para simulaciones corridas con Gurobi tras un análisis de "
                "infactibilidad."
            ),
        )
    from pathlib import Path as _Path

    p = _Path(ilp_path)
    if not p.is_file():
        raise HTTPException(
            status_code=404,
            detail="El archivo .ilp ya no existe en el servidor.",
        )
    filename = f"iis_job_{job_id}.ilp"
    return FileResponse(
        path=str(p),
        media_type="text/plain",
        filename=filename,
    )


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Definir contrato HTTP de simulaciones y mapear errores de dominio a códigos REST.
#
# Posibles mejoras:
# - Documentar responses con ejemplos OpenAPI (`responses={...}`) por endpoint.
# - Añadir rate limiting por usuario para proteger infraestructura de ejecución.
#
# Riesgos en producción:
# - Sin controles de burst de submit, un actor autenticado puede saturar la cola.
# - Exposición de mensajes de error crudos puede filtrar detalles internos.
#
# Escalabilidad:
# - El módulo escala horizontalmente junto con API; cuello de botella real está
#   en worker CPU-bound y almacenamiento de eventos/artefactos.
