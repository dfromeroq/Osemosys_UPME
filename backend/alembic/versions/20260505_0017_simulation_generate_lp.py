"""simulation_job.generate_lp flag.

Permite optar por la escritura del modelo como archivo `.lp` (Pyomo
``write_lp_file``) en ``tmp/lp-files/`` cuando se lanza una simulación.

Revision ID: 20260505_0017
Revises: 20260429_0016
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260505_0017"
down_revision = "20260429_0016"
branch_labels = None
depends_on = None

OSEMOSYS_SCHEMA = "osemosys"


def upgrade() -> None:
    op.add_column(
        "simulation_job",
        sa.Column(
            "generate_lp",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema=OSEMOSYS_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(
        "simulation_job",
        "generate_lp",
        schema=OSEMOSYS_SCHEMA,
    )
