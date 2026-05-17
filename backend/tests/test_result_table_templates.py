"""Tests del servicio de plantillas de tablas de resultados."""

from __future__ import annotations

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models import ResultTableTemplate
from app.services.result_table_template_service import ResultTableTemplateService
from tests.factories import create_user


def test_list_enabled_only_active_ordered(db_session):
    admin = create_user(db_session, username="admin1", is_admin_reports=True)
    ResultTableTemplateService.create(
        db_session,
        current_user=admin,
        data={
            "name": "A",
            "tipo": "capacidad_instalada",
            "un": "PJ",
            "is_enabled": True,
            "sort_order": 10,
        },
    )
    ResultTableTemplateService.create(
        db_session,
        current_user=admin,
        data={
            "name": "B",
            "tipo": "capacidad_instalada",
            "un": "PJ",
            "is_enabled": False,
            "sort_order": 0,
        },
    )
    rows = ResultTableTemplateService.list_enabled(db_session)
    assert len(rows) == 1
    assert rows[0].name == "A"


def test_create_forbidden_without_admin(db_session):
    user = create_user(db_session, username="plain")
    with pytest.raises(ForbiddenError):
        ResultTableTemplateService.create(
            db_session,
            current_user=user,
            data={"name": "x", "tipo": "capacidad_instalada", "un": "PJ"},
        )


def test_get_disabled_hidden_from_non_admin(db_session):
    admin = create_user(db_session, username="admin2", is_admin_reports=True)
    row = ResultTableTemplateService.create(
        db_session,
        current_user=admin,
        data={
            "name": "Off",
            "tipo": "capacidad_instalada",
            "un": "PJ",
            "is_enabled": False,
        },
    )
    plain = create_user(db_session, username="plain2")
    with pytest.raises(NotFoundError):
        ResultTableTemplateService.get(db_session, row.id, current_user=plain)


def test_reorder_updates_sort_order(db_session):
    admin = create_user(db_session, username="admin3", is_admin_reports=True)
    a = ResultTableTemplateService.create(
        db_session,
        current_user=admin,
        data={"name": "first", "tipo": "capacidad_instalada", "un": "PJ"},
    )
    b = ResultTableTemplateService.create(
        db_session,
        current_user=admin,
        data={"name": "second", "tipo": "capacidad_instalada", "un": "PJ"},
    )
    ResultTableTemplateService.reorder(
        db_session, current_user=admin, ordered_ids=[b.id, a.id]
    )
    db_session.expire_all()
    a2 = db_session.get(ResultTableTemplate, a.id)
    b2 = db_session.get(ResultTableTemplate, b.id)
    assert b2.sort_order == 0
    assert a2.sort_order == 1


def test_create_with_column_rules(db_session):
    admin = create_user(db_session, username="admin_rules", is_admin_reports=True)
    row = ResultTableTemplateService.create(
        db_session,
        current_user=admin,
        data={
            "name": "WithRules",
            "tipo": "capacidad_instalada",
            "un": "PJ",
            "column_rules": [
                {"category_key": "2030", "hidden": False, "sort_order": 0}
            ],
        },
    )
    assert len(row.column_rules) == 1
    assert row.column_rules[0].category_key == "2030"


def test_ensure_result_table_seeds_idempotent(db_session):
    from sqlalchemy import func, select

    from app.result_table_seeds import (
        RESULT_TABLE_TEMPLATE_SEEDS,
        ensure_result_table_seeds,
    )

    n1 = ensure_result_table_seeds(db_session)
    db_session.commit()
    assert n1 == len(RESULT_TABLE_TEMPLATE_SEEDS)
    n2 = ensure_result_table_seeds(db_session)
    assert n2 == 0
    count = db_session.scalar(select(func.count()).select_from(ResultTableTemplate))
    assert count == len(RESULT_TABLE_TEMPLATE_SEEDS)
    keys = db_session.scalars(
        select(ResultTableTemplate.seed_key).where(ResultTableTemplate.seed_key.is_not(None))
    ).all()
    assert set(keys) == {s.seed_key for s in RESULT_TABLE_TEMPLATE_SEEDS}


def test_presentation_options_electric_filters_technologies(db_session):
    from app.models import Technology
    from app.services.result_table_presentation_options import (
        build_result_table_presentation_options,
    )

    db_session.add_all(
        [
            Technology(name="PWRTEST01", is_active=True),
            Technology(name="FOOBAR", is_active=True),
        ]
    )
    db_session.commit()
    out = build_result_table_presentation_options(
        db_session, tipo="elec_produccion", agrupar_por="TECNOLOGIA", variable=None
    )
    codes = {o["code"] for o in out["series_options"]}
    assert "PWRTEST01" in codes
    assert "FOOBAR" not in codes
    assert len(out["category_keys"]) >= 50
