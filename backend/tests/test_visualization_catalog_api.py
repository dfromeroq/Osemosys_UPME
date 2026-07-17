"""Tests del servicio de catálogo de visualización."""

from __future__ import annotations

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.services import visualization_catalog_service as svc
from tests.factories import create_user


@pytest.fixture
def admin(db_session):
    return create_user(db_session, username="cat_admin", is_admin_reports=True)


def test_get_form_options(db_session):
    opts = svc.get_form_options(db_session)
    assert "grouping_axes" in opts
    assert "tecnologias" in opts["color_fn_keys"]
    assert len(opts["modules"]) >= 1


def test_label_crud(db_session, admin):
    created = svc.create_label(
        db_session,
        data={"code": "TEST_LBL_X", "label_es": "Prueba", "label_en": "Test", "category": "technology"},
        current_user=admin,
    )
    assert created.id > 0
    page = svc.list_labels(db_session, q="TEST_LBL_X", page=1, page_size=10)
    assert page["total"] >= 1
    updated = svc.update_label(
        db_session,
        row_id=created.id,
        data={"label_es": "Actualizado"},
        current_user=admin,
    )
    assert updated.label_es == "Actualizado"
    svc.delete_label(db_session, row_id=created.id, current_user=admin)
    with pytest.raises(NotFoundError):
        svc.update_label(db_session, row_id=created.id, data={"label_es": "x"}, current_user=admin)


def test_label_duplicate_raises(db_session, admin):
    svc.create_label(
        db_session,
        data={"code": "DUP_LBL", "label_es": "Uno"},
        current_user=admin,
    )
    with pytest.raises(ConflictError):
        svc.create_label(
            db_session,
            data={"code": "DUP_LBL", "label_es": "Dos"},
            current_user=admin,
        )


def test_color_crud(db_session, admin):
    row = svc.create_color(
        db_session,
        data={"group": "fuel", "key": "TEST_COLOR_X", "color_hex": "#aabbcc", "sort_order": 99},
        current_user=admin,
    )
    assert row.color_hex == "#aabbcc"
    updated = svc.update_color(
        db_session,
        row_id=row.id,
        data={"color_hex": "#112233"},
        current_user=admin,
    )
    assert updated.color_hex == "#112233"
    svc.delete_color(db_session, row_id=row.id, current_user=admin)


def test_filter_group_crud_and_import(db_session, admin):
    grp = svc.create_filter_group(
        db_session,
        data={
            "code": "TEST_GRP_X",
            "name": "Grupo prueba",
            "filter_mode": "TECH_ONLY",
            "members": [{"value": "PWRSOL", "operation": "INCLUDE", "entity_type": "TECHNOLOGY"}],
        },
        current_user=admin,
    )
    assert grp.code == "TEST_GRP_X"
    assert len(grp.members) == 1

    parsed = svc.parse_members_import_text("PWRWIND\nPWRCSPV", filter_mode="TECH_ONLY")
    assert len(parsed) == 2

    merged = svc.import_filter_group_members(
        db_session,
        code="TEST_GRP_X",
        text="PWRWIND",
        mode="merge",
        current_user=admin,
    )
    assert len(merged.members) >= 2

    svc.delete_filter_group(db_session, code="TEST_GRP_X", current_user=admin)
    with pytest.raises(NotFoundError):
        svc.get_filter_group(db_session, code="TEST_GRP_X")


def test_chart_config_crud(db_session, admin):
    mod = svc.get_form_options(db_session)["modules"][0]
    created = svc.create_chart_config(
        db_session,
        data={
            "tipo": "test_chart_x",
            "module_id": mod["id"],
            "label_titulo": "Gráfica test",
            "variable_default": "Dispatch",
            "agrupar_por_default": "TECNOLOGIA",
            "agrupaciones_permitidas_json": ["TECNOLOGIA", "FUEL"],
            "color_fn_key": "tecnologias",
            "flags_json": {"soporta_pareto": True},
        },
        current_user=admin,
    )
    assert created.tipo == "test_chart_x"
    detail = svc.get_chart_config(db_session, tipo="test_chart_x")
    assert detail.agrupaciones_permitidas_json == ["TECNOLOGIA", "FUEL"]

    svc.update_chart_config(
        db_session,
        tipo="test_chart_x",
        data={"label_titulo": "Título nuevo", "agrupar_por_default": "FUEL"},
        current_user=admin,
    )
    updated = svc.get_chart_config(db_session, tipo="test_chart_x")
    assert updated.label_titulo == "Título nuevo"
    assert updated.agrupar_por_default == "FUEL"

    svc.delete_chart_config(db_session, tipo="test_chart_x", current_user=admin)
    with pytest.raises(NotFoundError):
        svc.get_chart_config(db_session, tipo="test_chart_x")
