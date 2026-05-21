"""result_table_template_series/column — presentación relacional; drop presentation JSONB

Revision ID: 20260516_0023
Revises: 20260515_0022
Create Date: 2026-05-16
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "20260516_0023"
down_revision = "20260515_0022"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"


def upgrade() -> None:
    op.create_table(
        "result_table_template_series",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("series_match", sa.String(length=512), nullable=False),
        sa.Column("display_label", sa.String(length=512), nullable=True),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column(
            "hidden",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("sort_index", sa.Integer(), nullable=True),
        sa.Column("group_key", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "series_match",
            name="uq_rtt_series_template_match",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_rtt_series_template",
        "result_table_template_series",
        ["template_id"],
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_rtt_series_template",
        "result_table_template_series",
        "result_table_template",
        ["template_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )

    op.create_table(
        "result_table_template_column",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("category_key", sa.String(length=64), nullable=False),
        sa.Column(
            "hidden",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "category_key",
            name="uq_rtt_col_template_category",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_rtt_col_template",
        "result_table_template_column",
        ["template_id"],
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_rtt_col_template",
        "result_table_template_column",
        "result_table_template",
        ["template_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )

    conn = op.get_bind()
    rows = conn.execute(
        text(
            f"SELECT id, presentation FROM {SCHEMA}.result_table_template "
            "WHERE presentation IS NOT NULL"
        )
    ).fetchall()
    for tid, pres in rows:
        if pres is None:
            continue
        if isinstance(pres, str):
            try:
                pres = json.loads(pres)
            except json.JSONDecodeError:
                continue
        if not isinstance(pres, dict):
            continue
        for s in pres.get("series") or []:
            if not isinstance(s, dict):
                continue
            m = s.get("match")
            if not m:
                continue
            conn.execute(
                text(
                    f"INSERT INTO {SCHEMA}.result_table_template_series "
                    "(template_id, series_match, display_label, color, hidden, sort_index, group_key) "
                    "VALUES (:tid, :sm, :dl, :c, :h, :si, :gk) "
                    "ON CONFLICT ON CONSTRAINT uq_rtt_series_template_match DO NOTHING"
                ),
                {
                    "tid": tid,
                    "sm": str(m)[:512],
                    "dl": (str(s["display_label"])[:512] if s.get("display_label") else None),
                    "c": (str(s["color"])[:32] if s.get("color") else None),
                    "h": bool(s.get("hidden", False)),
                    "si": s.get("sort_index"),
                    "gk": (str(s["group_key"])[:255] if s.get("group_key") else None),
                },
            )
        for c in pres.get("columns") or []:
            if not isinstance(c, dict):
                continue
            ck = c.get("id")
            if not ck:
                continue
            conn.execute(
                text(
                    f"INSERT INTO {SCHEMA}.result_table_template_column "
                    "(template_id, category_key, hidden, sort_order) "
                    "VALUES (:tid, :ck, :h, :so) "
                    "ON CONFLICT ON CONSTRAINT uq_rtt_col_template_category DO NOTHING"
                ),
                {
                    "tid": tid,
                    "ck": str(ck)[:64],
                    "h": bool(c.get("hidden", False)),
                    "so": c.get("sort_order"),
                },
            )

    op.drop_column("result_table_template", "presentation", schema=SCHEMA)


def downgrade() -> None:
    from sqlalchemy.dialects.postgresql import JSONB

    op.add_column(
        "result_table_template",
        sa.Column("presentation", JSONB(astext_type=sa.Text()), nullable=True),
        schema=SCHEMA,
    )

    conn = op.get_bind()
    templates = conn.execute(
        text(f"SELECT id FROM {SCHEMA}.result_table_template")
    ).fetchall()
    for (tid,) in templates:
        series_rows = conn.execute(
            text(
                f"SELECT series_match, display_label, color, hidden, sort_index, group_key "
                f"FROM {SCHEMA}.result_table_template_series WHERE template_id = :tid ORDER BY id"
            ),
            {"tid": tid},
        ).fetchall()
        col_rows = conn.execute(
            text(
                f"SELECT category_key, hidden, sort_order FROM {SCHEMA}.result_table_template_column "
                "WHERE template_id = :tid ORDER BY id"
            ),
            {"tid": tid},
        ).fetchall()
        series = [
            {
                "match": r[0],
                "display_label": r[1],
                "color": r[2],
                "hidden": r[3],
                "sort_index": r[4],
                "group_key": r[5],
            }
            for r in series_rows
        ]
        columns = [
            {"id": r[0], "hidden": r[1], "sort_order": r[2]} for r in col_rows
        ]
        if not series and not columns:
            conn.execute(
                text(
                    f"UPDATE {SCHEMA}.result_table_template SET presentation = NULL WHERE id = :tid"
                ),
                {"tid": tid},
            )
        else:
            blob = json.dumps({"series": series, "columns": columns})
            conn.execute(
                text(
                    f"UPDATE {SCHEMA}.result_table_template SET presentation = CAST(:blob AS jsonb) WHERE id = :tid"
                ),
                {"blob": blob, "tid": tid},
            )

    op.drop_constraint(
        "fk_rtt_col_template",
        "result_table_template_column",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_index("ix_rtt_col_template", table_name="result_table_template_column", schema=SCHEMA)
    op.drop_table("result_table_template_column", schema=SCHEMA)

    op.drop_constraint(
        "fk_rtt_series_template",
        "result_table_template_series",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_index("ix_rtt_series_template", table_name="result_table_template_series", schema=SCHEMA)
    op.drop_table("result_table_template_series", schema=SCHEMA)
