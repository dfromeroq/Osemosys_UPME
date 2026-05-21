#!/usr/bin/env python3
"""Herramienta opcional: migrar ``series_rules`` legacy a ``chart_series_config``.

La migración Alembic ``20260519_0027`` ya copia los datos de
``osemosys.result_table_template_series`` a ``chart_series_config`` antes de
eliminar la tabla. **No hace falta** ejecutar este script en un flujo normal.

Úsalo solo si aplicaste cambios de esquema a mano sin pasar por esa migración
y aún tienes la tabla ``result_table_template_series`` poblada.

Ejemplo::

    cd backend && python scripts/migrate_result_table_series_rules_to_chart_series_config.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    from sqlalchemy import inspect, text
    from sqlalchemy.orm import Session

    from app.db.session import SessionLocal
    from app.visualization.configs import CONFIGS
    from app.visualization.labels import get_label

    SCHEMA = "osemosys"
    session: Session = SessionLocal()
    try:
        conn = session.connection()
        insp = inspect(conn)
        if "result_table_template_series" not in insp.get_table_names(schema=SCHEMA):
            print("No existe result_table_template_series; nada que migrar.")
            return 0

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

        n = 0
        for r in rows:
            tipo = str(r["tipo"]).strip()
            ap_raw = (r["agrupar_por"] or "").strip().upper()
            if not ap_raw:
                ap_raw = str((CONFIGS.get(tipo) or {}).get("agrupar_por") or "TECNOLOGIA").upper()
            if ap_raw == "COMBUSTIBLE":
                ap = "FUEL"
            else:
                ap = ap_raw
            sm = str(r["series_match"] or "").strip()
            if not sm:
                continue

            hit = conn.execute(
                text(
                    f"""
                    SELECT id FROM {SCHEMA}.chart_series_config
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
                dn = conn.execute(
                    text(
                        f"SELECT display_name FROM {SCHEMA}.chart_series_config WHERE id = :id"
                    ),
                    {"id": hit["id"]},
                ).scalar()
                new_name = str(dn)[:512]
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
            n += 1

        session.commit()
        print(f"Migradas {n} reglas de series hacia chart_series_config.")
        return 0
    except Exception as err:
        session.rollback()
        print(f"Error: {err}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
