"""Tests de configuración global de series (alta manual y conflictos)."""

from __future__ import annotations

import pytest

from app.core.exceptions import ConflictError
from app.models import ChartSeriesConfig
from app.services.chart_series_config_service import (
    apply_global_series_config,
    create_config,
    update_config,
)
from tests.factories import create_user


def test_create_config_manual_row(db_session):
    admin = create_user(db_session, username="csr_admin", is_admin_reports=True)
    row = create_config(
        db_session,
        tipo="elec_produccion",
        agrupar_por="TECNOLOGIA",
        cfg_default_agrupar="TECNOLOGIA",
        series_code="PWRTEST99",
        display_name="Tecnología de prueba",
        color="#aabbcc",
        hidden=False,
        sort_index=None,
        group_key="Otras",
        notes=None,
        current_user=admin,
    )
    assert row.id > 0
    assert row.series_code == "PWRTEST99"
    assert row.display_name == "Tecnología de prueba"
    assert row.agrupar_por == "TECNOLOGIA"


def test_create_config_duplicate_raises(db_session):
    admin = create_user(db_session, username="csr_admin2", is_admin_reports=True)
    body = dict(
        tipo="capacidad_instalada",
        agrupar_por="TECNOLOGIA",
        cfg_default_agrupar="TECNOLOGIA",
        series_code="DUPE01",
        display_name="Uno",
        color=None,
        hidden=False,
        sort_index=5,
        group_key=None,
        notes=None,
        current_user=admin,
    )
    create_config(db_session, **body)
    with pytest.raises(ConflictError):
        create_config(db_session, **body)


def test_apply_global_series_config_uses_is_global_cross_type(db_session):
    admin = create_user(db_session, username="csr_global", is_admin_reports=True)
    global_row = create_config(
        db_session,
        tipo="elec_produccion",
        agrupar_por="TECNOLOGIA",
        cfg_default_agrupar="TECNOLOGIA",
        series_code="PWRCROSS",
        display_name="Nombre global",
        color="#112233",
        hidden=False,
        sort_index=0,
        group_key=None,
        notes=None,
        current_user=admin,
    )
    update_config(
        db_session,
        row_id=global_row.id,
        data={"is_global": True},
        current_user=admin,
    )

    out = apply_global_series_config(
        db_session,
        tipo="capacidad_instalada",
        agrupar_por="TECNOLOGIA",
        orden_color=["PWRCROSS", "OTHER"],
        color_dict={"PWRCROSS": "#000000", "OTHER": "#ffffff"},
        default_name=lambda x: str(x),
    )
    assert len(out) == 2
    assert out[0][0] == "PWRCROSS"
    assert out[0][1] == "#112233"
    assert out[0][2] == "Nombre global"


def test_apply_global_series_config_local_overrides_global(db_session):
    admin = create_user(db_session, username="csr_local", is_admin_reports=True)
    global_row = create_config(
        db_session,
        tipo="elec_produccion",
        agrupar_por="TECNOLOGIA",
        cfg_default_agrupar="TECNOLOGIA",
        series_code="PWROVR",
        display_name="Global",
        color="#111111",
        hidden=False,
        sort_index=0,
        group_key=None,
        notes=None,
        current_user=admin,
    )
    update_config(
        db_session,
        row_id=global_row.id,
        data={"is_global": True},
        current_user=admin,
    )
    create_config(
        db_session,
        tipo="capacidad_instalada",
        agrupar_por="TECNOLOGIA",
        cfg_default_agrupar="TECNOLOGIA",
        series_code="PWROVR",
        display_name="Local",
        color="#222222",
        hidden=False,
        sort_index=0,
        group_key=None,
        notes=None,
        current_user=admin,
    )

    out = apply_global_series_config(
        db_session,
        tipo="capacidad_instalada",
        agrupar_por="TECNOLOGIA",
        orden_color=["PWROVR"],
        color_dict={"PWROVR": "#000000"},
        default_name=lambda x: str(x),
    )
    assert out[0][1] == "#222222"
    assert out[0][2] == "Local"
