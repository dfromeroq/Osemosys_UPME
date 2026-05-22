"""osemosys_param_value_audit: tracking de reverts.

Añade columnas para registrar cuándo y por quién se revirtió una entrada de
auditoría y para distinguir entradas que son ellas mismas un revert de un
cambio previo.

Columnas nuevas:
- ``reverted_at`` / ``reverted_by`` / ``reverted_by_audit_id``: una entrada
  queda marcada como revertida cuando se aplica un undo posterior.
- ``is_revert`` + ``reverts_entry_id``: marcan las entradas generadas por la
  acción de revert para poder filtrarlas y enlazarlas al cambio original.

Revision ID: 20260522_0029
Revises: 20260519_0028
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260522_0029"
down_revision = "20260519_0028"
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
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        schema=schema,
    )
    op.add_column(
        TABLE,
        sa.Column("reverted_by", sa.String(length=255), nullable=True),
        schema=schema,
    )
    op.add_column(
        TABLE,
        sa.Column("reverted_by_audit_id", sa.Integer(), nullable=True),
        schema=schema,
    )
    op.add_column(
        TABLE,
        sa.Column(
            "is_revert",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema=schema,
    )
    op.add_column(
        TABLE,
        sa.Column("reverts_entry_id", sa.Integer(), nullable=True),
        schema=schema,
    )

    op.create_index(
        "ix_osemosys_param_audit_reverted_by_audit_id",
        TABLE,
        ["reverted_by_audit_id"],
        schema=schema,
    )
    op.create_index(
        "ix_osemosys_param_audit_reverts_entry_id",
        TABLE,
        ["reverts_entry_id"],
        schema=schema,
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    schema = None if is_sqlite else SCHEMA

    op.drop_index(
        "ix_osemosys_param_audit_reverts_entry_id",
        table_name=TABLE,
        schema=schema,
    )
    op.drop_index(
        "ix_osemosys_param_audit_reverted_by_audit_id",
        table_name=TABLE,
        schema=schema,
    )
    op.drop_column(TABLE, "reverts_entry_id", schema=schema)
    op.drop_column(TABLE, "is_revert", schema=schema)
    op.drop_column(TABLE, "reverted_by_audit_id", schema=schema)
    op.drop_column(TABLE, "reverted_by", schema=schema)
    op.drop_column(TABLE, "reverted_at", schema=schema)
