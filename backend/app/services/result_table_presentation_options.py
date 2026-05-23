"""Opciones de presentación (series / categorías) para editor admin de tablas de resultados.

Deriva candidatos del catálogo osemosys usando la misma semántica que
``DATA_EXPLORER_FILTERS`` + ``get_label`` (coincide con ``ChartSeries.name``).
Sin depender de un job concreto.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Emission, Fuel, Region, Technology
from app.visualization.configs import CONFIGS
from app.visualization.configs_comparacion import MAPA_SECTOR
from app.visualization.data_explorer_filters import get_data_explorer_filters
from app.visualization.labels import get_label

# Rango sintético de años para ``category_key`` (columnas) en gráficas anuales.
YEAR_CATEGORY_MIN = 2015
YEAR_CATEGORY_MAX = 2075


def _dedupe_by_value(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for o in options:
        v = o["value"]
        if v in seen:
            continue
        seen.add(v)
        out.append(o)
    return out


def build_result_table_presentation_options(
    db: Session,
    *,
    tipo: str,
    agrupar_por: str | None,
    variable: str | None = None,
) -> dict[str, Any]:
    tipo_key = tipo.strip()
    cfg = CONFIGS.get(tipo_key) or {}
    variable_default = variable if (variable and variable.strip()) else cfg.get(
        "variable_default"
    )
    de = get_data_explorer_filters(tipo_key, variable_default)

    ap = (agrupar_por or "").strip().upper()
    if not ap:
        ap = str(cfg.get("agrupar_por") or "TECNOLOGIA").upper()

    raw_options: list[dict[str, Any]] = []

    if ap == "TECNOLOGIA":
        prefixes = list(de.get("technology_prefixes") or [])
        if prefixes:
            conds = [Technology.name.startswith(p) for p in prefixes]
            stmt = (
                select(Technology.name)
                .where(Technology.is_active.is_(True))
                .where(or_(*conds))
                .order_by(Technology.name.asc())
            )
            for code in db.scalars(stmt).all():
                raw_options.append(
                    {"value": get_label(str(code)), "code": str(code)}
                )

    elif ap == "FUEL":
        fuel_names = list(de.get("fuel_names") or [])
        fuel_prefixes = list(de.get("fuel_prefixes") or [])
        stmt = select(Fuel.name).where(Fuel.is_active.is_(True))
        fuel_conds: list[Any] = []
        if fuel_names:
            fuel_conds.append(Fuel.name.in_(fuel_names))
        if fuel_prefixes:
            fuel_conds.append(or_(*[Fuel.name.startswith(p) for p in fuel_prefixes]))
        if fuel_conds:
            stmt = stmt.where(or_(*fuel_conds))
            for code in db.scalars(stmt.order_by(Fuel.name.asc())).all():
                raw_options.append(
                    {"value": get_label(str(code)), "code": str(code)}
                )

    elif ap == "SECTOR":
        for code, sector_name in MAPA_SECTOR.items():
            raw_options.append({"value": sector_name, "code": code})
        raw_options.sort(key=lambda x: x["value"])

    elif ap == "EMISION":
        emission_names = list(de.get("emission_names") or [])
        codes: list[str] = []
        if emission_names:
            stmt = (
                select(Emission.name)
                .where(Emission.is_active.is_(True))
                .where(Emission.name.in_(emission_names))
                .order_by(Emission.name.asc())
            )
            codes = [str(c) for c in db.scalars(stmt).all()]
            if not codes:
                codes = emission_names
        for code in codes:
            raw_options.append({"value": get_label(str(code)), "code": str(code)})

    elif ap == "REGION":
        stmt = (
            select(Region.name)
            .where(Region.is_active.is_(True))
            .order_by(Region.name.asc())
        )
        for code in db.scalars(stmt).all():
            raw_options.append({"value": get_label(str(code)), "code": str(code)})

    series_options = _dedupe_by_value(raw_options)
    category_keys = [
        str(y) for y in range(YEAR_CATEGORY_MIN, YEAR_CATEGORY_MAX + 1)
    ]

    return {
        "series_options": series_options,
        "category_keys": category_keys,
        "agrupar_por_resolved": ap,
    }
