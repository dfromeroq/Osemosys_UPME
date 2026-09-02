"""Completa la entidad del filtro de emisiones GEI en el catálogo.

Revision ID: 20260902_0044
Revises: 20260606_0043
Create Date: 2026-09-02
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "20260902_0044"
down_revision = "20260606_0043"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"
CHART_TYPE = "emisiones_gei"
OLD_FILTER_PARAMS = {
    "group": "COMBUSTIBLES_GEI",
    "_filter_fn": "_filtro_gei",
}
NEW_FILTER_PARAMS = {
    "group": "COMBUSTIBLES_GEI",
    "entity": "FUEL",
    "_filter_fn": "_filtro_gei",
}


def _update_if_matches(expected: dict[str, str], replacement: dict[str, str]) -> int:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            f"""
            UPDATE {SCHEMA}.catalog_meta_chart_config
            SET filtro_params_json = CAST(:replacement AS jsonb),
                updated_at = now()
            WHERE tipo = :chart_type
              AND filtro_params_json = CAST(:expected AS jsonb)
            """
        ),
        {
            "chart_type": CHART_TYPE,
            "expected": json.dumps(expected),
            "replacement": json.dumps(replacement),
        },
    )
    return result.rowcount


def upgrade() -> None:
    updated = _update_if_matches(OLD_FILTER_PARAMS, NEW_FILTER_PARAMS)
    if updated != 1:
        raise RuntimeError(
            "Se esperaba actualizar exactamente una fila de "
            f"{SCHEMA}.catalog_meta_chart_config para tipo={CHART_TYPE!r}; "
            f"filas actualizadas: {updated}."
        )


def downgrade() -> None:
    _update_if_matches(NEW_FILTER_PARAMS, OLD_FILTER_PARAMS)
