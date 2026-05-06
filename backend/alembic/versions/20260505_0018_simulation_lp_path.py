"""simulation_job.lp_path column.

Persiste la ruta absoluta del archivo `.lp` escrito por el pipeline cuando
``generate_lp=True``. Habilita la descarga del modelo desde la UI vía
``GET /simulations/{id}/lp-file``.

Revision ID: 20260505_0018
Revises: 20260505_0017
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260505_0018"
down_revision = "20260505_0017"
branch_labels = None
depends_on = None

OSEMOSYS_SCHEMA = "osemosys"


def upgrade() -> None:
    op.add_column(
        "simulation_job",
        sa.Column("lp_path", sa.Text(), nullable=True),
        schema=OSEMOSYS_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(
        "simulation_job",
        "lp_path",
        schema=OSEMOSYS_SCHEMA,
    )
