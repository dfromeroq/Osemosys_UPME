"""Añade is_global a chart_series_config."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260519_0028"
down_revision = "20260519_0027"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"


def upgrade() -> None:
    op.add_column(
        "chart_series_config",
        sa.Column("is_global", sa.Boolean(), nullable=False, server_default="false"),
        schema=SCHEMA,
    )
    op.alter_column(
        "chart_series_config",
        "is_global",
        server_default=None,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("chart_series_config", "is_global", schema=SCHEMA)
