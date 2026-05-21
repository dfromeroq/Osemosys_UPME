"""chart_series_config — configuración global de series por tipo de gráfica."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260518_0026"
down_revision = "20260518_0025"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"


def upgrade() -> None:
    op.create_table(
        "chart_series_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tipo", sa.String(length=64), nullable=False),
        sa.Column("agrupar_por", sa.String(length=32), nullable=False),
        sa.Column("series_code", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sort_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("group_key", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tipo",
            "agrupar_por",
            "series_code",
            name="uq_chart_series_config_tipo_agrup_code",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_chart_series_config_tipo_agrup",
        "chart_series_config",
        ["tipo", "agrupar_por", "sort_index"],
        schema=SCHEMA,
    )
    op.alter_column(
        "chart_series_config",
        "hidden",
        server_default=None,
        schema=SCHEMA,
    )
    op.alter_column(
        "chart_series_config",
        "sort_index",
        server_default=None,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chart_series_config_tipo_agrup",
        table_name="chart_series_config",
        schema=SCHEMA,
    )
    op.drop_table("chart_series_config", schema=SCHEMA)
