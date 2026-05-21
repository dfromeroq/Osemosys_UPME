from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import (
    DocumentType,
    OsemosysParamValue,
    Region,
    Scenario,
    ScenarioPermission,
    User,
)


def create_user(
    db: Session,
    *,
    username: str,
    can_manage_catalogs: bool = False,
    can_import_official_data: bool = False,
    can_manage_users: bool = False,
    is_admin_reports: bool = False,
    can_manage_scenarios: bool = False,
) -> User:
    doc_type = DocumentType(code=f"CC-{username}", name=f"Cedula {username}")
    user = User(
        id=uuid.uuid4(),
        email=f"{username}@example.com",
        username=username,
        hashed_password="hashed",
        document_number=f"doc-{username}",
        document_type_id=None,
        is_active=True,
        can_manage_catalogs=can_manage_catalogs,
        can_import_official_data=can_import_official_data,
        can_manage_users=can_manage_users,
        is_admin_reports=is_admin_reports,
        can_manage_scenarios=can_manage_scenarios,
    )
    db.add(doc_type)
    db.flush()
    user.document_type_id = doc_type.id
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_scenario(
    db: Session,
    *,
    name: str,
    owner: str,
    edit_policy: str = "OWNER_ONLY",
    description: str | None = None,
    base_scenario_id: int | None = None,
    simulation_type: str = "NATIONAL",
    processing_mode: str = "STANDARD",
) -> Scenario:
    scenario = Scenario(
        name=name,
        description=description,
        owner=owner,
        edit_policy=edit_policy,
        simulation_type=simulation_type,
        processing_mode=processing_mode,
        is_template=False,
        base_scenario_id=base_scenario_id,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario


def create_permission(
    db: Session,
    *,
    scenario_id: int,
    user: User,
    can_edit_direct: bool = False,
    can_propose: bool = False,
    can_manage_values: bool = False,
) -> ScenarioPermission:
    permission = ScenarioPermission(
        id_scenario=scenario_id,
        user_identifier=f"user:{user.username}",
        user_id=user.id,
        can_edit_direct=can_edit_direct,
        can_propose=can_propose,
        can_manage_values=can_manage_values,
    )
    db.add(permission)
    db.commit()
    db.refresh(permission)
    return permission


def create_region(db: Session, *, name: str) -> Region:
    region = Region(name=name, is_active=True)
    db.add(region)
    db.commit()
    db.refresh(region)
    return region


def create_osemosys_value(
    db: Session,
    *,
    scenario_id: int,
    param_name: str,
    value: float,
    year: int | None = None,
    id_region: int | None = None,
    id_technology: int | None = None,
    id_fuel: int | None = None,
    id_emission: int | None = None,
    id_timeslice: int | None = None,
    id_mode_of_operation: int | None = None,
    id_season: int | None = None,
    id_daytype: int | None = None,
    id_dailytimebracket: int | None = None,
    id_storage_set: int | None = None,
    id_udc_set: int | None = None,
) -> OsemosysParamValue:
    row = OsemosysParamValue(
        id_scenario=scenario_id,
        param_name=param_name,
        value=value,
        year=year,
        id_region=id_region,
        id_technology=id_technology,
        id_fuel=id_fuel,
        id_emission=id_emission,
        id_timeslice=id_timeslice,
        id_mode_of_operation=id_mode_of_operation,
        id_season=id_season,
        id_daytype=id_daytype,
        id_dailytimebracket=id_dailytimebracket,
        id_storage_set=id_storage_set,
        id_udc_set=id_udc_set,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
