from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.scenarios import (
    delete_scenario,
    detach_scenario_children,
    get_scenario_delete_impact,
)
from app.api.v1.simulations import delete_simulation
from app.models import (
    ChangeRequest,
    ChangeRequestValue,
    DeletionLog,
    OsemosysOutputParamValue,
    OsemosysParamValue,
    OsemosysParamValueAudit,
    Scenario,
    ScenarioOperationJob,
    ScenarioPermission,
    SimulationJob,
    SimulationJobEvent,
    SimulationJobFavorite,
)
from app.schemas.scenario import ScenarioDetachChildrenRequest
from app.services.scenario_operation_service import ScenarioOperationService

from factories import create_osemosys_value, create_permission, create_scenario, create_user


def test_delete_scenario_cleans_dependents_and_writes_audit_log(db_session, monkeypatch) -> None:
    monkeypatch.setattr(ScenarioOperationService, "_enqueue_job", staticmethod(lambda db, *, job_id: None))
    owner = create_user(db_session, username="scenario-owner")
    scenario = create_scenario(db_session, name="Scenario to delete", owner=owner.username)
    permission = create_permission(db_session, scenario_id=scenario.id, user=owner)
    value = create_osemosys_value(
        db_session,
        scenario_id=scenario.id,
        param_name="CapitalCost",
        year=2030,
        value=10.0,
    )
    change_request = ChangeRequest(
        id_osemosys_param_value=value.id,
        created_by=owner.username,
        status="PENDING",
    )
    job = SimulationJob(
        user_id=owner.id,
        scenario_id=scenario.id,
        solver_name="highs",
        status="SUCCEEDED",
        progress=100.0,
    )
    db_session.add_all([change_request, job])
    db_session.flush()
    audit = OsemosysParamValueAudit(
        id_scenario=scenario.id,
        param_name=value.param_name,
        id_osemosys_param_value=value.id,
        action="UPDATE",
        old_value=9.0,
        new_value=10.0,
        source="API",
        changed_by=owner.username,
    )
    change_value = ChangeRequestValue(
        id_change_request=change_request.id,
        old_value=10.0,
        new_value=12.0,
    )
    output = OsemosysOutputParamValue(
        id_simulation_job=job.id,
        variable_name="TotalDiscountedCost",
        value=1.0,
    )
    event = SimulationJobEvent(job_id=job.id, event_type="INFO", stage="done")
    favorite = SimulationJobFavorite(user_id=owner.id, job_id=job.id)
    db_session.add_all([audit, change_value, output, event, favorite])
    db_session.commit()
    scenario_id = scenario.id
    job_id = job.id
    value_id = value.id
    output_id = output.id
    event_id = event.id
    permission_id = permission.id
    audit_id = audit.id
    change_request_id = change_request.id
    change_value_id = change_value.id

    response = delete_scenario(scenario.id, db=db_session, current_user=owner)

    assert response["operation_type"] == "DELETE_SCENARIO"
    assert response["status"] == "QUEUED"
    assert response["scenario_id"] == scenario_id
    assert response["scenario_name"] == "Scenario to delete"
    assert db_session.get(Scenario, scenario_id) is not None
    assert db_session.get(SimulationJob, job_id) is not None

    ScenarioOperationService.execute_job(db_session, job_id=response["id"])
    db_session.expire_all()

    assert db_session.get(SimulationJob, job_id) is None
    assert db_session.get(OsemosysOutputParamValue, output_id) is None
    assert db_session.get(SimulationJobEvent, event_id) is None
    assert db_session.get(SimulationJobFavorite, (owner.id, job_id)) is None
    assert db_session.get(ChangeRequestValue, change_value_id) is None
    assert db_session.get(ChangeRequest, change_request_id) is None
    assert db_session.get(ScenarioPermission, permission_id) is None
    assert db_session.get(OsemosysParamValue, value_id) is None
    assert db_session.get(OsemosysParamValueAudit, audit_id) is None
    assert db_session.get(DeletionLog, 1) is not None

    logs = db_session.query(DeletionLog).order_by(DeletionLog.entity_type).all()
    assert {log.entity_type for log in logs} == {"SCENARIO", "SIMULATION_JOB"}
    scenario_log = next(log for log in logs if log.entity_type == "SCENARIO")
    assert scenario_log.entity_id == scenario_id
    assert scenario_log.details_json["deleted_change_request_ids"] == [change_request_id]
    assert scenario_log.details_json["cascaded_simulation_job_ids"] == [job_id]
    operation_job = db_session.get(ScenarioOperationJob, response["id"])
    assert operation_job is not None
    assert operation_job.status == "SUCCEEDED"
    assert operation_job.result_json["deleted"] is True


