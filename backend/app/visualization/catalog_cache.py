"""Cache en memoria del catálogo de visualización (BD obligatoria)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.catalog_meta import (
    CatalogMetaChartConfig,
    CatalogMetaChartModule,
    CatalogMetaChartSubfilter,
    CatalogMetaChartSubmodule,
    CatalogMetaColorPalette,
    CatalogMetaFilterGroup,
    CatalogMetaFilterMember,
    CatalogMetaLabel,
    CatalogMetaSectorMapping,
    CatalogMetaTechFamily,
)
from app.visualization.configs_comparacion import CONFIGS_COMPARACION as _LEGACY_COMPARACION
from app.visualization.configs_registry import (
    COLOR_FN_REGISTRY,
    CONFIGS_CON_ALIAS_PWR,
    FILTER_FN_SPECS,
    PWR_TECH_ALIASES,
)
from app.visualization.configs_legacy import NOMBRES_COMBUSTIBLES, TITULOS_VARIABLES_CAPACIDAD
from app.visualization.filter_engine import FilterResolver, build_filter_fn
from app.visualization.catalog_seed import get_subfiltro_maps_from_db, _subfiltro_group_maps

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: "CatalogCache | None" = None

_STARTSWITH_FN_OVERRIDES: frozenset[str] = frozenset({
    "_filtro_imp_oil",
    "_filtro_exp_oil",
})


@dataclass
class CatalogCache:
    configs: dict[str, dict[str, Any]]
    menu: list[dict[str, Any]]
    labels: dict[str, str]
    colores_grupos: dict[str, str]
    colores_sector: dict[str, str]
    colores_emisiones: dict[str, str]
    mapa_sector: dict[str, str]
    familias_tec: dict[str, list[str]]
    color_map_pwr: dict[str, str]
    configs_comparacion: dict[str, Any]
    nombres_combustibles: dict[str, str]
    titulos_variables_capacidad: dict[str, str]
    filter_resolver: FilterResolver
    chart_catalog_meta: dict[str, dict[str, Any]] = field(default_factory=dict)


def _palette(db: Session, group: str) -> dict[str, str]:
    rows = db.scalars(
        select(CatalogMetaColorPalette)
        .where(CatalogMetaColorPalette.group == group)
        .order_by(CatalogMetaColorPalette.sort_order)
    ).all()
    return {r.key: r.color_hex for r in rows}


def _load_filter_groups(db: Session) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    tech: dict[str, set[str]] = {}
    fuel: dict[str, set[str]] = {}
    valid_fuel: dict[str, set[str]] = {}

    groups = db.scalars(
        select(CatalogMetaFilterGroup).options(joinedload(CatalogMetaFilterGroup.members))
    ).unique().all()

    group_id_to_code = {g.id: g.code for g in groups}
    refs: list[tuple[str, str, str]] = []

    for g in groups:
        target_tech = tech.setdefault(g.code, set())
        target_fuel = fuel.setdefault(g.code, set())
        for m in sorted(g.members, key=lambda x: x.sort_order):
            if m.member_kind == "GROUP_REF" and m.ref_group_id:
                refs.append((g.code, group_id_to_code.get(m.ref_group_id, ""), m.operation))
                continue
            if not m.value:
                continue
            if m.entity_type == "FUEL":
                if m.operation == "INCLUDE":
                    target_fuel.add(m.value)
            else:
                if m.operation == "INCLUDE":
                    target_tech.add(m.value)
                elif m.operation == "EXCLUDE":
                    target_tech.discard(m.value)

    for parent, child, op in refs:
        if not child:
            continue
        if op == "INCLUDE":
            tech.setdefault(parent, set()).update(tech.get(child, set()))
            fuel.setdefault(parent, set()).update(fuel.get(child, set()))
        elif op == "EXCLUDE":
            tech.setdefault(parent, set()).difference_update(tech.get(child, set()))

    if "FUEL_VALIDOS_DEMANDA" in fuel:
        valid_fuel["FUEL_VALIDOS_DEMANDA"] = fuel["FUEL_VALIDOS_DEMANDA"]

    return (
        {k: frozenset(v) for k, v in tech.items()},
        {k: frozenset(v) for k, v in fuel.items()},
        {k: frozenset(v) for k, v in valid_fuel.items()},
    )


def _build_menu(db: Session) -> list[dict[str, Any]]:
    modules = db.scalars(
        select(CatalogMetaChartModule)
        .where(CatalogMetaChartModule.is_visible.is_(True))
        .order_by(CatalogMetaChartModule.sort_order)
    ).all()
    submodules = db.scalars(
        select(CatalogMetaChartSubmodule)
        .where(CatalogMetaChartSubmodule.is_visible.is_(True))
        .order_by(CatalogMetaChartSubmodule.sort_order)
    ).all()
    charts = db.scalars(
        select(CatalogMetaChartConfig)
        .where(CatalogMetaChartConfig.is_visible.is_(True))
        .options(joinedload(CatalogMetaChartConfig.subfilters))
        .order_by(CatalogMetaChartConfig.sort_order)
    ).unique().all()

    subs_by_mod: dict[int, list] = {}
    for s in submodules:
        subs_by_mod.setdefault(s.module_id, []).append(s)

    charts_by_mod: dict[int, list] = {}
    charts_by_sub: dict[int, list] = {}
    for c in charts:
        if c.submodule_id:
            charts_by_sub.setdefault(c.submodule_id, []).append(c)
        else:
            charts_by_mod.setdefault(c.module_id, []).append(c)

    menu: list[dict[str, Any]] = []
    for mod in modules:
        entry: dict[str, Any] = {
            "code": mod.code,
            "label": mod.label,
            "icon": mod.icon,
        }
        mod_subs = subs_by_mod.get(mod.id, [])
        if mod_subs:
            entry["subs"] = []
            for sub in mod_subs:
                sub_entry = {
                    "code": sub.code,
                    "label": sub.label,
                    "charts": [_chart_to_menu(c) for c in charts_by_sub.get(sub.id, [])],
                }
                entry["subs"].append(sub_entry)
        else:
            entry["charts"] = [_chart_to_menu(c) for c in charts_by_mod.get(mod.id, [])]
        menu.append(entry)
    return menu


def _chart_to_menu(c: CatalogMetaChartConfig) -> dict[str, Any]:
    flags = c.flags_json or {}
    item: dict[str, Any] = {
        "tipo": c.tipo,
        "label": c.label_titulo,
    }
    if c.agrupaciones_permitidas_json:
        item["allowed"] = c.agrupaciones_permitidas_json
    if c.agrupar_por_default:
        item["default_grouping"] = c.agrupar_por_default
    if flags.get("es_capacidad"):
        item["is_capacity"] = True
    if flags.get("soporta_pareto"):
        item["soporta_pareto"] = True
    if flags.get("has_loc"):
        item["has_loc"] = True
    subs = sorted(c.subfilters, key=lambda x: x.sort_order)
    if subs:
        item["sub_filtros"] = [s.code for s in subs]
        item["sub_label"] = subs[0].group_label or flags.get("sub_filtro_label")
    elif flags.get("sub_filtros"):
        item["sub_filtros"] = flags["sub_filtros"]
        item["sub_label"] = flags.get("sub_filtro_label")
    return item


def _legacy_cfg_from_row(
    row: CatalogMetaChartConfig,
    resolver: FilterResolver,
) -> dict[str, Any]:
    raw = dict(row.filtro_params_json or {})
    fn_name = raw.pop("_filter_fn", None)
    spec = raw
    if not spec and row.filtro_kind == "startswith":
        spec = {"kind": "startswith"}
    elif not spec:
        gc = _group_code_for_row(row)
        if gc:
            spec = {"kind": "group", "group": gc}
            entity = "FUEL" if gc.startswith(("COMBUSTIBLES_", "FUELS_")) else "TECHNOLOGY"
            spec["entity"] = entity
    else:
        spec.setdefault("kind", row.filtro_kind or "group")

    if fn_name in _STARTSWITH_FN_OVERRIDES:
        spec["kind"] = "group_startswith"

    cfg: dict[str, Any] = {
        "variable_default": row.variable_default,
        "agrupar_por": row.agrupar_por_default,
        "filtro": build_filter_fn(spec, resolver) if spec else None,
        "color_fn": COLOR_FN_REGISTRY.get(row.color_fn_key),
    }
    if row.label_figura:
        if row.flags_json and row.flags_json.get("es_capacidad"):
            cfg["figura_base"] = row.label_figura
            cfg["titulo_base"] = row.label_titulo
        else:
            cfg["figura"] = row.label_figura
            cfg["titulo"] = row.label_titulo
    else:
        cfg["titulo"] = row.label_titulo

    if row.msg_sin_datos:
        cfg["msg_sin_datos"] = row.msg_sin_datos
    flags = row.flags_json or {}
    for k in (
        "es_capacidad",
        "es_porcentaje",
        "split_refineries_by_fuel",
        "allowedGroupings",
        "soportaPareto",
        "soportaPorcentaje",
        "soportaTabla",
        "has_sub",
        "sub_filtros",
        "sub_filtro_label",
    ):
        if k in flags:
            cfg[k] = flags[k]
    return cfg


def _group_code_for_row(row: CatalogMetaChartConfig) -> str | None:
    if row.filtro_group:
        return row.filtro_group.code
    return None


def load_catalog_cache(db: Session) -> CatalogCache:
    labels_rows = db.scalars(select(CatalogMetaLabel).order_by(CatalogMetaLabel.sort_order)).all()
    labels = {r.code: r.label_es for r in labels_rows}

    sector_rows = db.scalars(
        select(CatalogMetaSectorMapping).order_by(CatalogMetaSectorMapping.sort_order)
    ).all()
    mapa_sector = {r.tech_prefix: r.sector_name for r in sector_rows}

    fam_rows = db.scalars(
        select(CatalogMetaTechFamily).order_by(CatalogMetaTechFamily.sort_order)
    ).all()
    familias: dict[str, list[str]] = {}
    for r in fam_rows:
        familias.setdefault(r.family_code, []).append(r.tech_prefix)

    tech_groups, fuel_groups, valid_fuel = _load_filter_groups(db)
    sub_maps = get_subfiltro_maps_from_db(db) or _subfiltro_group_maps()
    resolver = FilterResolver(tech_groups, fuel_groups, sub_maps, valid_fuel)

    chart_rows = db.scalars(
        select(CatalogMetaChartConfig)
        .options(
            joinedload(CatalogMetaChartConfig.filtro_group),
            joinedload(CatalogMetaChartConfig.subfilters),
        )
    ).unique().all()

    configs: dict[str, dict[str, Any]] = {}
    chart_meta: dict[str, dict[str, Any]] = {}
    for row in chart_rows:
        configs[row.tipo] = _legacy_cfg_from_row(row, resolver)
        chart_meta[row.tipo] = {
            "id": row.id,
            "data_explorer_filters": row.data_explorer_filters_json,
            "flags": row.flags_json,
        }

    if not configs:
        raise RuntimeError(
            "Catálogo de visualización vacío en BD. Ejecute `alembic upgrade head`."
        )

    nombres = {
        k.replace("FUEL::", ""): v
        for k, v in labels.items()
        if k.startswith("FUEL::")
    }
    if not nombres:
        nombres = dict(NOMBRES_COMBUSTIBLES)

    titulos = {
        k.replace("VAR_CAP::", ""): v
        for k, v in labels.items()
        if k.startswith("VAR_CAP::")
    }
    if not titulos:
        titulos = dict(TITULOS_VARIABLES_CAPACIDAD)

    return CatalogCache(
        configs=configs,
        menu=_build_menu(db),
        labels=labels,
        colores_grupos=_palette(db, "fuel"),
        colores_sector=_palette(db, "sector"),
        colores_emisiones=_palette(db, "emission"),
        mapa_sector=mapa_sector,
        familias_tec=familias,
        color_map_pwr=_palette(db, "pwr"),
        configs_comparacion=dict(_LEGACY_COMPARACION),
        nombres_combustibles=nombres,
        titulos_variables_capacidad=titulos,
        filter_resolver=resolver,
        chart_catalog_meta=chart_meta,
    )


def warm_catalog_cache(db: Session) -> CatalogCache:
    global _cache
    loaded = load_catalog_cache(db)
    with _lock:
        _cache = loaded
    logger.info("Catalog cache warmed: %d chart configs", len(loaded.configs))
    return loaded


def get_catalog_cache() -> CatalogCache:
    if _cache is None:
        raise RuntimeError(
            "Catálogo de visualización no inicializado. "
            "El API debe cargar el cache al startup."
        )
    return _cache


def invalidate_catalog_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def reload_catalog_cache(db: Session) -> CatalogCache:
    invalidate_catalog_cache()
    return warm_catalog_cache(db)
