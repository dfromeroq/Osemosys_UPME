"""Tablas versionadas de defaults OSeMOSYS + permiso + job.model_defaults_version_id.

Revision ID: 20260603_0041
Revises: 20260603_0040
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260603_0041"
down_revision = "20260603_0040"
branch_labels = None
depends_on = None

OSEMOSYS_SCHEMA = "osemosys"
CORE_SCHEMA = "core"
ACTIVE_VERSION_KEY = "model_defaults.active_version_id"


def upgrade() -> None:
    op.create_table(
        "model_parameter_catalog",
        sa.Column("param_key", sa.String(length=80), primary_key=True),
        sa.Column("pyomo_name", sa.String(length=120), nullable=False),
        sa.Column("index_dims", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("value_type", sa.String(length=20), nullable=False, server_default="float"),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column(
            "requires_storage",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "requires_udc",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema=OSEMOSYS_SCHEMA,
    )

    op.create_table(
        "model_parameter_default_version",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(f"{CORE_SCHEMA}.user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=OSEMOSYS_SCHEMA,
    )

    op.create_table(
        "model_parameter_default_item",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("param_key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            [f"{OSEMOSYS_SCHEMA}.model_parameter_default_version.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["param_key"],
            [f"{OSEMOSYS_SCHEMA}.model_parameter_catalog.param_key"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "param_key", name="uq_model_default_item_version_key"),
        schema=OSEMOSYS_SCHEMA,
    )
    op.create_index(
        "ix_model_parameter_default_item_version_id",
        "model_parameter_default_item",
        ["version_id"],
        schema=OSEMOSYS_SCHEMA,
    )

    op.add_column(
        "user",
        sa.Column(
            "can_manage_model_defaults",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema=CORE_SCHEMA,
    )

    op.add_column(
        "simulation_job",
        sa.Column("model_defaults_version_id", sa.Integer(), nullable=True),
        schema=OSEMOSYS_SCHEMA,
    )
    op.create_foreign_key(
        "fk_simulation_job_model_defaults_version",
        "simulation_job",
        "model_parameter_default_version",
        ["model_defaults_version_id"],
        ["id"],
        source_schema=OSEMOSYS_SCHEMA,
        referent_schema=OSEMOSYS_SCHEMA,
        ondelete="SET NULL",
    )

    _seed_catalog_and_version()


def _seed_catalog_and_version() -> None:
    from app.simulation.core.model_param_catalog_seed import MODEL_PARAMETER_CATALOG

    bind = op.get_bind()
    for entry in MODEL_PARAMETER_CATALOG:
        bind.execute(
            sa.text(
                f"""
                INSERT INTO {OSEMOSYS_SCHEMA}.model_parameter_catalog
                    (param_key, pyomo_name, index_dims, category, description,
                     value_type, min_value, max_value, requires_storage, requires_udc)
                VALUES
                    (:param_key, :pyomo_name, :index_dims, :category, :description,
                     'float', :min_value, :max_value, :requires_storage, :requires_udc)
                ON CONFLICT (param_key) DO NOTHING
                """
            ),
            {
                "param_key": entry.param_key,
                "pyomo_name": entry.pyomo_name,
                "index_dims": entry.index_dims,
                "category": entry.category,
                "description": entry.description,
                "min_value": entry.min_value,
                "max_value": entry.max_value,
                "requires_storage": entry.requires_storage,
                "requires_udc": entry.requires_udc,
            },
        )

    version_id = bind.execute(
        sa.text(
            f"""
            INSERT INTO {OSEMOSYS_SCHEMA}.model_parameter_default_version (comment)
            VALUES ('Seed inicial desde OSEMOSYS_PARAM_DEFAULTS')
            RETURNING id
            """
        )
    ).scalar_one()

    for entry in MODEL_PARAMETER_CATALOG:
        bind.execute(
            sa.text(
                f"""
                INSERT INTO {OSEMOSYS_SCHEMA}.model_parameter_default_item
                    (version_id, param_key, value)
                VALUES (:version_id, :param_key, :value)
                """
            ),
            {
                "version_id": version_id,
                "param_key": entry.param_key,
                "value": entry.initial_value,
            },
        )

    bind.execute(
        sa.text(
            f"""
            INSERT INTO {CORE_SCHEMA}.system_setting (key, value)
            VALUES (:key, :value)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """
        ),
        {"key": ACTIVE_VERSION_KEY, "value": str(version_id)},
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_simulation_job_model_defaults_version",
        "simulation_job",
        schema=OSEMOSYS_SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("simulation_job", "model_defaults_version_id", schema=OSEMOSYS_SCHEMA)
    op.drop_column("user", "can_manage_model_defaults", schema=CORE_SCHEMA)
    op.drop_index(
        "ix_model_parameter_default_item_version_id",
        table_name="model_parameter_default_item",
        schema=OSEMOSYS_SCHEMA,
    )
    op.drop_table("model_parameter_default_item", schema=OSEMOSYS_SCHEMA)
    op.drop_table("model_parameter_default_version", schema=OSEMOSYS_SCHEMA)
    op.drop_table("model_parameter_catalog", schema=OSEMOSYS_SCHEMA)
    bind = op.get_bind()
    bind.execute(
        sa.text(f"DELETE FROM {CORE_SCHEMA}.system_setting WHERE key = :key"),
        {"key": ACTIVE_VERSION_KEY},
    )