def test_delete_scenario_blocks_direct_children_before_deleting_data(db_session) -> None:
    owner = create_user(db_session, username="parent-owner")
    parent = create_scenario(db_session, name="Parent scenario", owner=owner.username)
    child = create_scenario(
        db_session,
        name="Child scenario",
        owner=owner.username,
        base_scenario_id=parent.id,
    )
    parent_value = create_osemosys_value(
        db_session,
        scenario_id=parent.id,
        param_name="CapitalCost",
        year=2030,
        value=10.0,
    )
    db_session.commit()
    parent_id = parent.id
    child_id = child.id
    parent_value_id = parent_value.id

    with pytest.raises(HTTPException) as exc:
        delete_scenario(parent_id, db=db_session, current_user=owner)

    assert exc.value.status_code == 409
    assert "escenarios derivados" in exc.value.detail
    assert db_session.get(OsemosysParamValue, parent_value_id) is not None
    assert db_session.get(DeletionLog, 1) is None


def test_detach_scenario_children_allows_parent_delete(db_session, monkeypatch) -> None:
    monkeypatch.setattr(ScenarioOperationService, "_enqueue_job", staticmethod(lambda db, *, job_id: None))
    owner = create_user(db_session, username="detach-owner")
    parent = create_scenario(db_session, name="Parent scenario", owner=owner.username)
    child = create_scenario(
        db_session,
        name="Child scenario",
        owner=owner.username,
        base_scenario_id=parent.id,
    )
    db_session.commit()
    parent_id = parent.id
    child_id = child.id

    impact = get_scenario_delete_impact(parent_id, db=db_session, current_user=owner)

    assert impact["scenario_id"] == parent_id
    assert [item["id"] for item in impact["direct_children"]] == [child_id]

    response = detach_scenario_children(
        parent_id,
        ScenarioDetachChildrenRequest(child_ids=[child_id]),
        db=db_session,
        current_user=owner,
    )

    assert response == {"detached_child_ids": [child_id]}
    db_session.refresh(child)
    assert child.base_scenario_id is None

    response = delete_scenario(parent_id, db=db_session, current_user=owner)

    assert response["operation_type"] == "DELETE_SCENARIO"
    assert response["status"] == "QUEUED"
    assert db_session.get(type(parent), parent_id) is not None

    ScenarioOperationService.execute_job(db_session, job_id=response["id"])
    db_session.expire_all()

    assert db_session.get(type(parent), parent_id) is None
    assert db_session.get(type(child), child_id) is not None


def test_delete_simulation_blocks_active_jobs_and_deletes_results_for_admin(db_session) -> None:
    owner = create_user(db_session, username="job-owner")
    admin = create_user(db_session, username="scenario-admin")
    admin.can_manage_scenarios = True
    scenario = create_scenario(db_session, name="Simulation scenario", owner=owner.username)
    running_job = SimulationJob(
        user_id=owner.id,
        scenario_id=scenario.id,
        solver_name="highs",
        status="RUNNING",
        progress=50.0,
    )
    finished_job = SimulationJob(
        user_id=owner.id,
        scenario_id=scenario.id,
        solver_name="highs",
        status="SUCCEEDED",
        progress=100.0,
    )
    db_session.add_all([admin, running_job, finished_job])
    db_session.flush()
    output = OsemosysOutputParamValue(
        id_simulation_job=finished_job.id,
        variable_name="TotalCapacityAnnual",
        value=42.0,
    )
    event = SimulationJobEvent(job_id=finished_job.id, event_type="INFO", stage="done")
    favorite = SimulationJobFavorite(user_id=owner.id, job_id=finished_job.id)
    db_session.add_all([output, event, favorite])
    db_session.commit()
    running_job_id = running_job.id
    finished_job_id = finished_job.id
    output_id = output.id
    event_id = event.id

    with pytest.raises(HTTPException) as exc:
        delete_simulation(running_job_id, db=db_session, current_user=admin)
    assert exc.value.status_code == 409

    delete_simulation(finished_job_id, db=db_session, current_user=admin)

    assert db_session.get(SimulationJob, finished_job_id) is None
    assert db_session.get(OsemosysOutputParamValue, output_id) is None
    assert db_session.get(SimulationJobEvent, event_id) is None
    assert db_session.get(SimulationJobFavorite, (owner.id, finished_job_id)) is None

    log = db_session.query(DeletionLog).one()
    assert log.entity_type == "SIMULATION_JOB"
    assert log.entity_id == finished_job_id
    assert log.deleted_by_username == admin.username
