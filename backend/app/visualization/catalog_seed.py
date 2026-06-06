"""Siembra completa del catálogo de visualización desde ``configs_legacy``."""

from __future__ import annotations

import inspect
import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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
    CatalogMetaVariableUnit,
)
from app.visualization import chart_menu, configs_legacy, data_explorer_filters
from app.visualization.colors import (
    COLOR_BASE_FAMILIA,
    COLOR_MAP_PWR,
    COLORES_EMISIONES,
    COLORES_GRUPOS,
    FAMILIAS_TEC,
)
from app.visualization.configs_comparacion import COLORES_SECTOR, MAPA_SECTOR, CONFIGS_COMPARACION
from app.visualization.configs_registry import COLOR_FN_NAME_TO_KEY, FILTER_FN_SPECS
from app.visualization.labels import DISPLAY_NAMES

logger = logging.getLogger(__name__)

_GROUP_PREFIXES = (
    "TECNOLOGIAS_",
    "COMBUSTIBLES_",
    "FUELS_",
    "TEC_RES_",
    "SUBFILTROS_",
)


def _collect_legacy_groups() -> dict[str, tuple[list | set, str]]:
    """Nombre → (valores, entity_type)."""
    out: dict[str, tuple[list | set, str]] = {}
    mod = configs_legacy
    for name, val in vars(mod).items():
        if not isinstance(name, str):
            continue
        if name.startswith("TECNOLOGIAS_") or name.startswith("TEC_RES_"):
            if isinstance(val, (list, set, frozenset)):
                out[name] = (val, "TECHNOLOGY")
        elif name.startswith("COMBUSTIBLES_") or name.startswith("FUELS_"):
            if isinstance(val, (list, set, frozenset)):
                out[name] = (val, "FUEL")
    if hasattr(mod, "FUEL_VALIDOS_DEMANDA"):
        out["FUEL_VALIDOS_DEMANDA"] = (mod.FUEL_VALIDOS_DEMANDA, "FUEL")
    return out


def _subfiltro_group_maps() -> dict[str, dict[str, str]]:
    """SUBFILTROS_* → {sub_code: group_code}."""
    maps: dict[str, dict[str, str]] = {}
    mod = configs_legacy
    list_id_to_name = {
        id(v): k
        for k, v in vars(mod).items()
        if isinstance(v, (list, set, frozenset))
    }
    for name, val in vars(mod).items():
        if not name.startswith("SUBFILTROS_") or not isinstance(val, dict):
            continue
        entry: dict[str, str] = {}
        for sub_code, tech_list in val.items():
            gname = list_id_to_name.get(id(tech_list))
            if gname:
                entry[sub_code] = gname
        maps[name] = entry
    return maps


def seed_filter_groups(db: Session) -> dict[str, int]:
    """Inserta grupos y miembros desde configs_legacy."""
    db.execute(delete(CatalogMetaFilterMember))
    db.execute(delete(CatalogMetaFilterGroup))
    db.flush()

    groups = _collect_legacy_groups()
    id_by_code: dict[str, int] = {}

    for code, (values, entity) in sorted(groups.items()):
        row = CatalogMetaFilterGroup(
            code=code,
            name=code.replace("_", " ").title(),
            filter_mode="FUEL_ONLY" if entity == "FUEL" else "TECH_ONLY",
            is_system=True,
        )
        db.add(row)
        db.flush()
        id_by_code[code] = row.id
        for i, v in enumerate(sorted(values)):
            db.add(
                CatalogMetaFilterMember(
                    group_id=row.id,
                    member_kind="CODE",
                    operation="INCLUDE",
                    entity_type=entity,
                    match_mode="EXACT",
                    value=str(v),
                    sort_order=i,
                )
            )
    db.flush()
    return id_by_code


