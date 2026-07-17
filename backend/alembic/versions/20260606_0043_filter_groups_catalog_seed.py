"""Filter groups + seed completo del catálogo de visualización.

Revision ID: 20260606_0043
Revises: 20260603_0042
Create Date: 2026-06-06
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260606_0043"
down_revision = "20260603_0042"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")
SCHEMA = "osemosys"


def _audit_columns() -> list:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("modified_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("core.user.id", ondelete="SET NULL"), nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names(schema=SCHEMA))

    if "catalog_meta_filter_group" not in existing:
        op.create_table(
            "catalog_meta_filter_group",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(128), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("filter_mode", sa.String(32), nullable=False, server_default="TECH_ONLY"),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            *_audit_columns(),
            sa.UniqueConstraint("code", name="uq_filter_group_code"),
            schema=SCHEMA,
        )

    if "catalog_meta_filter_member" not in existing:
        op.create_table(
            "catalog_meta_filter_member",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("group_id", sa.Integer(), sa.ForeignKey(f"{SCHEMA}.catalog_meta_filter_group.id", ondelete="CASCADE"), nullable=False),
            sa.Column("member_kind", sa.String(16), nullable=False, server_default="CODE"),
            sa.Column("operation", sa.String(16), nullable=False, server_default="INCLUDE"),
            sa.Column("entity_type", sa.String(16), nullable=False, server_default="TECHNOLOGY"),
            sa.Column("match_mode", sa.String(16), nullable=False, server_default="EXACT"),
            sa.Column("value", sa.String(512), nullable=True),
            sa.Column("ref_group_id", sa.Integer(), sa.ForeignKey(f"{SCHEMA}.catalog_meta_filter_group.id", ondelete="SET NULL"), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            *_audit_columns(),
            schema=SCHEMA,
        )
        op.create_index(
            "ix_filter_member_group",
            "catalog_meta_filter_member",
            ["group_id", "sort_order"],
            schema=SCHEMA,
        )

    cc_cols = {c["name"] for c in insp.get_columns("catalog_meta_chart_config", schema=SCHEMA)} if "catalog_meta_chart_config" in existing else set()
    if "catalog_meta_chart_config" in existing and "filtro_group_id" not in cc_cols:
        op.add_column(
            "catalog_meta_chart_config",
            sa.Column("filtro_group_id", sa.Integer(), sa.ForeignKey(f"{SCHEMA}.catalog_meta_filter_group.id", ondelete="SET NULL"), nullable=True),
            schema=SCHEMA,
        )

    sf_cols = {c["name"] for c in insp.get_columns("catalog_meta_chart_subfilter", schema=SCHEMA)} if "catalog_meta_chart_subfilter" in existing else set()
    if "catalog_meta_chart_subfilter" in existing and "filter_group_id" not in sf_cols:
        op.add_column(
            "catalog_meta_chart_subfilter",
            sa.Column("filter_group_id", sa.Integer(), sa.ForeignKey(f"{SCHEMA}.catalog_meta_filter_group.id", ondelete="SET NULL"), nullable=True),
            schema=SCHEMA,
        )

    # Siembra desde configs_legacy (misma conexión que Alembic para ver DDL no commiteado)
    try:
        from sqlalchemy.orm import Session

        from app.visualization.catalog_seed import seed_visualization_catalog

        db = Session(bind=bind)
        try:
            summary = seed_visualization_catalog(db)
            db.commit()
            logger.info("Visualization catalog seeded: %s", summary)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Seed del catálogo omitido en migración: %s", exc)


def downgrade() -> None:
    op.drop_column("catalog_meta_chart_subfilter", "filter_group_id", schema=SCHEMA)
    op.drop_column("catalog_meta_chart_config", "filtro_group_id", schema=SCHEMA)
    op.drop_table("catalog_meta_filter_member", schema=SCHEMA)
    op.drop_table("catalog_meta_filter_group", schema=SCHEMA)
