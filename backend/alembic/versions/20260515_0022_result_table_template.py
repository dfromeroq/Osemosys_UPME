"""osemosys.result_table_template — tablas de resultados configurables (admin)

Revision ID: 20260515_0022
Revises: 20260515_0021
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260515_0022"
down_revision = "20260515_0021"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"


def upgrade() -> None:
    op.create_table(
        "result_table_template",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("display_title", sa.String(length=255), nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("tipo", sa.String(length=64), nullable=False),
        sa.Column("un", sa.String(length=16), nullable=False),
        sa.Column("sub_filtro", sa.String(length=64), nullable=True),
        sa.Column("loc", sa.String(length=32), nullable=True),
        sa.Column("variable", sa.String(length=64), nullable=True),
        sa.Column("agrupar_por", sa.String(length=32), nullable=True),
        sa.Column("region", sa.String(length=16), nullable=True),
        sa.Column("timeslice", sa.String(length=32), nullable=True),
        sa.Column("table_period_years", sa.Integer(), nullable=True),
        sa.Column("table_cumulative", sa.Boolean(), nullable=True),
        sa.Column("custom_series_order", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("y_axis_min", sa.Float(), nullable=True),
        sa.Column("y_axis_max", sa.Float(), nullable=True),
        sa.Column("presentation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_result_table_template_created_by",
        "result_table_template",
        "user",
        ["created_by_user_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema="core",
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_result_table_template_enabled_sort",
        "result_table_template",
        ["is_enabled", "sort_order"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_result_table_template_enabled_sort",
        table_name="result_table_template",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "fk_result_table_template_created_by",
        "result_table_template",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_table("result_table_template", schema=SCHEMA)
