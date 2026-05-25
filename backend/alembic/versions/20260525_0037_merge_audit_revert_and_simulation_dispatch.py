"""Merge heads: audit_revert_tracking + simulation_dispatch/delete_operation.

Tras mezclar ``develop`` (que aporta ``20260523_0036``) en la rama del
feature de undo del historial (``20260522_0029``) quedan dos heads de
Alembic. Esta migración vacía las fusiona para que ``alembic upgrade head``
no devuelva ``Multiple head revisions``.

Revision ID: 20260525_0037
Revises: 20260523_0036, 20260522_0029
Create Date: 2026-05-25
"""

from __future__ import annotations


revision = "20260525_0037"
down_revision = ("20260523_0036", "20260522_0029")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Migración pura de fusión: no aplica DDL.
    pass


def downgrade() -> None:
    # Sin operaciones inversas: la fusión solo une la historia de revisiones.
    pass
