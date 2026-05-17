"""Tests de configuración global de series (alta manual y conflictos)."""

from __future__ import annotations

import pytest

from app.core.exceptions import ConflictError
from app.models import ChartSeriesConfig
from app.services.chart_series_config_service import create_config
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
