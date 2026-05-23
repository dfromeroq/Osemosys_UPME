"""Servicio de negocio para operaciones asíncronas de escenarios."""

from __future__ import annotations

import threading

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.db.dialect import osemosys_table
from app.models import (
    ChangeRequest,
    ChangeRequestValue,
    DeletionLog,
    OsemosysParamValue,
    OsemosysParamValueAudit,
    Scenario,
    ScenarioPermission,
    SimulationJob,
    SimulationJobEvent,
    SimulationJobFavorite,
    User,
)
from app.repositories.scenario_operation_repository import ScenarioOperationRepository
from app.services.official_import_service import OfficialImportService
from app.services.pagination import build_meta, normalize_pagination
from app.services.scenario_service import ScenarioService


class ScenarioOperationService:
    """Orquesta encolado, consulta y ejecución de operaciones largas."""

    @staticmethod
    def _to_public(
        job,
        *,
        username: str | None = None,
        scenario_name: str | None = None,
        target_scenario_name: str | None = None,
    ) -> dict:
        return {
            "id": int(job.id),
            "operation_type": job.operation_type,
            "status": job.status,
            "user_id": str(job.user_id),
            "username": username,
            "scenario_id": int(job.scenario_id) if job.scenario_id is not None else None,
            "scenario_name": scenario_name,
            "target_scenario_id": int(job.target_scenario_id) if job.target_scenario_id is not None else None,
            "target_scenario_name": target_scenario_name,
            "progress": float(job.progress),
            "stage": job.stage,
            "message": job.message,
            "result_json": job.result_json,
            "error_message": job.error_message,
            "queued_at": job.queued_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }

    @staticmethod
    def _enqueue_job(db: Session, *, job_id: int) -> None:
        from app.scenario.tasks import run_scenario_operation_job

        settings = get_settings()
        sync_mode = (
            settings.is_sync_simulation_mode()
            if hasattr(settings, "is_sync_simulation_mode")
            else str(getattr(settings, "simulation_mode", "async")).strip().lower() == "sync"
        )
        if sync_mode:
            # En modo sync ejecutamos en un hilo separado para responder 202 inmediato.
            worker = threading.Thread(
                target=lambda: run_scenario_operation_job.apply(args=[job_id], throw=False),
                daemon=True,
            )
            worker.start()
            return
        run_scenario_operation_job.delay(job_id)

    @staticmethod
    def submit_clone(
        db: Session,
        *,
        scenario_id: int,
        current_user: User,
        name: str,
        description: str | None,
        edit_policy: str,
    ) -> dict:
        ScenarioService._require_access(db, scenario_id=scenario_id, current_user=current_user)
        job = ScenarioOperationRepository.create_job(
            db,
            operation_type="CLONE_SCENARIO",
            user_id=current_user.id,
            scenario_id=scenario_id,
            payload_json={
                "source_scenario_id": scenario_id,
                "name": name,
                "description": description,
                "edit_policy": edit_policy,
            },
        )
        db.flush()
        ScenarioOperationRepository.add_event(
            db,
            job_id=job.id,
            event_type="INFO",
            stage="queue",
            message="Solicitud de copiado encolada.",
            progress=0.0,
        )
        db.commit()
        db.refresh(job)
        try:
            ScenarioOperationService._enqueue_job(db, job_id=int(job.id))
        except Exception as exc:  # pragma: no cover
            failed_job = ScenarioOperationRepository.get_by_id(db, job_id=int(job.id))
            if failed_job is not None:
                failed_job.status = "FAILED"
                failed_job.error_message = f"QUEUE_ENQUEUE_ERROR: {exc}"
                ScenarioOperationRepository.add_event(
                    db,
                    job_id=failed_job.id,
                    event_type="ERROR",
                    stage="queue",
                    message=f"No se pudo encolar la operación: {exc}",
                    progress=failed_job.progress,
                )
                db.commit()
                db.refresh(failed_job)
                return ScenarioOperationService._to_public(failed_job, username=current_user.username)
            raise ConflictError("No se pudo encolar la operación.") from exc
        return ScenarioOperationService._to_public(job, username=current_user.username)

    @staticmethod
    def submit_apply_excel_changes(
        db: Session,
        *,
        scenario_id: int,
        current_user: User,
        changes: list[dict],
    ) -> dict:
        ScenarioService._require_manage_values(db, scenario_id=scenario_id, current_user=current_user)
        job = ScenarioOperationRepository.create_job(
            db,
            operation_type="APPLY_EXCEL_CHANGES",
            user_id=current_user.id,
            scenario_id=scenario_id,
            payload_json={"scenario_id": scenario_id, "changes": changes},
        )
        db.flush()
        ScenarioOperationRepository.add_event(
            db,
            job_id=job.id,
            event_type="INFO",
            stage="queue",
            message="Solicitud de actualización encolada.",
            progress=0.0,
        )
        db.commit()
        db.refresh(job)
        ScenarioOperationService._enqueue_job(db, job_id=int(job.id))
        return ScenarioOperationService._to_public(job, username=current_user.username)

    @staticmethod
    def submit_delete(
        db: Session,
        *,
        scenario_id: int,
        current_user: User,
    ) -> dict:
        scenario = db.get(Scenario, scenario_id)
        if scenario is None:
            raise NotFoundError("Escenario no encontrado.")
        is_scenario_admin = bool(getattr(current_user, "can_manage_scenarios", False))
        if scenario.owner != current_user.username and not is_scenario_admin:
            raise ForbiddenError("No tienes permisos para eliminar este escenario.")

        child_count = db.query(func.count(Scenario.id)).filter(Scenario.base_scenario_id == scenario_id).scalar() or 0
        if int(child_count) > 0:
            raise ConflictError(
                "El escenario tiene escenarios derivados. Elimine o reasigne esas dependencias antes de continuar."
            )
        job = ScenarioOperationRepository.create_job(
            db,
            operation_type="DELETE_SCENARIO",
            user_id=current_user.id,
            scenario_id=scenario_id,
            payload_json={"scenario_id": scenario_id, "scenario_name": scenario.name},
        )
        db.flush()
        ScenarioOperationRepository.add_event(
            db,
            job_id=job.id,
            event_type="INFO",
            stage="queue",
            message="Solicitud de eliminación encolada.",
            progress=0.0,
        )
        db.commit()
        db.refresh(job)
        ScenarioOperationService._enqueue_job(db, job_id=int(job.id))
        return ScenarioOperationService._to_public(job, username=current_user.username, scenario_name=scenario.name)

    @staticmethod
    def list_jobs(
        db: Session,
        *,
        current_user: User,
        status: str | None,
        operation_type: str | None,
        scenario_id: int | None,
        cantidad: int | None,
        offset: int | None,
    ) -> dict:
        page, page_size, row_offset = normalize_pagination(offset, cantidad)
        rows, total = ScenarioOperationRepository.list_jobs(
            db,
            user_id=current_user.id,
            status=status,
            operation_type=operation_type,
            scenario_id=scenario_id,
            row_offset=row_offset,
            limit=page_size,
        )
        data = [
            ScenarioOperationService._to_public(
                job,
                username=username,
                scenario_name=scenario_name,
                target_scenario_name=target_scenario_name,
            )
            for job, username, scenario_name, target_scenario_name in rows
        ]
        return {"data": data, "meta": build_meta(page, page_size, total, status)}

    @staticmethod
    def get_by_id(db: Session, *, current_user: User, job_id: int) -> dict:
        visible = ScenarioOperationRepository.get_visible(db, job_id=job_id)
        if visible is None:
            raise NotFoundError("Operación no encontrada.")
        job, username, scenario_name, target_scenario_name = visible
        if str(job.user_id) != str(current_user.id):
            raise NotFoundError("Operación no encontrada.")
        return ScenarioOperationService._to_public(
            job,
            username=username,
            scenario_name=scenario_name,
            target_scenario_name=target_scenario_name,
        )

    @staticmethod
    def list_logs(
        db: Session, *, current_user: User, job_id: int, cantidad: int | None, offset: int | None
    ) -> dict:
        job = ScenarioOperationRepository.get_by_id(db, job_id=job_id)
        if job is None or str(job.user_id) != str(current_user.id):
            raise NotFoundError("Operación no encontrada.")
        page, page_size, row_offset = normalize_pagination(offset, cantidad)
        events, total = ScenarioOperationRepository.list_events(
            db, job_id=job_id, row_offset=row_offset, limit=page_size
        )
        data = [
            {
                "id": int(e.id),
                "event_type": e.event_type,
                "stage": e.stage,
                "message": e.message,
                "progress": float(e.progress) if e.progress is not None else None,
                "created_at": e.created_at,
            }
            for e in events
        ]
        return {"data": data, "meta": build_meta(page, page_size, total, None)}

    @staticmethod
    def _update_progress(
        db: Session,
        *,
        job,
        progress: float,
        stage: str,
        message: str,
        event_type: str = "INFO",
    ) -> None:
        job.progress = float(max(0.0, min(progress, 100.0)))
        job.stage = stage
        job.message = message
        ScenarioOperationRepository.add_event(
            db,
            job_id=int(job.id),
            event_type=event_type,
            stage=stage,
            message=message,
            progress=job.progress,
        )
        db.commit()

    @staticmethod
    def execute_job(db: Session, *, job_id: int) -> None:
        job = ScenarioOperationRepository.get_by_id(db, job_id=job_id)
        if job is None or job.status in {"RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"}:
            return
        if job.status != "QUEUED":
            return
        job.status = "RUNNING"
        job.started_at = func.now()
        job.progress = 1.0
        job.stage = "start"
        job.message = "Iniciando operación."
        db.commit()

        try:
            if job.operation_type == "CLONE_SCENARIO":
                ScenarioOperationService._run_clone_job(db, job=job)
            elif job.operation_type == "APPLY_EXCEL_CHANGES":
                ScenarioOperationService._run_apply_excel_changes_job(db, job=job)
            elif job.operation_type == "DELETE_SCENARIO":
                ScenarioOperationService._run_delete_job(db, job=job)
            else:
                raise RuntimeError(f"Tipo de operación no soportado: {job.operation_type}")
            job.status = "SUCCEEDED"
            job.progress = 100.0
            job.stage = "done"
            job.message = "Operación completada."
            job.finished_at = func.now()
            ScenarioOperationRepository.add_event(
                db,
                job_id=int(job.id),
                event_type="INFO",
                stage="done",
                message="Operación finalizada correctamente.",
                progress=100.0,
            )
            db.commit()
        except Exception as exc:  # pragma: no cover
            db.rollback()
            failed_job = ScenarioOperationRepository.get_by_id(db, job_id=job_id)
            if failed_job is None:
                return
            failed_job.status = "FAILED"
            failed_job.error_message = str(exc)
            failed_job.finished_at = func.now()
            failed_job.stage = "failed"
            failed_job.message = str(exc)
            ScenarioOperationRepository.add_event(
                db,
                job_id=failed_job.id,
                event_type="ERROR",
                stage="failed",
                message=str(exc),
                progress=failed_job.progress,
            )
            db.commit()

    @staticmethod
    def _run_clone_job(db: Session, *, job) -> None:
        payload = dict(job.payload_json or {})
        source_id = int(payload.get("source_scenario_id"))
        source = db.get(Scenario, source_id)
        if source is None:
            raise NotFoundError("Escenario origen no encontrado.")
        owner = db.get(User, job.user_id)
        if owner is None:
            raise NotFoundError("Usuario solicitante no encontrado.")

        ScenarioOperationService._update_progress(
            db,
            job=job,
            progress=5.0,
            stage="create_target",
            message="Creando escenario destino.",
        )
        new_scenario = Scenario(
            name=str(payload.get("name") or "").strip(),
            description=(str(payload.get("description") or "").strip() or None),
            owner=owner.username,
            base_scenario_id=source.id,
            changed_param_names=[],
            edit_policy=str(payload.get("edit_policy") or "OWNER_ONLY"),
            simulation_type=getattr(source, "simulation_type", "NATIONAL"),
            processing_mode=getattr(source, "processing_mode", "STANDARD"),
            is_template=False,
            udc_config=source.udc_config,
        )
        db.add(new_scenario)
        db.flush()
        # Copia tags del escenario origen excluyendo categorías exclusivas
        # (estado "Oficial/Entregado" no se hereda al clonar).
        from app.models import ScenarioTagLink, ScenarioTag, ScenarioTagCategory
        source_tag_ids = (
            db.execute(
                select(ScenarioTagLink.tag_id)
                .join(ScenarioTag, ScenarioTag.id == ScenarioTagLink.tag_id)
                .join(ScenarioTagCategory, ScenarioTagCategory.id == ScenarioTag.category_id)
                .where(
                    ScenarioTagLink.scenario_id == source.id,
                    ScenarioTagCategory.is_exclusive_combination.is_(False),
                )
            )
            .scalars()
            .all()
        )
        for tid in source_tag_ids:
            db.add(ScenarioTagLink(scenario_id=int(new_scenario.id), tag_id=int(tid)))
        job.target_scenario_id = int(new_scenario.id)
        ScenarioOperationService._update_progress(
            db,
            job=job,
            progress=10.0,
            stage="prepare_copy",
            message="Preparando copiado de datos OSeMOSYS.",
        )
        from app.repositories.scenario_repository import ScenarioRepository

        ScenarioRepository.add_permission(
            db,
            scenario_id=new_scenario.id,
            user_identifier=f"user:{owner.username}",
            user_id=owner.id,
            can_edit_direct=True,
            can_propose=True,
            can_manage_values=True,
        )
        db.commit()

        osemosys_param_value_table = osemosys_table("osemosys_param_value")
        total_rows = int(
            db.execute(
                text(
                    f"SELECT COUNT(*) FROM {osemosys_param_value_table} WHERE id_scenario = :src"
                ),
                {"src": source_id},
            ).scalar()
            or 0
        )

        def _on_batch(_: int, copied_total: int) -> None:
            if total_rows <= 0:
                next_progress = 95.0
            else:
                next_progress = 10.0 + (85.0 * float(copied_total) / float(total_rows))
            ScenarioOperationService._update_progress(
                db,
                job=job,
                progress=next_progress,
                stage="copying_data",
                message=f"Copiando datos: {copied_total}/{total_rows} registros.",
            )

        copied = ScenarioService._clone_data_batched(
            db,
            source_id=source_id,
            new_id=int(new_scenario.id),
            on_batch=_on_batch,
        )
        ScenarioService.sync_catalogs_from_scenario_values(db, scenario_id=int(new_scenario.id))
        job.result_json = {
            "source_scenario_id": source_id,
            "target_scenario_id": int(new_scenario.id),
            "target_scenario_name": new_scenario.name,
            "copied_rows": copied,
        }
        ScenarioOperationService._update_progress(
            db,
            job=job,
            progress=99.0,
            stage="finalizing",
            message="Finalizando operación de copiado.",
        )

    @staticmethod
    def _run_apply_excel_changes_job(db: Session, *, job) -> None:
        payload = dict(job.payload_json or {})
        scenario_id = int(payload.get("scenario_id"))
        changes = list(payload.get("changes") or [])
        if db.get(Scenario, scenario_id) is None:
            raise NotFoundError("Escenario no encontrado.")

        ScenarioOperationService._update_progress(
            db,
            job=job,
            progress=15.0,
            stage="validating_payload",
            message="Validando cambios a aplicar.",
        )
        actor_user = db.get(User, job.user_id) if job.user_id else None
        actor_username = str(actor_user.username) if actor_user is not None else None
        n_changes = len(changes)
        result = OfficialImportService.apply_excel_changes(
            db,
            scenario_id=scenario_id,
            changes=changes,
            actor=actor_username,
            batch_label=f"Aplicación Excel async ({n_changes} {'fila' if n_changes == 1 else 'filas'})",
        )
        ScenarioService.sync_catalogs_from_scenario_values(db, scenario_id=scenario_id)
        ScenarioOperationService._update_progress(
            db,
            job=job,
            progress=80.0,
            stage="updating_metadata",
            message="Actualizando metadatos de cambios del escenario.",
        )
        scenario = db.get(Scenario, scenario_id)
        if scenario is not None and changes:
            changed_param_names = sorted(
                {
                    str(c.get("param_name") or "").strip()
                    for c in changes
                    if str(c.get("param_name") or "").strip()
                }
            )
            change_ids = [int(c.get("row_id")) for c in changes if c.get("row_id") is not None]
            if change_ids:
                changed_param_names.extend(
                    sorted(
                        {
                            row.param_name
                            for row in db.query(OsemosysParamValue)
                            .filter(
                                OsemosysParamValue.id_scenario == scenario_id,
                                OsemosysParamValue.id.in_(change_ids),
                            )
                            .all()
                        }
                    )
                )
            changed_param_names = sorted({name for name in changed_param_names if name})
            ScenarioService._track_changed_params(scenario, param_names=changed_param_names)
            if changed_param_names:
                db.commit()
        job.result_json = {
            "updated": int(result.get("updated", 0)),
            "inserted": int(result.get("inserted", 0)),
            "skipped": int(result.get("skipped", 0)),
            "total_rows_read": len(changes),
        }
        ScenarioOperationService._update_progress(
            db,
            job=job,
            progress=99.0,
            stage="finalizing",
            message="Finalizando actualización desde Excel.",
        )

    @staticmethod
    def _run_delete_job(db: Session, *, job) -> None:
        payload = dict(job.payload_json or {})
        scenario_id = int(payload.get("scenario_id"))
        scenario = db.get(Scenario, scenario_id)
        if scenario is None:
            job.result_json = {"scenario_id": scenario_id, "deleted": False, "reason": "already_missing"}
            ScenarioOperationService._update_progress(
                db,
                job=job,
                progress=99.0,
                stage="finalizing",
                message="El escenario ya no existe.",
            )
            return

        owner = db.get(User, job.user_id)
        if owner is None:
            raise NotFoundError("Usuario solicitante no encontrado.")
        is_scenario_admin = bool(getattr(owner, "can_manage_scenarios", False))
        if scenario.owner != owner.username and not is_scenario_admin:
            raise ForbiddenError("No tienes permisos para eliminar este escenario.")

        child_count = db.query(func.count(Scenario.id)).filter(Scenario.base_scenario_id == scenario_id).scalar() or 0
        if int(child_count) > 0:
            raise ConflictError(
                "El escenario tiene escenarios derivados. Elimine o reasigne esas dependencias antes de continuar."
            )

        scenario_snapshot = {
            "name": scenario.name,
            "description": scenario.description,
            "owner": scenario.owner,
            "simulation_type": scenario.simulation_type,
            "edit_policy": scenario.edit_policy,
            "tag_ids": [int(t.id) for t in (scenario.tags or [])],
            "base_scenario_id": scenario.base_scenario_id,
            "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
        }

        child_jobs: list[SimulationJob] = (
            db.query(SimulationJob).filter(SimulationJob.scenario_id == scenario_id).all()
        )
        for simulation_job in child_jobs:
            job_snapshot = {
                "scenario_id": simulation_job.scenario_id,
                "scenario_name": scenario.name,
                "display_name": simulation_job.display_name,
                "input_name": simulation_job.input_name,
                "solver_name": simulation_job.solver_name,
                "status": simulation_job.status,
                "queued_at": simulation_job.queued_at.isoformat() if simulation_job.queued_at else None,
                "deleted_via": "scenario_cascade",
                "parent_scenario_id": scenario_id,
            }
            db.add(
                DeletionLog(
                    entity_type="SIMULATION_JOB",
                    entity_id=simulation_job.id,
                    entity_name=(simulation_job.display_name or scenario.name or f"Job #{simulation_job.id}")[:400],
                    deleted_by_user_id=owner.id,
                    deleted_by_username=owner.username,
                    details_json=job_snapshot,
                )
            )
            db.query(SimulationJobFavorite).filter(SimulationJobFavorite.job_id == simulation_job.id).delete()
            db.query(SimulationJobEvent).filter(SimulationJobEvent.job_id == simulation_job.id).delete()
            db.delete(simulation_job)
        db.flush()

        ScenarioOperationService._update_progress(
            db,
            job=job,
            progress=4.0,
            stage="deleting_simulations",
            message=f"Eliminando {len(child_jobs)} simulaciones asociadas.",
        )

        change_request_ids = [
            int(row[0])
            for row in (
                db.query(ChangeRequest.id)
                .join(
                    OsemosysParamValue,
                    ChangeRequest.id_osemosys_param_value == OsemosysParamValue.id,
                )
                .filter(OsemosysParamValue.id_scenario == scenario_id)
                .all()
            )
        ]
        if change_request_ids:
            db.query(ChangeRequestValue).filter(
                ChangeRequestValue.id_change_request.in_(change_request_ids)
            ).delete(synchronize_session=False)
            db.query(ChangeRequest).filter(ChangeRequest.id.in_(change_request_ids)).delete(
                synchronize_session=False
            )

        db.query(OsemosysParamValueAudit).filter(
            OsemosysParamValueAudit.id_scenario == scenario_id
        ).delete(synchronize_session=False)

        total_rows = int(
            db.query(func.count(OsemosysParamValue.id))
            .filter(OsemosysParamValue.id_scenario == scenario_id)
            .scalar()
            or 0
        )
        ScenarioOperationService._update_progress(
            db,
            job=job,
            progress=5.0,
            stage="counting_values",
            message=f"Preparando eliminación de {total_rows} valores OSeMOSYS.",
        )

        batch_size = 25_000
        deleted_rows = 0
        cursor_id = 0
        while True:
            batch_ids = (
                select(OsemosysParamValue.id)
                .where(
                    OsemosysParamValue.id_scenario == scenario_id,
                    OsemosysParamValue.id > cursor_id,
                )
                .order_by(OsemosysParamValue.id)
                .limit(batch_size)
                .subquery()
            )
            batch = db.execute(
                select(
                    func.max(batch_ids.c.id).label("max_id"),
                    func.count(batch_ids.c.id).label("rows_count"),
                )
            ).mappings().first()
            if not batch or not batch["max_id"]:
                break
            max_id = int(batch["max_id"])
            rows_count = int(batch["rows_count"] or 0)
            db.execute(
                delete(OsemosysParamValue).where(
                    OsemosysParamValue.id_scenario == scenario_id,
                    OsemosysParamValue.id > cursor_id,
                    OsemosysParamValue.id <= max_id,
                )
            )
            deleted_rows += rows_count
            cursor_id = max_id
            progress = 10.0 + (80.0 * float(deleted_rows) / float(total_rows)) if total_rows else 90.0
            ScenarioOperationService._update_progress(
                db,
                job=job,
                progress=progress,
                stage="deleting_values",
                message=f"Eliminando valores OSeMOSYS: {deleted_rows}/{total_rows} registros.",
            )

        permission_count = (
            db.query(ScenarioPermission).filter(ScenarioPermission.id_scenario == scenario_id).delete()
        )
        ScenarioOperationService._update_progress(
            db,
            job=job,
            progress=94.0,
            stage="deleting_permissions",
            message="Eliminando permisos del escenario.",
        )
        scenario = db.get(Scenario, scenario_id)
        if scenario is not None:
            db.add(
                DeletionLog(
                    entity_type="SCENARIO",
                    entity_id=scenario_id,
                    entity_name=scenario.name[:400] if scenario.name else f"Escenario #{scenario_id}",
                    deleted_by_user_id=owner.id,
                    deleted_by_username=owner.username,
                    details_json={
                        **scenario_snapshot,
                        "cascaded_simulation_job_ids": [j.id for j in child_jobs],
                        "deleted_change_request_ids": change_request_ids,
                    },
                )
            )
            db.delete(scenario)
            db.commit()

        job.result_json = {
            "scenario_id": scenario_id,
            "scenario_name": payload.get("scenario_name"),
            "deleted": True,
            "deleted_values": deleted_rows,
            "deleted_permissions": int(permission_count or 0),
            "deleted_simulation_jobs": len(child_jobs),
            "deleted_change_requests": len(change_request_ids),
        }
        ScenarioOperationService._update_progress(
            db,
            job=job,
            progress=99.0,
            stage="finalizing",
            message="Finalizando eliminación del escenario.",
        )
