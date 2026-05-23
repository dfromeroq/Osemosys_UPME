"""Seed de datos para ambiente local/desarrollo.

Este script inserta un set mínimo y consistente de datos para pruebas:
- Usuario `core.user` (auth)
- Catálogos en `osemosys` (parameter/region/technology/fuel/emission/solver)
- Un escenario base y permisos
- Ejemplos de `parameter_value`, `parameter_storage`
- Un `change_request` con su valor

Es idempotente a nivel lógico: antes de insertar, busca registros existentes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import json

from sqlalchemy import and_, select

# Permite ejecutar `python scripts/seed.py` sin depender de PYTHONPATH externo.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models import (
    ChangeRequest,
    ChangeRequestValue,
    DocumentType,
    Emission,
    Fuel,
    Parameter,
    ParameterStorage,
    ParameterValue,
    Region,
    OsemosysParamValue,
    Scenario,
    ScenarioPermission,
    SimulationBenchmark,
    SimulationJob,
    Solver,
    StorageSet,
    Timeslice,
    Technology,
    ModeOfOperation,
    Season,
    Daytype,
    Dailytimebracket,
    UdcSet,
    User,
)


def cleanup_demo_data(session) -> None:
    """Elimina escenarios y registros sintéticos heredados de seeds antiguos."""
    demo_scenarios = session.execute(
        select(Scenario).where(
            Scenario.owner == "seed",
            Scenario.name.in_(["EscenarioPlantilla", "EscenarioBase"]),
        )
    ).scalars().all()
    # Clean global parameter_value defaults
    pv_ids = session.execute(select(ParameterValue.id)).scalars().all()
    if pv_ids:
        session.query(ParameterStorage).filter(ParameterStorage.id_parameter_value.in_(pv_ids)).delete(
            synchronize_session=False
        )
        session.query(ParameterValue).delete(synchronize_session=False)

    for scenario in demo_scenarios:
        ov_ids = session.execute(
            select(OsemosysParamValue.id).where(OsemosysParamValue.id_scenario == scenario.id)
        ).scalars().all()
        if ov_ids:
            cr_ids = session.execute(
                select(ChangeRequest.id).where(ChangeRequest.id_osemosys_param_value.in_(ov_ids))
            ).scalars().all()
            if cr_ids:
                session.query(ChangeRequestValue).filter(
                    ChangeRequestValue.id_change_request.in_(cr_ids)
                ).delete(synchronize_session=False)
            session.query(ChangeRequest).filter(
                ChangeRequest.id_osemosys_param_value.in_(ov_ids)
            ).delete(synchronize_session=False)
        session.query(OsemosysParamValue).filter(
            OsemosysParamValue.id_scenario == scenario.id
        ).delete(synchronize_session=False)
        session.query(ScenarioPermission).filter(
            ScenarioPermission.id_scenario == scenario.id
        ).delete(synchronize_session=False)
        session.query(SimulationBenchmark).filter(
            SimulationBenchmark.scenario_name == scenario.name
        ).delete(synchronize_session=False)
        session.query(SimulationJob).filter(
            SimulationJob.scenario_id == scenario.id
        ).delete(synchronize_session=False)
        session.delete(scenario)


def get_or_create_by_name(session, model, name: str):
    """Obtiene un registro por `name` o lo crea si no existe."""
    obj = session.execute(select(model).where(model.name == name)).scalar_one_or_none()
    if obj:
        return obj
    obj = model(name=name)
    session.add(obj)
    session.flush()
    return obj


def get_or_create_by_code(session, model, code: str, description: str | None = None):
    obj = session.execute(select(model).where(model.code == code)).scalar_one_or_none()
    if obj:
        return obj
    obj = model(code=code, description=description)
    session.add(obj)
    session.flush()
    return obj


def upsert_osemosys_param(
    session,
    *,
    scenario_id: int,
    param_name: str,
    value: float,
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
    year: int | None = None,
) -> None:
    def _dim_condition(column, value):
        return column.is_(None) if value is None else column == value

    stmt = select(OsemosysParamValue).where(
        and_(
            OsemosysParamValue.id_scenario == scenario_id,
            OsemosysParamValue.param_name == param_name,
            _dim_condition(OsemosysParamValue.id_region, id_region),
            _dim_condition(OsemosysParamValue.id_technology, id_technology),
            _dim_condition(OsemosysParamValue.id_fuel, id_fuel),
            _dim_condition(OsemosysParamValue.id_emission, id_emission),
            _dim_condition(OsemosysParamValue.id_timeslice, id_timeslice),
            _dim_condition(OsemosysParamValue.id_mode_of_operation, id_mode_of_operation),
            _dim_condition(OsemosysParamValue.id_season, id_season),
            _dim_condition(OsemosysParamValue.id_daytype, id_daytype),
            _dim_condition(OsemosysParamValue.id_dailytimebracket, id_dailytimebracket),
            _dim_condition(OsemosysParamValue.id_storage_set, id_storage_set),
            _dim_condition(OsemosysParamValue.id_udc_set, id_udc_set),
            _dim_condition(OsemosysParamValue.year, year),
        )
    )
    obj = session.execute(stmt).scalar_one_or_none()
    if obj:
        obj.value = float(value)
        return
    session.add(
        OsemosysParamValue(
            id_scenario=scenario_id,
            param_name=param_name,
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
            year=year,
            value=float(value),
        )
    )


def main() -> None:
    """Ejecuta el seed dentro de una única transacción."""
    with SessionLocal() as session:
        # Catálogo core: tipos de documento
        dt_cc = session.execute(
            select(DocumentType).where(DocumentType.code == "CC")
        ).scalar_one_or_none()
        if not dt_cc:
            dt_cc = DocumentType(code="CC", name="Cédula de ciudadanía")
            session.add(dt_cc)
            session.flush()

        dt_pp = session.execute(
            select(DocumentType).where(DocumentType.code == "PASSPORT")
        ).scalar_one_or_none()
        if not dt_pp:
            dt_pp = DocumentType(code="PASSPORT", name="Pasaporte")
            session.add(dt_pp)
            session.flush()

        # Usuario core
        user = session.execute(
            select(User).where(User.username == "seed")
        ).scalar_one_or_none()
        if not user:
            user = User(
                email="seed@example.com",
                username="seed",
                hashed_password=get_password_hash("seed1234"),
                document_number="1234567890",
                document_type_id=dt_cc.id,
                is_active=True,
                can_manage_catalogs=True,
                can_import_official_data=True,
                can_manage_users=True,
                can_manage_scenarios=True,
                is_admin_reports=True,
            )
            session.add(user)
            session.flush()
        else:
            # Mantiene credencial de prueba consistente tras cambios de algoritmo hash.
            user.hashed_password = get_password_hash("seed1234")
            if user.document_type_id is None:
                user.document_type_id = dt_cc.id
            if not user.document_number:
                user.document_number = "1234567890"
            user.is_active = True
            user.can_manage_catalogs = True
            user.can_import_official_data = True
            user.can_manage_users = True
            user.can_manage_scenarios = True
            user.is_admin_reports = True
            session.flush()

        cleanup_demo_data(session)

        from app.result_table_seeds import ensure_result_table_seeds

        n_rt_tables = ensure_result_table_seeds(session)

        # A partir de este punto no se siembran datos de ejemplo del modelo.
        # Los datos iniciales deben ingresar únicamente por "Carga oficial".
        session.commit()
        print("Seed mínimo completado (usuario/permisos).")
        if n_rt_tables:
            print(f"  Plantillas de tabla de resultados: +{n_rt_tables} nueva(s).")
        return

        # Catálogos mínimos
        p_demand = get_or_create_by_name(session, Parameter, "Demand")
        p_cost = get_or_create_by_name(session, Parameter, "Cost")

        r_col = get_or_create_by_name(session, Region, "COL")
        r_ant = get_or_create_by_name(session, Region, "ANT")

        t_solar = get_or_create_by_name(session, Technology, "SolarPV")
        f_gas = get_or_create_by_name(session, Fuel, "NaturalGas")
        e_co2 = get_or_create_by_name(session, Emission, "CO2")

        s_default = get_or_create_by_name(session, Solver, "default")
        ts_day = get_or_create_by_code(session, Timeslice, "DAY", "Bloque día")
        moo_default = get_or_create_by_code(
            session, ModeOfOperation, "M1", "Modo de operación principal"
        )
        season_all = get_or_create_by_code(session, Season, "S1", "Única estación")
        daytype_all = get_or_create_by_code(session, Daytype, "D1", "Único tipo de día")
        dtb_all = get_or_create_by_code(
            session, Dailytimebracket, "H1", "Único bloque horario"
        )
        storage_battery = get_or_create_by_code(
            session, StorageSet, "BATTERY", "Almacenamiento batería"
        )
        udc_cap = get_or_create_by_code(
            session, UdcSet, "UDC_CAP", "Límite agregado de actividad"
        )

        # Escenario plantilla (base de parameter_value para nuevos escenarios)
        template_scenario = session.execute(
            select(Scenario).where(Scenario.name == "EscenarioPlantilla", Scenario.owner == "seed")
        ).scalar_one_or_none()
        if not template_scenario:
            template_scenario = Scenario(
                name="EscenarioPlantilla",
                description="Plantilla base para inicializar escenarios",
                owner="seed",
                edit_policy="OWNER_ONLY",
                is_template=True,
            )
            session.add(template_scenario)
            session.flush()

        # Permisos
        perm = session.execute(
            select(ScenarioPermission).where(
                ScenarioPermission.id_scenario == template_scenario.id,
                ScenarioPermission.user_identifier == "user:seed",
            )
        ).scalar_one_or_none()
        if not perm:
            session.add(
                ScenarioPermission(
                    id_scenario=template_scenario.id,
                    user_identifier="user:seed",
                    user_id=user.id,
                    can_edit_direct=True,
                    can_propose=True,
                    can_manage_values=True,
                )
            )

        # ParameterValue defaults (global, sin escenario)
        pv_demand = session.execute(
            select(ParameterValue).where(
                ParameterValue.id_parameter == p_demand.id,
                ParameterValue.id_region == r_col.id,
                ParameterValue.year == 2025,
                ParameterValue.id_solver == s_default.id,
            )
        ).scalar_one_or_none()
        if not pv_demand:
            pv_demand = ParameterValue(
                id_parameter=p_demand.id,
                id_region=r_col.id,
                id_solver=s_default.id,
                mode_of_operation=False,
                year=2025,
                value=123.45,
                unit="GWh",
            )
            session.add(pv_demand)
            session.flush()

        pv_cost = session.execute(
            select(ParameterValue).where(
                ParameterValue.id_parameter == p_cost.id,
                ParameterValue.id_region == r_ant.id,
                ParameterValue.id_technology == t_solar.id,
                ParameterValue.id_fuel == f_gas.id,
                ParameterValue.id_emission == e_co2.id,
                ParameterValue.year == 2025,
                ParameterValue.id_solver == s_default.id,
            )
        ).scalar_one_or_none()
        if not pv_cost:
            pv_cost = ParameterValue(
                id_parameter=p_cost.id,
                id_region=r_ant.id,
                id_technology=t_solar.id,
                id_fuel=f_gas.id,
                id_emission=e_co2.id,
                id_solver=s_default.id,
                mode_of_operation=True,
                year=2025,
                value=9.99,
                unit="USD",
            )
            session.add(pv_cost)
            session.flush()

        # Escenario de trabajo inicial (no plantilla), clonado desde plantilla.
        work_scenario = session.execute(
            select(Scenario).where(Scenario.name == "EscenarioBase", Scenario.owner == "seed")
        ).scalar_one_or_none()
        if not work_scenario:
            work_scenario = Scenario(
                name="EscenarioBase",
                description="Escenario operativo para pruebas",
                owner="seed",
                edit_policy="OWNER_ONLY",
                is_template=False,
            )
            session.add(work_scenario)
            session.flush()

        work_perm = session.execute(
            select(ScenarioPermission).where(
                ScenarioPermission.id_scenario == work_scenario.id,
                ScenarioPermission.user_identifier == "user:seed",
            )
        ).scalar_one_or_none()
        if not work_perm:
            session.add(
                ScenarioPermission(
                    id_scenario=work_scenario.id,
                    user_identifier="user:seed",
                    user_id=user.id,
                    can_edit_direct=True,
                    can_propose=True,
                    can_manage_values=True,
                )
            )

        # parameter_value is now global (no per-scenario duplication needed).
        # The work scenario gets its data in osemosys_param_value via the create flow.

        # Parámetros multidimensionales OSEMOSYS (normal + storage + UDC).
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="VariableCost",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            year=2025,
            value=0.15,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="CapacityFactor",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            id_timeslice=ts_day.id,
            year=2025,
            value=0.35,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="AvailabilityFactor",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            year=2025,
            value=0.95,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="CapacityToActivityUnit",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            year=2025,
            value=1.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="ResidualCapacity",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            year=2025,
            value=500.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="CapitalCost",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            year=2025,
            value=3.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="FixedCost",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            year=2025,
            value=0.1,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="TotalAnnualMaxCapacity",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            year=2025,
            value=700.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="TotalAnnualMaxCapacityInvestment",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            year=2025,
            value=300.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="EmissionActivityRatio",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            id_emission=e_co2.id,
            id_mode_of_operation=moo_default.id,
            year=2025,
            value=0.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="AnnualEmissionLimit",
            id_region=r_ant.id,
            id_emission=e_co2.id,
            year=2025,
            value=1_000_000.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="ReserveMargin",
            id_region=r_ant.id,
            year=2025,
            value=1.15,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="REMinProductionTarget",
            id_region=r_ant.id,
            year=2025,
            value=0.20,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="RETagTechnology",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            year=2025,
            value=1.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="TechnologyToStorage",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            id_storage_set=storage_battery.id,
            id_mode_of_operation=moo_default.id,
            value=1.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="TechnologyFromStorage",
            id_region=r_ant.id,
            id_technology=t_solar.id,
            id_storage_set=storage_battery.id,
            id_mode_of_operation=moo_default.id,
            value=1.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="StorageMaxChargeRate",
            id_region=r_ant.id,
            id_storage_set=storage_battery.id,
            value=500.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="StorageMaxDischargeRate",
            id_region=r_ant.id,
            id_storage_set=storage_battery.id,
            value=500.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="UDCConstant",
            id_region=r_ant.id,
            id_udc_set=udc_cap.id,
            year=2025,
            value=5_000.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="YearSplit",
            id_timeslice=ts_day.id,
            year=2025,
            value=1.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="DaysInDayType",
            id_season=season_all.id,
            id_daytype=daytype_all.id,
            year=2025,
            value=365.0,
        )
        upsert_osemosys_param(
            session,
            scenario_id=work_scenario.id,
            param_name="DaySplit",
            id_dailytimebracket=dtb_all.id,
            year=2025,
            value=1.0,
        )

        # 1:1 storage (solo para uno)
        storage = session.execute(
            select(ParameterStorage).where(ParameterStorage.id_parameter_value == pv_cost.id)
        ).scalar_one_or_none()
        if not storage:
            session.add(
                ParameterStorage(
                    id_parameter_value=pv_cost.id,
                    timesline=1,
                    daytype=1,
                    season=1,
                    dailytimebracket=1,
                )
            )

        # Change request + valores
        cr = session.execute(
            select(ChangeRequest).where(
                ChangeRequest.id_parameter_value == pv_cost.id,
                ChangeRequest.created_by == "seed",
                ChangeRequest.status == "PENDING",
            )
        ).scalar_one_or_none()
        if not cr:
            cr = ChangeRequest(
                id_parameter_value=pv_cost.id,
                created_by="seed",
                status="PENDING",
            )
            session.add(cr)
            session.flush()

        crv = session.execute(
            select(ChangeRequestValue).where(ChangeRequestValue.id_change_request == cr.id)
        ).scalar_one_or_none()
        if not crv:
            session.add(
                ChangeRequestValue(
                    id_change_request=cr.id,
                    old_value=9.99,
                    new_value=10.50,
                )
            )

        # Benchmark base para validación numérica.
        benchmark = session.execute(
            select(SimulationBenchmark).where(
                SimulationBenchmark.benchmark_key == "base_2025",
                SimulationBenchmark.scenario_name == work_scenario.name,
            )
        ).scalar_one_or_none()
        if not benchmark:
            session.add(
                SimulationBenchmark(
                    benchmark_key="base_2025",
                    scenario_name=work_scenario.name,
                    source="notebook",
                    objective_value=185175.0,
                    metrics_json=json.dumps(
                        {
                            "objective_value": 185175.0,
                            "coverage_ratio": 0.0,
                            "total_demand": 123.45,
                            "total_unmet": 123.45,
                        }
                    ),
                )
            )
        else:
            benchmark.source = "notebook"
            benchmark.objective_value = 185175.0
            benchmark.metrics_json = json.dumps(
                {
                    "objective_value": 185175.0,
                    "coverage_ratio": 0.0,
                    "total_demand": 123.45,
                    "total_unmet": 123.45,
                }
            )

        session.commit()

    print("Seed completado.")


if __name__ == "__main__":
    main()


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Sembrar datos mínimos reproducibles para desarrollo/integración.
#
# Posibles mejoras:
# - Separar seed por dominios y soportar perfiles (`minimal`, `benchmark`, `full`).
#
# Riesgos en producción:
# - No ejecutar en entornos productivos sin controles; puede introducir datos sintéticos.
#
# Escalabilidad:
# - I/O-bound sobre BD; tiempo crece con cantidad de upserts.

