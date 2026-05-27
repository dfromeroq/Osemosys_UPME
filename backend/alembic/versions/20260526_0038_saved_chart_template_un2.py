"""Añade un2 (unidad de eje Y secundario) a saved_chart_template."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260526_0038"
down_revision = "20260525_0037"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"


def upgrade() -> None:
    op.add_column(
        "saved_chart_template",
        sa.Column("un2", sa.String(16), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("saved_chart_template", "un2", schema=SCHEMA)
