"""Añade timestamp de despacho Celery a simulation_job."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260523_0035"
down_revision = "20260519_0028"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"


def upgrade() -> None:
    op.add_column(
        "simulation_job",
        sa.Column("celery_dispatched_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("simulation_job", "celery_dispatched_at", schema=SCHEMA)
