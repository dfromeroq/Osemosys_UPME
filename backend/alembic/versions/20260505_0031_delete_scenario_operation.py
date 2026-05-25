"""add async scenario delete operation

Revision ID: 20260505_0031
Revises: 20260418_0030
Create Date: 2026-05-05
"""

from alembic import op


revision = "20260505_0031"
down_revision = "20260418_0030"
branch_labels = None
depends_on = None


SCHEMA = "osemosys"
CONSTRAINT = "scenario_operation_job_type"
TABLE = "scenario_operation_job"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(
        CONSTRAINT,
        TABLE,
        "operation_type IN ('CLONE_SCENARIO','APPLY_EXCEL_CHANGES','DELETE_SCENARIO')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(
        CONSTRAINT,
        TABLE,
        "operation_type IN ('CLONE_SCENARIO','APPLY_EXCEL_CHANGES')",
        schema=SCHEMA,
    )
