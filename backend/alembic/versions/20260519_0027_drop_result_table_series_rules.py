"""Migra series_rules de plantillas a chart_series_config; elimina tabla y apply_to_main_chart.

Revision ID: 20260519_0027
Revises: 20260518_0026
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

from app.visualization.configs import CONFIGS
from app.visualization.labels import get_label

revision = "20260519_0027"
down_revision = "20260518_0026"
branch_labels = None
depends_on = None

SCHEMA = "osemosys"


def _normalize_agrupar(tipo: str, agrupar_por: str | None) -> str:
    ap = (agrupar_por or "").strip().upper()
    if not ap:
        ap = str((CONFIGS.get(tipo.strip()) or {}).get("agrupar_por") or "TECNOLOGIA").upper()
    if ap == "COMBUSTIBLE":
        return "FUEL"
    return ap


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    tables = insp.get_table_names(schema=SCHEMA)

    if "result_table_template_series" in tables:
        rows = conn.execute(
            text(
                f"""
                SELECT s.series_match, s.display_label, s.color, s.hidden, s.sort_index, s.group_key,
                       t.tipo, t.agrupar_por
                FROM {SCHEMA}.result_table_template_series s
                JOIN {SCHEMA}.result_table_template t ON t.id = s.template_id
                """
            )
        ).mappings().all()

        for r in rows:
            tipo = str(r["tipo"]).strip()
            ap = _normalize_agrupar(tipo, r["agrupar_por"])
            sm = str(r["series_match"] or "").strip()
            if not sm:
                continue

            hit = conn.execute(
                text(
                    f"""
                    SELECT id, series_code, display_name FROM {SCHEMA}.chart_series_config
                    WHERE tipo = :tipo AND agrupar_por = :ap
                      AND (series_code = :sm OR display_name = :sm
                           OR lower(series_code) = lower(:sm) OR lower(display_name) = lower(:sm))
                    LIMIT 1
                    """
                ),
                {"tipo": tipo, "ap": ap, "sm": sm},
            ).mappings().first()

            dl = r["display_label"]
            if dl is not None and str(dl).strip():
                new_name = str(dl).strip()[:512]
            elif hit:
                new_name = str(hit["display_name"])
            else:
                new_name = get_label(sm)[:512]

            color = r["color"]
            color_s = str(color).strip()[:32] if color not in (None, "") else None
            hidden = bool(r["hidden"])
            gk = r["group_key"]
            gk_s = str(gk).strip()[:255] if gk not in (None, "") else None
            si = r["sort_index"]
            si_v = int(si) if si is not None else None

            if hit:
                conn.execute(
                    text(
                        f"""
                        UPDATE {SCHEMA}.chart_series_config SET
                          display_name = :dn,
                          color = COALESCE(:color, color),
                          hidden = :hidden,
                          sort_index = COALESCE(:si, sort_index),
                          group_key = COALESCE(:gk, group_key)
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": hit["id"],
                        "dn": new_name,
                        "color": color_s,
                        "hidden": hidden,
                        "si": si_v,
                        "gk": gk_s,
                    },
                )
            else:
                code = sm[:512]
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {SCHEMA}.chart_series_config
                          (tipo, agrupar_por, series_code, display_name, color, hidden,
                           sort_index, group_key)
                        VALUES
                          (:tipo, :ap, :code, :dn, :color, :hidden, COALESCE(:si, 0), :gk)
                        ON CONFLICT (tipo, agrupar_por, series_code) DO UPDATE SET
                          display_name = EXCLUDED.display_name,
                          color = COALESCE(EXCLUDED.color, chart_series_config.color),
                          hidden = EXCLUDED.hidden,
                          sort_index = COALESCE(EXCLUDED.sort_index, chart_series_config.sort_index),
                          group_key = COALESCE(EXCLUDED.group_key, chart_series_config.group_key)
                        """
                    ),
                    {
                        "tipo": tipo,
                        "ap": ap,
                        "code": code,
                        "dn": new_name,
                        "color": color_s,
                        "hidden": hidden,
                        "si": si_v,
                        "gk": gk_s,
                    },
                )

        op.drop_constraint(
            "fk_rtt_series_template",
            "result_table_template_series",
            schema=SCHEMA,
            type_="foreignkey",
        )
        op.drop_index(
            "ix_rtt_series_template",
            table_name="result_table_template_series",
            schema=SCHEMA,
        )
        op.drop_table("result_table_template_series", schema=SCHEMA)

    if "apply_to_main_chart" in {
        c["name"]
        for c in inspect(conn).get_columns("result_table_template", schema=SCHEMA)
    }:
        op.drop_column("result_table_template", "apply_to_main_chart", schema=SCHEMA)


def downgrade() -> None:
    op.add_column(
        "result_table_template",
        sa.Column(
            "apply_to_main_chart",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        schema=SCHEMA,
    )
    op.alter_column(
        "result_table_template",
        "apply_to_main_chart",
        server_default=None,
        schema=SCHEMA,
    )

    op.create_table(
        "result_table_template_series",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("series_match", sa.String(length=512), nullable=False),
        sa.Column("display_label", sa.String(length=512), nullable=True),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default="false"),
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
