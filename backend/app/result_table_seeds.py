"""Siembra idempotente de plantillas globales de tablas en página de resultados.

Filas con ``seed_key`` se insertan una sola vez (upsert lógico). El admin puede
editar nombre, título, orden, etc.; una segunda siembra no duplica filas.

La lista inicial refleja el bloque «Sector Eléctrico» de ``chart_menu.MENU``
y el subconjunto ``todos`` del ChartSelector (producción, capacidad, factor).

Vive fuera de ``app.visualization`` para que migraciones Alembic puedan importar
esta lista sin cargar ``chart_service`` (pandas).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ResultTableTemplate


@dataclass(frozen=True)
class ResultTableTemplateSeed:
    """Definición de una fila en ``osemosys.result_table_template``."""

    seed_key: str
    name: str
    display_title: str | None
    sort_order: int
    tipo: str
    un: str
    agrupar_por: str
    is_enabled: bool = True
    sub_filtro: str | None = None
    loc: str | None = None
    variable: str | None = None
    region: str | None = None
    timeslice: str | None = None


# Orden alineado con chart_menu.MENU (Sector Eléctrico) y uso típico «todos».
RESULT_TABLE_TEMPLATE_SEEDS: tuple[ResultTableTemplateSeed, ...] = (
    ResultTableTemplateSeed(
        seed_key="default_elec_produccion",
        name="Tabla — Producción de electricidad",
        display_title="Producción de Electricidad - ProductionByTechnology",
        sort_order=0,
        tipo="elec_produccion",
        un="PJ",
        agrupar_por="TECNOLOGIA",
    ),
    ResultTableTemplateSeed(
        seed_key="default_prd_electricidad",
        name="Tabla — Producción eléctrica (%)",
        display_title="Producción de Electricidad - ProductionByTechnology (%)",
        sort_order=1,
        tipo="prd_electricidad",
        un="%",
        agrupar_por="TECNOLOGIA",
    ),
    ResultTableTemplateSeed(
        seed_key="default_cap_electricidad",
        name="Tabla — Matriz eléctrica (capacidad)",
        display_title="Matriz Eléctrica (Capacidad) - TotalCapacityAnnual",
        sort_order=2,
        tipo="cap_electricidad",
        un="GW",
        agrupar_por="TECNOLOGIA",
        variable="TotalCapacityAnnual",
    ),
    ResultTableTemplateSeed(
        seed_key="default_factor_planta",
        name="Tabla — Factor de planta",
        display_title="Factor de Planta (%)",
        sort_order=3,
        tipo="factor_planta",
        un="%",
        agrupar_por="TECNOLOGIA",
    ),
)


def _seed_to_model_kwargs(spec: ResultTableTemplateSeed) -> dict[str, Any]:
    return {
        "seed_key": spec.seed_key,
        "name": spec.name,
        "display_title": spec.display_title,
        "sort_order": spec.sort_order,
        "is_enabled": spec.is_enabled,
        "tipo": spec.tipo,
        "un": spec.un,
        "sub_filtro": spec.sub_filtro,
        "loc": spec.loc,
        "variable": spec.variable,
        "agrupar_por": spec.agrupar_por,
        "region": spec.region,
        "timeslice": spec.timeslice,
        "table_period_years": None,
        "table_cumulative": None,
        "custom_series_order": None,
        "y_axis_min": None,
        "y_axis_max": None,
        "created_by_user_id": None,
    }


def seed_rows_for_sql() -> list[dict[str, Any]]:
    """Filas para migración Alembic o script SQL (sin ``id``)."""
    return [_seed_to_model_kwargs(s) for s in RESULT_TABLE_TEMPLATE_SEEDS]


def ensure_result_table_seeds(session: Session) -> int:
    """Inserta plantillas faltantes. No actualiza filas existentes.

    Returns:
        Número de filas nuevas insertadas en esta llamada.
    """
    added = 0
    for spec in RESULT_TABLE_TEMPLATE_SEEDS:
        exists = session.scalar(
            select(ResultTableTemplate.id).where(
                ResultTableTemplate.seed_key == spec.seed_key
            )
        )
        if exists is not None:
            continue
        session.add(ResultTableTemplate(**_seed_to_model_kwargs(spec)))
        added += 1
    if added:
        session.flush()
    return added