def seed_labels_colors_sectors(db: Session) -> None:
    for row in db.scalars(select(CatalogMetaLabel)).all():
        db.delete(row)
    for row in db.scalars(select(CatalogMetaColorPalette)).all():
        db.delete(row)
    for row in db.scalars(select(CatalogMetaSectorMapping)).all():
        db.delete(row)
    for row in db.scalars(select(CatalogMetaTechFamily)).all():
        db.delete(row)
    db.flush()

    for i, (code, label) in enumerate(DISPLAY_NAMES.items()):
        db.add(CatalogMetaLabel(code=code, label_es=label, category="technology", sort_order=i))

    for i, (code, label) in enumerate(configs_legacy.NOMBRES_COMBUSTIBLES.items()):
        db.add(
            CatalogMetaLabel(
                code=f"FUEL::{code}", label_es=label, category="fuel", sort_order=i
            )
        )

    for i, (code, label) in enumerate(configs_legacy.TITULOS_VARIABLES_CAPACIDAD.items()):
        db.add(
            CatalogMetaLabel(
                code=f"VAR_CAP::{code}", label_es=label, category="var_capacidad", sort_order=i
            )
        )

    sources: list[tuple[str, dict[str, str]]] = [
        ("fuel", COLORES_GRUPOS),
        ("pwr", COLOR_MAP_PWR),
        ("sector", COLORES_SECTOR),
        ("emission", COLORES_EMISIONES),
        ("family", COLOR_BASE_FAMILIA),
    ]
    for group, src in sources:
        for i, (key, color) in enumerate(src.items()):
            db.add(
                CatalogMetaColorPalette(
                    group=group, key=key, color_hex=color, sort_order=i
                )
            )

    for i, (pref, sector) in enumerate(MAPA_SECTOR.items()):
        db.add(CatalogMetaSectorMapping(tech_prefix=pref, sector_name=sector, sort_order=i))

    for family, prefixes in FAMILIAS_TEC.items():
        for i, pref in enumerate(prefixes):
            db.add(
                CatalogMetaTechFamily(
                    family_code=family, tech_prefix=pref, sort_order=i
                )
            )
    db.flush()


def _cfg_to_db_row(
    tipo: str,
    cfg: dict[str, Any],
    module_id: int,
    submodule_id: int | None,
    group_ids: dict[str, int],
    sort_order: int,
) -> dict[str, Any]:
    filtro_fn = cfg.get("filtro")
    fn_name = getattr(filtro_fn, "__name__", None) if filtro_fn else None
    spec = FILTER_FN_SPECS.get(fn_name or "", {"group": "TECNOLOGIAS_PWR"})
    filtro_kind = spec.get("kind", "group")
    filtro_group_id = None
    if "group" in spec:
        filtro_group_id = group_ids.get(spec["group"])
    elif "root_group" in spec:
        filtro_group_id = group_ids.get(spec["root_group"])
    elif "tech_group" in spec:
        filtro_group_id = group_ids.get(spec["tech_group"])

    filtro_params = dict(spec)
    if fn_name:
        filtro_params["_filter_fn"] = fn_name

    color_fn = cfg.get("color_fn")
    color_key = "none"
    if color_fn is not None:
        color_key = COLOR_FN_NAME_TO_KEY.get(color_fn.__name__, "tecnologias")

    flags: dict[str, Any] = {}
    for k in (
        "es_capacidad",
        "es_porcentaje",
        "split_refineries_by_fuel",
        "allowedGroupings",
        "soportaPareto",
        "soportaPorcentaje",
        "soportaTabla",
        "has_sub",
    ):
        if k in cfg:
            flags[k] = cfg[k]
    if cfg.get("has_sub"):
        flags["has_sub_filtro"] = True
        flags["sub_filtro_label"] = cfg.get("sub_filtro_label")
        if cfg.get("sub_filtros"):
            flags["sub_filtros"] = cfg["sub_filtros"]

    titulo = cfg.get("titulo") or cfg.get("titulo_base") or tipo
    de = data_explorer_filters.DATA_EXPLORER_FILTERS.get(tipo)

    return {
        "tipo": tipo,
        "module_id": module_id,
        "submodule_id": submodule_id,
        "label_titulo": titulo,
        "label_figura": cfg.get("figura") or cfg.get("figura_base"),
        "variable_default": cfg.get("variable_default", "UseByTechnology"),
        "filtro_kind": filtro_kind if fn_name != "_filtro_otros" else "startswith",
        "filtro_group_id": filtro_group_id,
        "filtro_params_json": filtro_params,
        "agrupar_por_default": cfg.get("agrupar_por", "TECNOLOGIA"),
        "agrupaciones_permitidas_json": cfg.get("allowedGroupings"),
        "color_fn_key": color_key,
        "flags_json": flags or None,
        "msg_sin_datos": cfg.get("msg_sin_datos"),
        "data_explorer_filters_json": de,
        "is_visible": True,
        "sort_order": sort_order,
    }


