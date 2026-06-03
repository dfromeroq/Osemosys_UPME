"""Elimina simulation_job.accept_uncertified_feasible si existe.

Revision ID: 20260603_0040
Revises: 20260528_0038
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260603_0040"
down_revision = "20260528_0038"
branch_labels = None
depends_on = None

OSEMOSYS_SCHEMA = "osemosys"


def _column_exists(connection, column_name: str) -> bool:
    insp = sa.inspect(connection)
    cols = insp.get_columns("simulation_job", schema=OSEMOSYS_SCHEMA)
    return any(c["name"] == column_name for c in cols)


def upgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "accept_uncertified_feasible"):
        op.drop_column(
            "simulation_job",
            "accept_uncertified_feasible",
            schema=OSEMOSYS_SCHEMA,
        )


def downgrade() -> None:
    op.add_column(
        "simulation_job",
        sa.Column(
            "accept_uncertified_feasible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema=OSEMOSYS_SCHEMA,
    )
