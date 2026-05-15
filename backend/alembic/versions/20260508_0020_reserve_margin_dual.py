"""simulation_job.reserve_margin_dual Float column.

Stores the maximum absolute dual value of the reserve margin constraint
(ReserveMarginConstraint or UDC1_UserDefinedConstraintInequality['UDC_Margin'])
extracted via Pyomo Suffix(IMPORT) after LP solve.

Revision ID: 20260508_0020
Revises: 20260506_0019
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260508_0020"
down_revision = "20260506_0019"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"


def upgrade() -> None:
    op.add_column(
        "simulation_job",
        sa.Column("reserve_margin_dual", sa.Float(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("simulation_job", "reserve_margin_dual", schema=SCHEMA)