def seed_chart_hierarchy(db: Session, group_ids: dict[str, int]) -> None:
    for row in db.scalars(select(CatalogMetaChartSubfilter)).all():
        db.delete(row)
    for row in db.scalars(select(CatalogMetaChartConfig)).all():
        db.delete(row)
    for row in db.scalars(select(CatalogMetaChartSubmodule)).all():
        db.delete(row)
    for row in db.scalars(select(CatalogMetaChartModule)).all():
        db.delete(row)
    db.flush()

    module_ids: dict[str, int] = {}
    for i, m in enumerate(chart_menu.MENU):
        mod = CatalogMetaChartModule(
            code=m["code"], label=m["label"], icon=m.get("icon"), sort_order=i
        )
        db.add(mod)
        db.flush()
        module_ids[m["code"]] = mod.id

    submodule_ids: dict[tuple[str, str], int] = {}
    for m in chart_menu.MENU:
        if not m.get("subs"):
            continue
        mod_id = module_ids[m["code"]]
        for i, sub in enumerate(m["subs"]):
            sm = CatalogMetaChartSubmodule(
                module_id=mod_id,
                code=sub["code"],
                label=sub["label"],
                sort_order=i,
            )
            db.add(sm)
            db.flush()
            submodule_ids[(m["code"], sub["code"])] = sm.id

    subfiltro_maps = _subfiltro_group_maps()
    sort_idx = 0
    chart_id_by_tipo: dict[str, int] = {}

    for module, submodule, chart in chart_menu.iter_charts():
        sort_idx += 1
        tipo = chart["tipo"]
        legacy_cfg = configs_legacy.CONFIGS.get(tipo, {})
        mod_id = module_ids[module["code"]]
        sub_id = (
            submodule_ids.get((module["code"], submodule["code"]))
            if submodule
            else None
        )
        row_data = _cfg_to_db_row(tipo, legacy_cfg, mod_id, sub_id, group_ids, sort_idx)
        cc = CatalogMetaChartConfig(**row_data)
        db.add(cc)
        db.flush()
        chart_id_by_tipo[tipo] = cc.id

        sub_filtros = chart.get("sub_filtros") or legacy_cfg.get("sub_filtros") or []
        fn_name = getattr(legacy_cfg.get("filtro"), "__name__", "")
        spec = FILTER_FN_SPECS.get(fn_name, {})
        sub_dict_name = spec.get("subfiltros_dict")
        sub_map = subfiltro_maps.get(sub_dict_name or "", {})

        for i, code in enumerate(sub_filtros):
            fg_id = group_ids.get(sub_map.get(code, ""))
            db.add(
                CatalogMetaChartSubfilter(
                    chart_id=cc.id,
                    group_label=chart.get("sub_label") or legacy_cfg.get("sub_filtro_label"),
                    code=code,
                    display_label=configs_legacy.NOMBRES_COMBUSTIBLES.get(code, code),
                    filter_group_id=fg_id,
                    sort_order=i,
                )
            )

    # Charts en CONFIGS que no están en MENU
    for tipo, legacy_cfg in configs_legacy.CONFIGS.items():
        if tipo in chart_id_by_tipo:
            continue
        sort_idx += 1
        first_mod = next(iter(module_ids.values()))
        row_data = _cfg_to_db_row(tipo, legacy_cfg, first_mod, None, group_ids, sort_idx)
        cc = CatalogMetaChartConfig(**row_data)
        db.add(cc)
        db.flush()
        chart_id_by_tipo[tipo] = cc.id

    db.flush()


