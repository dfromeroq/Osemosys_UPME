"""Añade apply_to_main_chart a result_table_template."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260518_0025"
down_revision = "20260517_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "result_table_template",
        sa.Column(
            "apply_to_main_chart",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        schema="osemosys",
    )
    op.alter_column(
        "result_table_template",
        "apply_to_main_chart",
        server_default=None,
        schema="osemosys",
    )


def downgrade() -> None:
    op.drop_column(
        "result_table_template",
        "apply_to_main_chart",
        schema="osemosys",
    )
