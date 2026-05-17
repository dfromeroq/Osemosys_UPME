"""result_table_template.seed_key + siembra idempotente de plantillas eléctricas

Revision ID: 20260517_0024
Revises: 20260516_0023
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

from app.result_table_seeds import seed_rows_for_sql

revision = "20260517_0024"
down_revision = "20260516_0023"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"

_SEED_KEYS = (
    "default_elec_produccion",
    "default_prd_electricidad",
    "default_cap_electricidad",
    "default_factor_planta",
)


def upgrade() -> None:
    op.add_column(
        "result_table_template",
        sa.Column("seed_key", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_result_table_template_seed_key",
        "result_table_template",
        ["seed_key"],
        unique=True,
        schema=SCHEMA,
    )

    conn = op.get_bind()
    insert_sql = text(
        f"""
        INSERT INTO {SCHEMA}.result_table_template (
            seed_key, name, display_title, sort_order, is_enabled,
            tipo, un, sub_filtro, loc, variable, agrupar_por, region, timeslice,
            table_period_years, table_cumulative, custom_series_order,
            y_axis_min, y_axis_max, created_by_user_id
        ) VALUES (
            :seed_key, :name, :display_title, :sort_order, :is_enabled,
            :tipo, :un, :sub_filtro, :loc, :variable, :agrupar_por, :region, :timeslice,
            :table_period_years, :table_cumulative, :custom_series_order,
            :y_axis_min, :y_axis_max, :created_by_user_id
        )
        ON CONFLICT (seed_key) DO NOTHING
        """
    )
    for row in seed_rows_for_sql():
        conn.execute(insert_sql, row)


def downgrade() -> None:
    conn = op.get_bind()
    keys = ", ".join(f"'{k}'" for k in _SEED_KEYS)
    conn.execute(
        text(
            f"DELETE FROM {SCHEMA}.result_table_template "
            f"WHERE seed_key IN ({keys})"
        )
    )
    op.drop_index(
        "uq_result_table_template_seed_key",
        table_name="result_table_template",
        schema=SCHEMA,
    )
    op.drop_column("result_table_template", "seed_key", schema=SCHEMA)