def seed_variable_units(db: Session) -> None:
    db.execute(delete(CatalogMetaVariableUnit))
    db.flush()
    db.add(
        CatalogMetaVariableUnit(
            variable_name="__DEFAULT_ENERGY__",
            unit_base="PJ",
            display_units_json=[
                {"code": "PJ", "label": "PJ", "factor": 1.0},
                {"code": "GW", "label": "GW", "factor": 1.0 / 31.536},
                {"code": "MW", "label": "MW", "factor": 1.0 / 0.031536},
                {"code": "TWh", "label": "TWh", "factor": 1.0 / 3.6},
            ],
        )
    )
    db.add(
        CatalogMetaVariableUnit(
            variable_name="__DEFAULT_EMISSION__",
            unit_base="MtCO2eq",
            display_units_json=[
                {"code": "MtCO2eq", "label": "MtCO₂eq", "factor": 1.0},
                {"code": "ktCO2eq", "label": "ktCO₂eq", "factor": 1000.0},
            ],
        )
    )
    db.flush()


def seed_visualization_catalog(db: Session) -> dict[str, Any]:
    """Siembra idempotente-destructiva (reemplaza catálogo completo)."""
    logger.info("Seeding visualization catalog from configs_legacy...")
    group_ids = seed_filter_groups(db)
    seed_labels_colors_sectors(db)
    seed_chart_hierarchy(db, group_ids)
    seed_variable_units(db)
    db.commit()
    return {
        "filter_groups": len(group_ids),
        "charts": len(configs_legacy.CONFIGS),
        "comparison_configs": len(CONFIGS_COMPARACION),
    }


def get_subfiltro_maps_from_db(db: Session) -> dict[str, dict[str, str]]:
    """Construye mapas sub_filtro → group_code desde subfilters con filter_group."""
    out: dict[str, dict[str, str]] = {}
    rows = db.execute(
        select(
            CatalogMetaChartConfig.tipo,
            CatalogMetaChartSubfilter.code,
            CatalogMetaFilterGroup.code,
        )
        .join(
            CatalogMetaChartSubfilter,
            CatalogMetaChartSubfilter.chart_id == CatalogMetaChartConfig.id,
        )
        .outerjoin(
            CatalogMetaFilterGroup,
            CatalogMetaFilterGroup.id == CatalogMetaChartSubfilter.filter_group_id,
        )
    ).all()
    fn_to_dict = {
        spec.get("subfiltros_dict"): fn
        for fn, spec in FILTER_FN_SPECS.items()
        if spec.get("subfiltros_dict")
    }
    tipo_to_dict: dict[str, str] = {}
    for tipo, cfg in configs_legacy.CONFIGS.items():
        fn = getattr(cfg.get("filtro"), "__name__", None)
        if fn and fn in FILTER_FN_SPECS:
            d = FILTER_FN_SPECS[fn].get("subfiltros_dict")
            if d:
                tipo_to_dict[tipo] = d

    for tipo, sub_code, group_code in rows:
        if not group_code:
            continue
        dict_name = tipo_to_dict.get(tipo)
        if not dict_name:
            continue
        out.setdefault(dict_name, {})[sub_code] = group_code
    if not out:
        out = _subfiltro_group_maps()
    return out
