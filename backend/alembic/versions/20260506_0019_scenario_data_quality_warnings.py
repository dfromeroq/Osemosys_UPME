"""scenario.data_quality_warnings JSONB column.

Persiste los warnings de calidad de datos detectados por
``app.simulation.core.data_validation`` (bound conflicts lower/upper y
exclusiones de años con YearSplit=0). Habilita un sistema de notificaciones
constante en la tabla de escenarios y endpoints de auto-fix.

Estructura de la columna (ver DataQualityReport.to_dict()):

    {
      "bound_conflicts": [{lower, upper, key, value_lower, value_upper, gap, severity}, ...],
      "year_exclusions": [{year, reason, n_timeslices_zero, n_timeslices_total}, ...],
      "detected_at": "<iso8601>",
      "detected_during": "import" | "manual" | "simulation",
      "summary": {n_bound_conflicts, n_bound_real_conflict, n_bound_numeric_precision, n_year_exclusions}
    }

Revision ID: 20260506_0019
Revises: 20260505_0018
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260506_0019"
down_revision = "20260505_0018"
branch_labels = None
depends_on = None

OSEMOSYS_SCHEMA = "osemosys"


def upgrade() -> None:
    op.add_column(
        "scenario",
        sa.Column(
            "data_quality_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema=OSEMOSYS_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(
        "scenario",
        "data_quality_warnings",
        schema=OSEMOSYS_SCHEMA,
    )
