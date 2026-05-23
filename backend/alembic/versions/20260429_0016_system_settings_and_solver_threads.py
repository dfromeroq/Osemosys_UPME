"""system_settings table + can_manage_system_settings flag + solver_threads_used.

Soporta configuración runtime de SIM_SOLVER_THREADS desde la UI admin y reporta
en cada SimulationJob el número de hilos efectivamente entregados al solver.

Revision ID: 20260429_0016
Revises: 20260424_0015
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_0016"
down_revision = "20260424_0015"
branch_labels = None
depends_on = None

OSEMOSYS_SCHEMA = "osemosys"
CORE_SCHEMA = "core"


def upgrade() -> None:
    op.create_table(
        "system_setting",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_by",
            sa.Uuid(),
            sa.ForeignKey("core.user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema=CORE_SCHEMA,
    )

    op.add_column(
        "user",
        sa.Column(
            "can_manage_system_settings",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema=CORE_SCHEMA,
    )

    op.add_column(
        "simulation_job",
        sa.Column("solver_threads_used", sa.Integer(), nullable=True),
        schema=OSEMOSYS_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(
        "simulation_job", "solver_threads_used", schema=OSEMOSYS_SCHEMA
    )
    op.drop_column(
        "user", "can_manage_system_settings", schema=CORE_SCHEMA
    )
    op.drop_table("system_setting", schema=CORE_SCHEMA)
