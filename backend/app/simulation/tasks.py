from __future__ import annotations

"""Tareas Celery para ejecución de jobs de simulación.

Este módulo traduce el estado de infraestructura (task ejecutándose/fallando)
a estado de dominio (`simulation_job`) persistido en base de datos.
"""

import logging
import shutil
from pathlib import Path

from celery.signals import task_failure
from sqlalchemy import func, update

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import SimulationJob
from app.repositories.simulation_repository import SimulationRepository
from app.simulation.celery_app import celery_app
from app.simulation.pipeline import run_pipeline, run_pipeline_from_csv

logger = logging.getLogger(__name__)


def _persist_solver_failure_metadata(job: SimulationJob, exc: Exception) -> None:
    metadata = getattr(exc, "solver_failure_metadata", None)
    if not isinstance(metadata, dict):
        return
    job.model_timings_json = {
        **dict(job.model_timings_json or {}),
        **metadata,
    }


def _resolve_csv_upload_cleanup_root(input_ref: str | None) -> Path | None:
    if not input_ref:
        return None

    uploads_root = (Path(get_settings().simulation_artifacts_dir).resolve() / "csv_upload_jobs").resolve()
    candidate = Path(str(input_ref)).resolve()
    try:
        relative = candidate.relative_to(uploads_root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    return uploads_root / relative.parts[0]


def _cleanup_csv_upload_artifacts(job: SimulationJob | None) -> None:
    if job is None or getattr(job, "input_mode", "SCENARIO") != "CSV_UPLOAD":
        return

    cleanup_root = _resolve_csv_upload_cleanup_root(getattr(job, "input_ref", None))
    if cleanup_root is None:
        return

    try:
        shutil.rmtree(cleanup_root)
        logger.info("Artefactos CSV temporales eliminados para job %s en %s", job.id, cleanup_root)
    except FileNotFoundError:
        return
    except Exception:
        logger.warning(
            "No se pudieron eliminar artefactos CSV temporales del job %s en %s",
            getattr(job, "id", "?"),
            cleanup_root,
            exc_info=True,
        )


def _is_worker_lost_error(exception: BaseException | None) -> bool:
    if exception is None:
        return False
    text = f"{type(exception).__name__}: {exception}".lower()
    return (
        "workerlosterror" in text
        or "worker exited prematurely" in text
        or "signal 9" in text
        or "sigkill" in text
    )


def _fail_running_job(db, *, job: SimulationJob, reason: str) -> None:
    if job.status != "RUNNING":
        return
    job.status = "FAILED"
    job.finished_at = func.now()
    job.error_message = reason
    SimulationRepository.add_event(
        db,
        job_id=job.id,
        event_type="ERROR",
        stage="run",
        message=reason,
        progress=job.progress,
    )
    db.commit()


def _mark_failed_by_task_or_job_id(
    *,
    task_id: str | None,
    job_id: int | None,
    reason: str,
) -> bool:
    with SessionLocal() as db:
        job: SimulationJob | None = None
        if task_id:
            job = (
                db.query(SimulationJob)
                .filter(
                    SimulationJob.celery_task_id == task_id,
                    SimulationJob.status == "RUNNING",
                )
                .first()
            )
        if job is None and job_id is not None:
            job = (
                db.query(SimulationJob)
                .filter(SimulationJob.id == job_id, SimulationJob.status == "RUNNING")
                .first()
            )
        if job is None:
            return False
        _fail_running_job(db, job=job, reason=reason)
        return True


def _dispatch_pending_jobs_safely() -> None:
    try:
        from app.services.simulation_service import SimulationService

        with SessionLocal() as db:
            SimulationService.dispatch_pending_jobs(db)
    except Exception:
        logger.warning(
            "No se pudo despachar cola pendiente tras WorkerLostError",
            exc_info=True,
        )


@celery_app.task(name="app.simulation.tasks.run_simulation_job", bind=True)
def run_simulation_job(self, job_id: int) -> None:
    """Ejecuta un job de simulación en contexto worker.

    Args:
        self: Instancia de task Celery (no usada directamente en la lógica actual).
        job_id: Identificador del job persistido en BD.

    Flujo:
        1. Marca job en `RUNNING`.
        2. Ejecuta pipeline matemático.
        3. Persiste estado terminal (`SUCCEEDED`/`FAILED`).
        4. Registra eventos para observabilidad operacional.

    Edge cases:
        - Job no encontrado (mensaje obsoleto en cola).
        - Job previamente finalizado/cancelado.
        - Cancelación cooperativa durante pipeline.

    Rendimiento:
        - CPU-bound en `run_pipeline` durante etapa de solve.
        - I/O-bound en escrituras de eventos y actualización de estado.
    """
    try:
        current_task_id = self.request.id  # type: ignore[attr-defined]
    except Exception:
        current_task_id = None

    with SessionLocal() as db:
        transition_stmt = (
            update(SimulationJob)
            .where(SimulationJob.id == job_id, SimulationJob.status == "QUEUED")
            .values(status="RUNNING", started_at=func.now(), progress=1.0)
        )
        if current_task_id and not get_settings().is_sync_simulation_mode():
            transition_stmt = transition_stmt.where(
                SimulationJob.celery_task_id == current_task_id
            )
        transitioned = db.execute(transition_stmt).rowcount
        db.commit()

        if not transitioned:
            job = SimulationRepository.get_job_by_id(db, job_id=job_id)
            if not job:
                return
            if job.status in ("RUNNING", "CANCELLED", "SUCCEEDED", "FAILED"):
                return
            return

        job = SimulationRepository.get_job_by_id(db, job_id=job_id)
        if not job:
            return
        SimulationRepository.add_event(
            db,
            job_id=job_id,
            event_type="INFO",
            stage="start",
            message="Simulación iniciada en worker.",
            progress=job.progress,
        )
        db.commit()

    try:
        with SessionLocal() as db:
            job = SimulationRepository.get_job_by_id(db, job_id=job_id)
            if not job:
                return
            if getattr(job, "input_mode", "SCENARIO") == "CSV_UPLOAD":
                run_pipeline_from_csv(db, job_id=job_id)
            else:
                run_pipeline(db, job_id=job_id)
            job = SimulationRepository.get_job_by_id(db, job_id=job_id)
            if not job:
                return
            if job.status == "CANCELLED":
                return
            job.status = "SUCCEEDED"
            job.progress = 100.0
            job.finished_at = func.now()
            SimulationRepository.add_event(
                db,
                job_id=job_id,
                event_type="INFO",
                stage="end",
                message="Simulacion finalizada correctamente.",
                progress=100.0,
            )
            db.commit()
    except RuntimeError as exc:
        if str(exc) == "JOB_CANCELLED":
            return
        with SessionLocal() as db:
            job = SimulationRepository.get_job_by_id(db, job_id=job_id)
            if job:
                job.status = "FAILED"
                job.finished_at = func.now()
                job.error_message = str(exc)
                _persist_solver_failure_metadata(job, exc)
                SimulationRepository.add_event(
                    db,
                    job_id=job_id,
                    event_type="ERROR",
                    stage="run",
                    message=str(exc),
                    progress=job.progress,
                )
                db.commit()
    except Exception as exc:  # pragma: no cover - seguridad ante fallos inesperados
        with SessionLocal() as db:
            job = SimulationRepository.get_job_by_id(db, job_id=job_id)
            if job:
                job.status = "FAILED"
                job.finished_at = func.now()
                job.error_message = str(exc)
                _persist_solver_failure_metadata(job, exc)
                SimulationRepository.add_event(
                    db,
                    job_id=job_id,
                    event_type="ERROR",
                    stage="run",
                    message=str(exc),
                    progress=job.progress,
                )
                db.commit()
    finally:
        with SessionLocal() as db:
            job = SimulationRepository.get_job_by_id(db, job_id=job_id)
            _cleanup_csv_upload_artifacts(job)
        with SessionLocal() as db:
            from app.services.simulation_service import SimulationService

            SimulationService.dispatch_pending_jobs(db)


@celery_app.task(
    name="app.simulation.tasks.run_infeasibility_diagnostic_job",
    bind=True,
)
def run_infeasibility_diagnostic_job(
    self,
    job_id: int,
    level: str = "structural",
    baseline_scenario_id: int | None = None,
) -> None:
    """Ejecuta el análisis enriquecido de infactibilidad (IIS + mapeo a
    parámetros) sobre un job SUCCEEDED ya infactible.

    Se invoca **a demanda** desde la UI; el pipeline productivo ya no corre
    este análisis automáticamente para no agregar latencia a corridas que no
    necesitan diagnóstico.

    Requisitos:
        * ``job.status == 'SUCCEEDED'`` e infactible (``is_infeasible_result``).
        * ``job.solver_name == 'highs'`` (GLPK no expone IIS utilizable).

    Persistencia:
        Mantiene todos los campos existentes de ``infeasibility_diagnostics_json``
        y agrega: ``iis``, ``overview``, ``top_suspects``, ``constraint_analyses``,
        ``unmapped_constraint_prefixes`` y mete ``diagnostic_status='SUCCEEDED'``.
        En fallo deja ``diagnostic_status='FAILED'`` + ``diagnostic_error``.
    """
    # Imports locales para evitar costes de import en tiempo de arranque del
    # worker cuando esta task no se usa.
    import gc
    import os
    import tempfile
    from dataclasses import asdict
    from datetime import datetime, timezone

    from app.db.session import SessionLocal
    from app.simulation.core.data_processing import (
        eliminar_valores_fuera_de_indices,
        get_processing_result_from_csv_dir,
        normalize_mode_of_operation_in_csv_dir,
        reorder_activity_ratio_csvs_for_dataportal,
        run_data_processing,
        strip_whitespace_in_set_csvs,
    )
    from app.simulation.core.infeasibility_analysis import (
        classify_solver_outcome,
        enrich_solution_dict,
    )
    from app.simulation.core.instance_builder import build_instance
    from app.simulation.core.model_definition import create_abstract_model

    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    valid_levels = {
        "structural", "advanced", "presolve", "families", "dual_ray", "iis", "relaxation"
    }
    if level not in valid_levels:
        raise ValueError(f"Nivel de diagnóstico inválido: {level!r}")

    class _DiagnosticCancelled(RuntimeError):
        """Interno: se lanza cuando la UI pidió cancelar antes del siguiente chequeo."""

    def _raise_if_cancel_requested(job_id_: int) -> None:
        """Relee la fila del job y aborta si la UI marcó ``diagnostic_cancel_requested``."""
        with SessionLocal() as db_:
            j = SimulationRepository.get_job_by_id(db_, job_id=job_id_)
            if not j:
                raise _DiagnosticCancelled("Job no encontrado")
            d = j.infeasibility_diagnostics_json or {}
            if isinstance(d, dict) and d.get("diagnostic_cancel_requested"):
                raise _DiagnosticCancelled("Cancelado por el usuario.")

    def _on_diagnostic_phase(phase: str) -> None:
        """Chequea cancelación y persiste progreso entre fases costosas."""
        _raise_if_cancel_requested(job_id)
        labels = {
            "classify": "Clasificando el estado matemático del solver.",
            "presolve": "Ejecutando presolve diagnóstico sobre una copia del LP.",
            "families": "Aislando familias mediante probes incrementales HiGHS.",
            "dual_ray": "Calculando certificado de Farkas (dual ray).",
            "feasibility_relaxation": "Cuantificando cambios mínimos de factibilidad.",
            "iis": "Calculando subsistema inconsistente irreducible (IIS).",
            "structural": "Validando rutas de suministro y conflictos estructurales CSV/pandas.",
            "advanced": "Ejecutando la suite avanzada CSV y núcleos algebraicos reducidos.",
        }
        with SessionLocal() as phase_db:
            phase_job = SimulationRepository.get_job_by_id(phase_db, job_id=job_id)
            if not phase_job:
                raise _DiagnosticCancelled("Job no encontrado")
            SimulationRepository.add_event(
                phase_db,
                job_id=job_id,
                event_type="INFO",
                stage=f"infeasibility_{phase}",
                message=labels.get(phase, f"Fase de diagnóstico: {phase}"),
                progress=phase_job.progress,
            )
            phase_db.commit()

    def _structural_only(solution_seed: dict, csv_dir: str) -> dict:
        """Nivel barato: sólo CSV/pandas, sin construir el modelo Pyomo."""
        _on_diagnostic_phase("classify")
        classification = classify_solver_outcome(str(solution_seed["solver_status"]))
        _on_diagnostic_phase("structural")
        from app.simulation.core.structural_infeasibility import (  # noqa: WPS433
            analyze_structural_infeasibility,
        )

        diag_seed = dict(solution_seed["infeasibility_diagnostics"])
        diag_seed["classification"] = asdict(classification)
        diag_seed["structural_findings"] = [
            finding.to_dict() for finding in analyze_structural_infeasibility(csv_dir)
        ]
        diag_seed["analysis_level"] = "structural"
        return diag_seed

    def _advanced_only(solution_seed: dict, csv_dir: str, db_session) -> dict:
        """Once análisis focalizados sin reconstruir Pyomo ni cargar el LP global."""
        diag_seed = _structural_only(solution_seed, csv_dir)
        _on_diagnostic_phase("advanced")
        from app.simulation.core.advanced_infeasibility import (  # noqa: WPS433
            run_advanced_diagnostic_suite,
        )

        baseline_dir: str | None = None
        baseline_tmp = None
        try:
            if baseline_scenario_id is not None:
                baseline_tmp = tempfile.TemporaryDirectory(
                    prefix="osemosys_diag_baseline_"
                )
                run_data_processing(
                    db_session,
                    scenario_id=baseline_scenario_id,
                    csv_dir=baseline_tmp.name,
                )
                baseline_dir = baseline_tmp.name
            diag_seed["advanced_diagnostics"] = run_advanced_diagnostic_suite(
                csv_dir,
                diag_seed.get("structural_findings", []),
                baseline_csv_dir=baseline_dir,
            )
        finally:
            if baseline_tmp is not None:
                baseline_tmp.cleanup()
        diag_seed["analysis_level"] = "advanced"
        return diag_seed

    def _lp_progressive_method(instance: object, requested_level: str) -> dict:
        """Ejecuta presolve/familias sobre un LP temporal independiente."""
        from app.simulation.core.progressive_diagnostics import (  # noqa: WPS433
            run_family_diagnosis,
            run_highs_presolve_diagnostic,
        )
        from app.simulation.core.solver import write_lp_file  # noqa: WPS433

        lp_path = Path("tmp/infeasibility-reports") / f"job_{job_id}_{requested_level}.lp"
        write_lp_file(instance, lp_path)
        if requested_level == "presolve":
            _on_diagnostic_phase("presolve")
            result = run_highs_presolve_diagnostic(lp_path)
            return {"presolve_report": result, "analysis_level": requested_level}
        _on_diagnostic_phase("families")
        result = run_family_diagnosis(
            lp_path, cancel_check=lambda: _raise_if_cancel_requested(job_id)
        )
        return {"family_diagnosis": result, "analysis_level": requested_level}

    def _selected_enrichment(solution_seed: dict, requested_level: str) -> dict:
        diag_result = solution_seed["infeasibility_diagnostics"]
        keys = {
            "dual_ray": ("classification", "certificate"),
            "iis": (
                "classification", "iis", "overview", "top_suspects",
                "constraint_analyses", "unmapped_constraint_prefixes",
            ),
            "relaxation": ("classification", "feasibility_relaxation"),
        }[requested_level]
        return {
            **{key: diag_result[key] for key in keys if key in diag_result},
            "analysis_level": requested_level,
        }

    # 1) Mark RUNNING atomically y persistir el task_id de Celery.
    with SessionLocal() as db:
        job = SimulationRepository.get_job_by_id(db, job_id=job_id)
        if not job:
            return
        diag = dict(job.infeasibility_diagnostics_json or {})
        # Si la UI ya había marcado cancelación antes de que el worker tomara
        # la task, respetarla y salir sin trabajo.
        if diag.get("diagnostic_cancel_requested"):
            diag["diagnostic_status"] = "CANCELLED"
            diag["diagnostic_finished_at"] = _utc_now_iso()
            diag["diagnostic_error"] = "Cancelado por el usuario antes de iniciar."
            diag.pop("diagnostic_cancel_requested", None)
            job.infeasibility_diagnostics_json = diag
            SimulationRepository.add_event(
                db, job_id=job_id, event_type="WARN",
                stage="infeasibility_analysis_cancel",
                message="Diagnóstico cancelado antes de iniciar.",
                progress=job.progress,
            )
            db.commit()
            return
        diag["diagnostic_status"] = "RUNNING"
        diag["diagnostic_started_at"] = _utc_now_iso()
        diag.pop("diagnostic_error", None)
        # Captura el task id real del worker actual (override del que puso el
        # service al encolar, por si difiere).
        try:
            current_task_id = self.request.id  # type: ignore[attr-defined]
        except Exception:
            current_task_id = None
        if current_task_id:
            diag["diagnostic_celery_task_id"] = current_task_id
        job.infeasibility_diagnostics_json = diag
        SimulationRepository.add_event(
            db,
            job_id=job_id,
            event_type="INFO",
            stage="infeasibility_analysis_start",
            message="Análisis de infactibilidad (IIS + mapeo) iniciado.",
            progress=job.progress,
        )
        db.commit()
        job_snapshot = {
            "input_mode": getattr(job, "input_mode", "SCENARIO"),
            "input_ref": getattr(job, "input_ref", None),
            "scenario_id": job.scenario_id,
            "solver_name": job.solver_name,
            "solver_status": str(
                (getattr(job, "model_timings_json", None) or {}).get(
                    "solver_status", "infactible"
                )
            ),
            "model_defaults_version_id": getattr(job, "model_defaults_version_id", None),
            "diagnostics_seed": {
                "constraint_violations": diag.get("constraint_violations", []),
                "var_bound_conflicts": diag.get("var_bound_conflicts", []),
            },
        }

    # 2) Rebuild model and run enrich_solution_dict, revisando cancel entre fases.
    error_message: str | None = None
    was_cancelled = False
    enriched: dict | None = None
    try:
        _raise_if_cancel_requested(job_id)
        with SessionLocal() as db:
            from app.services.model_parameter_defaults_service import (
                ModelParameterDefaultsService,
            )
            from app.simulation.core.osemosys_defaults import (
                reset_defaults_context,
                set_defaults_context,
            )

            _vid, _defaults_map = ModelParameterDefaultsService.resolve_for_job(
                db,
                job_version_id=job_snapshot.get("model_defaults_version_id"),
            )
            _defaults_token = set_defaults_context(_defaults_map)
            try:
                if job_snapshot["input_mode"] == "CSV_UPLOAD":
                    csv_dir = job_snapshot["input_ref"]
                    if not csv_dir or not os.path.isdir(str(csv_dir)):
                        raise RuntimeError(
                            "No se encontraron los CSV originales del job "
                            f"({csv_dir!r}); el diagnóstico no puede correr."
                        )
                    reorder_activity_ratio_csvs_for_dataportal(str(csv_dir))
                    normalize_mode_of_operation_in_csv_dir(str(csv_dir))
                    strip_whitespace_in_set_csvs(str(csv_dir))
                    eliminar_valores_fuera_de_indices(str(csv_dir))
                    _raise_if_cancel_requested(job_id)
                    solution_seed = {
                        "solver_name": job_snapshot["solver_name"],
                        "solver_status": job_snapshot["solver_status"],
                        "infeasibility_diagnostics": dict(job_snapshot["diagnostics_seed"]),
                    }
                    if level == "structural":
                        enriched = _structural_only(solution_seed, str(csv_dir))
                    elif level == "advanced":
                        enriched = _advanced_only(solution_seed, str(csv_dir), db)
                    else:
                        proc_result = get_processing_result_from_csv_dir(str(csv_dir))
                        model = create_abstract_model(
                            has_storage=proc_result.has_storage,
                            has_udc=proc_result.has_udc,
                            param_defaults=_defaults_map,
                        )
                        _raise_if_cancel_requested(job_id)
                        instance = build_instance(
                            model,
                            str(csv_dir),
                            has_storage=proc_result.has_storage,
                            has_udc=proc_result.has_udc,
                        )
                        del model
                        gc.collect()
                        _raise_if_cancel_requested(job_id)
                        if level in {"presolve", "families"}:
                            enriched = _lp_progressive_method(instance, level)
                        else:
                            enrich_solution_dict(
                                solution_seed,
                                instance=instance,
                                csv_dir=str(csv_dir),
                                job_id=job_id,
                                on_phase=_on_diagnostic_phase,
                                analysis_level=level,
                            )
                            enriched = _selected_enrichment(solution_seed, level)
                else:
                    if job_snapshot["scenario_id"] is None:
                        raise RuntimeError(
                            "Job sin scenario_id ni CSV_UPLOAD; no hay entradas "
                            "para rebuild del modelo."
                        )
                    with tempfile.TemporaryDirectory(prefix="osemosys_diag_") as tmp_csv:
                        proc_result = run_data_processing(
                            db,
                            scenario_id=job_snapshot["scenario_id"],
                            csv_dir=tmp_csv,
                        )
                        _raise_if_cancel_requested(job_id)
                        solution_seed = {
                            "solver_name": job_snapshot["solver_name"],
                            "solver_status": job_snapshot["solver_status"],
                            "infeasibility_diagnostics": dict(
                                job_snapshot["diagnostics_seed"],
                            ),
                        }
                        if level == "structural":
                            enriched = _structural_only(solution_seed, tmp_csv)
                        elif level == "advanced":
                            enriched = _advanced_only(solution_seed, tmp_csv, db)
                        else:
                            model = create_abstract_model(
                                has_storage=proc_result.has_storage,
                                has_udc=proc_result.has_udc,
                                param_defaults=_defaults_map,
                            )
                            instance = build_instance(
                                model,
                                tmp_csv,
                                has_storage=proc_result.has_storage,
                                has_udc=proc_result.has_udc,
                            )
                            del model
                            gc.collect()
                            _raise_if_cancel_requested(job_id)
                            if level in {"presolve", "families"}:
                                enriched = _lp_progressive_method(instance, level)
                            else:
                                enrich_solution_dict(
                                    solution_seed,
                                    instance=instance,
                                    csv_dir=tmp_csv,
                                    job_id=job_id,
                                    on_phase=_on_diagnostic_phase,
                                    analysis_level=level,
                                )
                                enriched = _selected_enrichment(solution_seed, level)
            finally:
                reset_defaults_context(_defaults_token)
    except _DiagnosticCancelled as exc:
        was_cancelled = True
        error_message = str(exc) or "Cancelado por el usuario."
    except Exception as exc:  # pragma: no cover
        logger.exception("run_infeasibility_diagnostic_job falló para job %s", job_id)
        error_message = str(exc) or exc.__class__.__name__

    # 3) Persist result (o cancelación o fallo) + evento.
    with SessionLocal() as db:
        job = SimulationRepository.get_job_by_id(db, job_id=job_id)
        if not job:
            return
        diag = dict(job.infeasibility_diagnostics_json or {})
        now_iso = _utc_now_iso()
        if enriched is not None and error_message is None:
            diag.update(enriched)
            diag["diagnostic_status"] = "SUCCEEDED"
            diag["diagnostic_finished_at"] = now_iso
            diag.pop("diagnostic_error", None)
            diag.pop("diagnostic_cancel_requested", None)
            evt_type = "INFO"
            evt_msg = "Análisis de infactibilidad finalizado."
        elif was_cancelled:
            diag["diagnostic_status"] = "CANCELLED"
            diag["diagnostic_finished_at"] = now_iso
            diag["diagnostic_error"] = error_message or "Cancelado por el usuario."
            diag.pop("diagnostic_cancel_requested", None)
            evt_type = "WARN"
            evt_msg = "Diagnóstico de infactibilidad cancelado por el usuario."
        else:
            diag["diagnostic_status"] = "FAILED"
            diag["diagnostic_finished_at"] = now_iso
            diag["diagnostic_error"] = error_message or "Error desconocido"
            diag.pop("diagnostic_cancel_requested", None)
            evt_type = "ERROR"
            evt_msg = f"Análisis de infactibilidad falló: {diag['diagnostic_error']}"
        # Cálculo del tiempo total del diagnóstico (started → finished).
        try:
            from datetime import datetime as _dt  # noqa: WPS433
            started = diag.get("diagnostic_started_at")
            if started:
                t0 = _dt.fromisoformat(str(started))
                t1 = _dt.fromisoformat(now_iso)
                diag["diagnostic_seconds"] = max(0.0, (t1 - t0).total_seconds())
        except Exception:
            pass
        history = list(diag.get("diagnostic_history") or [])
        history.append(
            {
                "level": level,
                "status": diag["diagnostic_status"],
                "started_at": diag.get("diagnostic_started_at"),
                "finished_at": diag.get("diagnostic_finished_at"),
                "elapsed_seconds": diag.get("diagnostic_seconds"),
                "error": diag.get("diagnostic_error"),
            }
        )
        diag["diagnostic_history"] = history[-50:]
        job.infeasibility_diagnostics_json = diag
        SimulationRepository.add_event(
            db,
            job_id=job_id,
            event_type=evt_type,
            stage="infeasibility_analysis_complete",
            message=evt_msg,
            progress=job.progress,
        )
        db.commit()


@task_failure.connect
def handle_worker_lost_failure(
    sender=None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    args: tuple | None = None,
    **_: object,
) -> None:
    sender_name = getattr(sender, "name", None)
    if not _is_worker_lost_error(exception):
        return

    job_id: int | None = None
    if args and len(args) > 0 and isinstance(args[0], int):
        job_id = args[0]

    reason = (
        f"WorkerLostError detectado por Celery: {exception}. "
        "El proceso del worker fue terminado abruptamente."
    )

    if sender_name == run_infeasibility_diagnostic_job.name:
        if job_id is None:
            return
        from datetime import datetime, timezone

        with SessionLocal() as db:
            job = SimulationRepository.get_job_by_id(db, job_id=job_id)
            if not job:
                return
            diag = dict(job.infeasibility_diagnostics_json or {})
            if diag.get("diagnostic_status") != "RUNNING":
                return
            now = datetime.now(timezone.utc)
            diag["diagnostic_status"] = "FAILED"
            diag["diagnostic_error"] = reason
            diag["diagnostic_finished_at"] = now.isoformat()
            started = diag.get("diagnostic_started_at")
            if started:
                try:
                    t0 = datetime.fromisoformat(str(started))
                    if t0.tzinfo is None:
                        t0 = t0.replace(tzinfo=timezone.utc)
                    diag["diagnostic_seconds"] = max(
                        0.0, (now - t0).total_seconds()
                    )
                except ValueError:
                    pass
            job.infeasibility_diagnostics_json = diag
            SimulationRepository.add_event(
                db,
                job_id=job_id,
                event_type="ERROR",
                stage="infeasibility_analysis_worker_lost",
                message=reason,
                progress=job.progress,
            )
            db.commit()
        return

    if sender_name != run_simulation_job.name:
        return

    updated = _mark_failed_by_task_or_job_id(
        task_id=task_id,
        job_id=job_id,
        reason=reason,
    )
    if not updated:
        logger.warning(
            "No se encontró job RUNNING para task_id=%s job_id=%s tras WorkerLostError",
            task_id,
            job_id,
        )
    _dispatch_pending_jobs_safely()


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Garantizar transición consistente de estado de jobs desde la capa de worker.
#
# Posibles mejoras:
# - Incorporar idempotencia explícita por `celery_task_id` para retries/replays.
# - Añadir taxonomía de errores (solver, datos, infraestructura) para observabilidad.
#
# Riesgos en producción:
# - Fallos entre solve exitoso y commit final pueden dejar artefacto generado pero
#   estado no actualizado, generando incoherencia temporal.
# - Reintentos automáticos no configurados podrían ocultar fallos transitorios.
#
# Escalabilidad:
# - El throughput está limitado por CPU disponible y concurrencia del worker.
