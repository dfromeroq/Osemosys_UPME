"""osemosys_param_value_audit: agregar batch_id y batch_label.

Agrupa cambios que se aplican en una misma operación (Excel apply, import,
edición masiva) bajo un identificador común para que la UI de historial
pueda colapsar/expandir batches en vez de listar miles de filas sueltas.

- ``batch_id`` UUID textual (String(36)) compartido por todas las entradas
  generadas en una misma operación; nullable para entradas legacy o
  cambios atómicos individuales que no requieren agrupación.
- ``batch_label`` descripción legible de la operación (ej. "Aplicación
  Excel: archivo.xlsx (487 filas)").

Revision ID: 20260506_0020
Revises: 20260506_0019
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260506_0020"
down_revision = "20260506_0019"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"
TABLE = "osemosys_param_value_audit"


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    schema = None if is_sqlite else SCHEMA

    op.add_column(
        TABLE,
        sa.Column("batch_id", sa.String(length=36), nullable=True),
        schema=schema,
    )
    op.add_column(
        TABLE,
        sa.Column("batch_label", sa.String(length=200), nullable=True),
        schema=schema,
    )
    op.create_index(
        "ix_osemosys_param_audit_scenario_batch",
        TABLE,
        ["id_scenario", "batch_id"],
        schema=schema,
    )
    op.create_index(
        "ix_osemosys_param_audit_scenario_created",
        TABLE,
        ["id_scenario", "created_at"],
        schema=schema,
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    schema = None if is_sqlite else SCHEMA

    op.drop_index(
        "ix_osemosys_param_audit_scenario_created",
        table_name=TABLE,
        schema=schema,
    )
    op.drop_index(
        "ix_osemosys_param_audit_scenario_batch",
        table_name=TABLE,
        schema=schema,
    )
    op.drop_column(TABLE, "batch_label", schema=schema)
    op.drop_column(TABLE, "batch_id", schema=schema)
