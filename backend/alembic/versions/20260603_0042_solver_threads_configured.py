"""Add simulation_job.solver_threads_configured.

Revision ID: 20260603_0042
Revises: 20260603_0041
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260603_0042"
down_revision = "20260603_0041"
branch_labels = None
depends_on = None

OSEMOSYS_SCHEMA = "osemosys"


def upgrade() -> None:
    op.add_column(
        "simulation_job",
        sa.Column("solver_threads_configured", sa.Integer(), nullable=True),
        schema=OSEMOSYS_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(
        "simulation_job",
        "solver_threads_configured",
        schema=OSEMOSYS_SCHEMA,
    )
