"""Add description column to simulation_job.

Revision ID: 20260528_0038
Revises: 20260525_0037
Create Date: 2026-05-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260528_0038"
down_revision = "20260525_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "simulation_job",
        sa.Column("description", sa.Text(), nullable=True),
        schema="osemosys",
    )


def downgrade() -> None:
    op.drop_column("simulation_job", "description", schema="osemosys")
