"""Servicio de administración del catálogo de visualización."""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models import User
from app.models.catalog_meta import (
    CatalogMetaChartConfig,
    CatalogMetaChartModule,
    CatalogMetaChartSubfilter,
    CatalogMetaChartSubmodule,
    CatalogMetaColorPalette,
    CatalogMetaFilterGroup,
    CatalogMetaFilterMember,
    CatalogMetaLabel,
)
from app.services.chart_series_config_service import require_reports_admin
from app.visualization.catalog_cache import reload_catalog_cache
from app.visualization.configs_registry import COLOR_FN_REGISTRY

GROUPING_AXES: list[tuple[str, str]] = [
    ("TECNOLOGIA", "Por Tecnología"),
    ("FUEL", "Por combustible"),
    ("SECTOR", "Por Sector"),
    ("TRANSPORTE_GRUPO", "Por Grupo Transporte"),
    ("MODO", "Por Modo"),
    ("REGION", "Por Región"),
    ("EMISION", "Por Emisión"),
    ("H2_PRODUCCION", "Por producción H2"),
    ("GROUP", "Por Grupo"),
    ("YEAR", "Por Año"),
]

FILTRO_KINDS = ["group", "startswith", "sector_sub_loc", "prefix", "all"]
FILTER_MODES = ["TECH_ONLY", "FUEL_ONLY"]
MEMBER_OPERATIONS = ["INCLUDE", "EXCLUDE"]
ENTITY_TYPES = ["TECHNOLOGY", "FUEL"]
COLOR_GROUPS = ["fuel", "pwr", "sector", "emission", "family"]


def _touch_modified(row: object, user: User) -> None:
    if hasattr(row, "modified_by"):
        row.modified_by = user.id  # type: ignore[attr-defined]


def _commit_and_reload(db: Session) -> None:
    db.commit()
    reload_catalog_cache(db)


# ── Form options ─────────────────────────────────────────────────────────────


def get_form_options(db: Session) -> dict[str, Any]:
    modules = list(
        db.scalars(
            select(CatalogMetaChartModule).order_by(CatalogMetaChartModule.sort_order)
        ).all()
    )
    submodules = list(
        db.scalars(
            select(CatalogMetaChartSubmodule).order_by(
                CatalogMetaChartSubmodule.module_id,
                CatalogMetaChartSubmodule.sort_order,
            )
        ).all()
    )
    categories = list(
        db.scalars(
            select(CatalogMetaLabel.category)
            .where(CatalogMetaLabel.category.isnot(None))
            .distinct()
            .order_by(CatalogMetaLabel.category)
        ).all()
    )
    return {
        "grouping_axes": [{"value": v, "label": lbl} for v, lbl in GROUPING_AXES],
        "color_fn_keys": sorted(COLOR_FN_REGISTRY.keys()),
        "filtro_kinds": FILTRO_KINDS,
        "filter_modes": FILTER_MODES,
        "member_operations": MEMBER_OPERATIONS,
        "entity_types": ENTITY_TYPES,
        "color_groups": COLOR_GROUPS,
        "label_categories": [c for c in categories if c],
        "modules": [
            {"id": m.id, "code": m.code, "label": m.label} for m in modules
        ],
        "submodules": [
            {"id": s.id, "module_id": s.module_id, "code": s.code, "label": s.label}
            for s in submodules
        ],
    }


# ── Filter groups ──────────────────────────────────────────────────────────────


def list_filter_groups(db: Session) -> list[CatalogMetaFilterGroup]:
    return list(
        db.scalars(
            select(CatalogMetaFilterGroup)
            .options(joinedload(CatalogMetaFilterGroup.members))
            .order_by(CatalogMetaFilterGroup.code)
        )
        .unique()
        .all()
    )


def get_filter_group(db: Session, *, code: str) -> CatalogMetaFilterGroup:
    row = db.scalar(
        select(CatalogMetaFilterGroup)
        .options(joinedload(CatalogMetaFilterGroup.members))
        .where(CatalogMetaFilterGroup.code == code)
    )
    if row is None:
        raise NotFoundError(f"Grupo de filtro {code!r} no encontrado.")
    return row


def _default_entity_type(filter_mode: str) -> str:
    return "FUEL" if filter_mode == "FUEL_ONLY" else "TECHNOLOGY"


def _assert_filter_group_not_referenced(db: Session, group_id: int) -> None:
    chart_ref = db.scalar(
        select(func.count())
        .select_from(CatalogMetaChartConfig)
        .where(CatalogMetaChartConfig.filtro_group_id == group_id)
    )
    sub_ref = db.scalar(
        select(func.count())
        .select_from(CatalogMetaChartSubfilter)
        .where(CatalogMetaChartSubfilter.filter_group_id == group_id)
    )
    if (chart_ref or 0) > 0 or (sub_ref or 0) > 0:
        raise ConflictError(
            "El grupo está referenciado por una o más gráficas o subfiltros."
        )


def create_filter_group(
    db: Session,
    *,
    data: dict[str, Any],
    current_user: User,
) -> CatalogMetaFilterGroup:
    require_reports_admin(current_user)
    code = str(data["code"]).strip()
    if db.scalar(select(CatalogMetaFilterGroup.id).where(CatalogMetaFilterGroup.code == code)):
        raise ConflictError(f"Ya existe un grupo con código {code!r}.")
    filter_mode = str(data.get("filter_mode") or "TECH_ONLY")
    row = CatalogMetaFilterGroup(
        code=code,
        name=str(data["name"]).strip(),
        description=(str(data["description"]).strip() if data.get("description") else None),
        filter_mode=filter_mode,
        is_system=False,
    )
    _touch_modified(row, current_user)
    db.add(row)
    db.flush()
    members = data.get("members") or []
    if members:
        replace_filter_group_members(
            db, code=code, members=members, current_user=current_user, commit=False
        )
    _commit_and_reload(db)
    return get_filter_group(db, code=code)


def update_filter_group(
    db: Session,
    *,
    code: str,
    data: dict[str, Any],
    current_user: User,
) -> CatalogMetaFilterGroup:
    require_reports_admin(current_user)
    row = get_filter_group(db, code=code)
    if data.get("name") is not None:
        row.name = str(data["name"]).strip()
    if "description" in data:
        d = data["description"]
        row.description = str(d).strip() if d else None
    if data.get("filter_mode") is not None:
        row.filter_mode = str(data["filter_mode"]).strip()
    _touch_modified(row, current_user)
    db.add(row)
    _commit_and_reload(db)
    return get_filter_group(db, code=code)


def delete_filter_group(db: Session, *, code: str, current_user: User) -> None:
    require_reports_admin(current_user)
    row = get_filter_group(db, code=code)
    _assert_filter_group_not_referenced(db, row.id)
    db.delete(row)
    _commit_and_reload(db)


def _member_rows_from_payload(
    members: list[dict[str, Any]],
    *,
    filter_mode: str,
    group_id: int,
) -> list[CatalogMetaFilterMember]:
    default_et = _default_entity_type(filter_mode)
    rows: list[CatalogMetaFilterMember] = []
    for i, m in enumerate(members):
        rows.append(
            CatalogMetaFilterMember(
                group_id=group_id,
                member_kind=str(m.get("member_kind") or "CODE"),
                operation=str(m.get("operation") or "INCLUDE"),
                entity_type=str(m.get("entity_type") or default_et),
                match_mode=str(m.get("match_mode") or "EXACT"),
                value=(str(m["value"]).strip() if m.get("value") else None),
                ref_group_id=m.get("ref_group_id"),
                sort_order=int(m.get("sort_order") if m.get("sort_order") is not None else i),
            )
        )
    return rows


def replace_filter_group_members(
    db: Session,
    *,
    code: str,
    members: list[dict[str, Any]],
    current_user: User,
    commit: bool = True,
) -> CatalogMetaFilterGroup:
    require_reports_admin(current_user)
    row = get_filter_group(db, code=code)
    db.execute(
        delete(CatalogMetaFilterMember).where(CatalogMetaFilterMember.group_id == row.id)
    )
    for member in _member_rows_from_payload(
        members, filter_mode=row.filter_mode, group_id=row.id
    ):
        db.add(member)
    _touch_modified(row, current_user)
    db.add(row)
    if commit:
        _commit_and_reload(db)
    else:
        db.flush()
    return get_filter_group(db, code=code)


def parse_members_import_text(
    text: str,
    *,
    filter_mode: str,
) -> list[dict[str, Any]]:
    """Parsea CSV/pegado: columnas code[,operation][,entity_type] o una columna."""
    default_et = _default_entity_type(filter_mode)
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return []

    reader: csv.reader
    first = lines[0].lower()
    has_header = "code" in first or "valor" in first or "value" in first
    if has_header:
        reader = csv.reader(io.StringIO("\n".join(lines)))
        header = [h.strip().lower() for h in next(reader)]
        code_idx = next(
            (i for i, h in enumerate(header) if h in ("code", "valor", "value", "codigo")),
            0,
        )
        op_idx = next(
            (i for i, h in enumerate(header) if h in ("operation", "operacion", "op")),
            None,
        )
        et_idx = next(
            (i for i, h in enumerate(header) if h in ("entity_type", "tipo", "entity")),
            None,
        )
        rows: list[dict[str, Any]] = []
        for i, parts in enumerate(reader):
            if not parts or not parts[code_idx].strip():
                continue
            rows.append(
                {
                    "value": parts[code_idx].strip(),
                    "operation": (
                        parts[op_idx].strip().upper()
                        if op_idx is not None and op_idx < len(parts)
                        else "INCLUDE"
                    ),
                    "entity_type": (
                        parts[et_idx].strip().upper()
                        if et_idx is not None and et_idx < len(parts)
                        else default_et
                    ),
                    "sort_order": i,
                }
            )
        return rows

    rows = []
    for i, line in enumerate(lines):
        if "," in line or ";" in line or "\t" in line:
            parts = re.split(r"[,;\t]", line)
            code = parts[0].strip()
            op = parts[1].strip().upper() if len(parts) > 1 else "INCLUDE"
            et = parts[2].strip().upper() if len(parts) > 2 else default_et
        else:
            code, op, et = line.strip(), "INCLUDE", default_et
        if code:
            rows.append({"value": code, "operation": op, "entity_type": et, "sort_order": i})
    return rows


def import_filter_group_members(
    db: Session,
    *,
    code: str,
    text: str,
    mode: str,
    current_user: User,
) -> CatalogMetaFilterGroup:
    require_reports_admin(current_user)
    row = get_filter_group(db, code=code)
    parsed = parse_members_import_text(text, filter_mode=row.filter_mode)
    if mode == "replace":
        return replace_filter_group_members(
            db, code=code, members=parsed, current_user=current_user
        )
    existing = [
        {
            "member_kind": m.member_kind,
            "operation": m.operation,
            "entity_type": m.entity_type,
            "match_mode": m.match_mode,
            "value": m.value,
            "ref_group_id": m.ref_group_id,
            "sort_order": m.sort_order,
        }
        for m in sorted(row.members, key=lambda x: x.sort_order)
    ]
    seen = {(m.get("value"), m.get("entity_type")) for m in existing if m.get("value")}
    for p in parsed:
        key = (p.get("value"), p.get("entity_type"))
        if key not in seen:
            existing.append(p)
            seen.add(key)
    return replace_filter_group_members(
        db, code=code, members=existing, current_user=current_user
    )


def resolve_filter_group(db: Session, *, code: str) -> dict[str, Any]:
    from app.visualization.catalog_cache import load_catalog_cache

    cache = load_catalog_cache(db)
    resolver = cache.filter_resolver
    try:
        tech = sorted(resolver.tech(code))
    except KeyError:
        tech = []
    try:
        fuel = sorted(resolver.fuel(code))
    except KeyError:
        fuel = []
    return {"code": code, "technology_codes": tech, "fuel_codes": fuel}


# ── Labels ───────────────────────────────────────────────────────────────────


def list_labels(
    db: Session,
    *,
    category: str | None = None,
    q: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> list[CatalogMetaLabel] | dict[str, Any]:
    stmt = select(CatalogMetaLabel)
    if category:
        stmt = stmt.where(CatalogMetaLabel.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                CatalogMetaLabel.code.ilike(like),
                CatalogMetaLabel.label_es.ilike(like),
                CatalogMetaLabel.label_en.ilike(like),
            )
        )
    stmt = stmt.order_by(CatalogMetaLabel.code)

    if page is not None and page_size is not None:
        count_stmt = select(func.count()).select_from(CatalogMetaLabel)
        if category:
            count_stmt = count_stmt.where(CatalogMetaLabel.category == category)
        if q:
            like = f"%{q.strip()}%"
            count_stmt = count_stmt.where(
                or_(
                    CatalogMetaLabel.code.ilike(like),
                    CatalogMetaLabel.label_es.ilike(like),
                    CatalogMetaLabel.label_en.ilike(like),
                )
            )
        total = db.scalar(count_stmt) or 0
        page = max(1, page)
        page_size = max(1, min(200, page_size))
        items = list(
            db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        )
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    return list(db.scalars(stmt).all())


def create_label(
    db: Session,
    *,
    data: dict[str, Any],
    current_user: User,
) -> CatalogMetaLabel:
    require_reports_admin(current_user)
    code = str(data["code"]).strip()
    if db.scalar(select(CatalogMetaLabel.id).where(CatalogMetaLabel.code == code)):
        raise ConflictError(f"Ya existe un label con código {code!r}.")
    row = CatalogMetaLabel(
        code=code,
        label_es=str(data["label_es"]).strip(),
        label_en=(str(data["label_en"]).strip() if data.get("label_en") else None),
        category=(str(data["category"]).strip() if data.get("category") else None),
    )
    _touch_modified(row, current_user)
    db.add(row)
    _commit_and_reload(db)
    db.refresh(row)
    return row


def update_label(
    db: Session,
    *,
    row_id: int,
    data: dict[str, Any],
    current_user: User,
) -> CatalogMetaLabel:
    require_reports_admin(current_user)
    row = db.get(CatalogMetaLabel, row_id)
    if row is None:
        raise NotFoundError("Label no encontrado.")
    if data.get("label_es") is not None:
        row.label_es = str(data["label_es"]).strip()
    if "label_en" in data:
        v = data["label_en"]
        row.label_en = str(v).strip() if v else None
    if "category" in data:
        v = data["category"]
        row.category = str(v).strip() if v else None
    _touch_modified(row, current_user)
    db.add(row)
    _commit_and_reload(db)
    db.refresh(row)
    return row


def delete_label(db: Session, *, row_id: int, current_user: User) -> None:
    require_reports_admin(current_user)
    row = db.get(CatalogMetaLabel, row_id)
    if row is None:
        raise NotFoundError("Label no encontrado.")
    db.delete(row)
    _commit_and_reload(db)


# ── Colors ───────────────────────────────────────────────────────────────────


def list_colors(db: Session, *, group: str | None = None) -> list[CatalogMetaColorPalette]:
    stmt = select(CatalogMetaColorPalette).order_by(
        CatalogMetaColorPalette.group, CatalogMetaColorPalette.sort_order
    )
    if group:
        stmt = stmt.where(CatalogMetaColorPalette.group == group)
    return list(db.scalars(stmt).all())


def create_color(
    db: Session,
    *,
    data: dict[str, Any],
    current_user: User,
) -> CatalogMetaColorPalette:
    require_reports_admin(current_user)
    grp = str(data["group"]).strip()
    key = str(data["key"]).strip()
    exists = db.scalar(
        select(CatalogMetaColorPalette.id).where(
            CatalogMetaColorPalette.group == grp,
            CatalogMetaColorPalette.key == key,
        )
    )
    if exists:
        raise ConflictError(f"Ya existe color {grp}/{key!r}.")
    row = CatalogMetaColorPalette(
        group=grp,
        key=key,
        color_hex=str(data["color_hex"]).strip(),
        sort_order=int(data.get("sort_order") or 0),
    )
    _touch_modified(row, current_user)
    db.add(row)
    _commit_and_reload(db)
    db.refresh(row)
    return row


def update_color(
    db: Session,
    *,
    row_id: int,
    data: dict[str, Any],
    current_user: User,
) -> CatalogMetaColorPalette:
    require_reports_admin(current_user)
    row = db.get(CatalogMetaColorPalette, row_id)
    if row is None:
        raise NotFoundError("Color no encontrado.")
    if data.get("group") is not None:
        row.group = str(data["group"]).strip()
    if data.get("key") is not None:
        row.key = str(data["key"]).strip()
    if data.get("color_hex") is not None:
        row.color_hex = str(data["color_hex"]).strip()
    if data.get("sort_order") is not None:
        row.sort_order = int(data["sort_order"])
    _touch_modified(row, current_user)
    db.add(row)
    _commit_and_reload(db)
    db.refresh(row)
    return row


def delete_color(db: Session, *, row_id: int, current_user: User) -> None:
    require_reports_admin(current_user)
    row = db.get(CatalogMetaColorPalette, row_id)
    if row is None:
        raise NotFoundError("Color no encontrado.")
    db.delete(row)
    _commit_and_reload(db)


# ── Chart configs ────────────────────────────────────────────────────────────


def list_chart_configs(db: Session) -> list[CatalogMetaChartConfig]:
    return list(
        db.scalars(
            select(CatalogMetaChartConfig).order_by(CatalogMetaChartConfig.sort_order)
        ).all()
    )


def get_chart_config(db: Session, *, tipo: str) -> CatalogMetaChartConfig:
    row = db.scalar(
        select(CatalogMetaChartConfig)
        .options(joinedload(CatalogMetaChartConfig.subfilters))
        .where(CatalogMetaChartConfig.tipo == tipo)
    )
    if row is None:
        raise NotFoundError(f"Gráfica {tipo!r} no encontrada.")
    return row


def _apply_subfilters(
    db: Session,
    chart: CatalogMetaChartConfig,
    subfilters: list[dict[str, Any]],
    user: User,
) -> None:
    db.execute(
        delete(CatalogMetaChartSubfilter).where(
            CatalogMetaChartSubfilter.chart_id == chart.id
        )
    )
    for i, sf in enumerate(subfilters):
        sub = CatalogMetaChartSubfilter(
            chart_id=chart.id,
            code=str(sf["code"]).strip(),
            display_label=(str(sf["display_label"]).strip() if sf.get("display_label") else None),
            group_label=(str(sf["group_label"]).strip() if sf.get("group_label") else None),
            filter_group_id=sf.get("filter_group_id"),
            sort_order=int(sf.get("sort_order") if sf.get("sort_order") is not None else i),
            default_selected=bool(sf.get("default_selected", False)),
        )
        _touch_modified(sub, user)
        db.add(sub)


def create_chart_config(
    db: Session,
    *,
    data: dict[str, Any],
    current_user: User,
) -> CatalogMetaChartConfig:
    require_reports_admin(current_user)
    tipo = str(data["tipo"]).strip()
    if db.scalar(select(CatalogMetaChartConfig.id).where(CatalogMetaChartConfig.tipo == tipo)):
        raise ConflictError(f"Ya existe una gráfica con tipo {tipo!r}.")
    row = CatalogMetaChartConfig(
        tipo=tipo,
        module_id=int(data["module_id"]),
        submodule_id=data.get("submodule_id"),
        label_titulo=str(data["label_titulo"]).strip(),
        label_figura=(str(data["label_figura"]).strip() if data.get("label_figura") else None),
        variable_default=str(data["variable_default"]).strip(),
        filtro_kind=str(data.get("filtro_kind") or "group"),
        filtro_group_id=data.get("filtro_group_id"),
        filtro_params_json=data.get("filtro_params_json"),
        agrupar_por_default=str(data.get("agrupar_por_default") or "TECNOLOGIA"),
        agrupaciones_permitidas_json=data.get("agrupaciones_permitidas_json"),
        color_fn_key=str(data.get("color_fn_key") or "tecnologias"),
        flags_json=data.get("flags_json"),
        msg_sin_datos=(str(data["msg_sin_datos"]).strip() if data.get("msg_sin_datos") else None),
        data_explorer_filters_json=data.get("data_explorer_filters_json"),
        is_visible=bool(data.get("is_visible", True)),
        sort_order=int(data.get("sort_order") or 0),
    )
    _touch_modified(row, current_user)
    db.add(row)
    db.flush()
    subfilters = data.get("subfilters") or []
    if subfilters:
        _apply_subfilters(db, row, subfilters, current_user)
    _commit_and_reload(db)
    return get_chart_config(db, tipo=tipo)


def update_chart_config(
    db: Session,
    *,
    tipo: str,
    data: dict[str, Any],
    current_user: User,
) -> CatalogMetaChartConfig:
    require_reports_admin(current_user)
    row = get_chart_config(db, tipo=tipo)
    field_map = {
        "module_id": int,
        "submodule_id": lambda v: v,
        "label_titulo": str,
        "label_figura": lambda v: str(v).strip() if v else None,
        "variable_default": str,
        "filtro_kind": str,
        "filtro_group_id": lambda v: v,
        "filtro_params_json": lambda v: v,
        "agrupar_por_default": str,
        "agrupaciones_permitidas_json": lambda v: v,
        "color_fn_key": str,
        "flags_json": lambda v: v,
        "msg_sin_datos": lambda v: str(v).strip() if v else None,
        "data_explorer_filters_json": lambda v: v,
        "is_visible": bool,
        "sort_order": int,
    }
    for key, conv in field_map.items():
        if key in data and data[key] is not None:
            val = data[key]
            setattr(row, key, conv(val) if conv is not str else str(val).strip())
        elif key in data and key in ("submodule_id", "filtro_group_id", "label_figura", "msg_sin_datos"):
            setattr(row, key, None)
    _touch_modified(row, current_user)
    db.add(row)
    if "subfilters" in data and data["subfilters"] is not None:
        _apply_subfilters(db, row, data["subfilters"], current_user)
    _commit_and_reload(db)
    return get_chart_config(db, tipo=tipo)


def delete_chart_config(db: Session, *, tipo: str, current_user: User) -> None:
    require_reports_admin(current_user)
    row = get_chart_config(db, tipo=tipo)
    db.delete(row)
    _commit_and_reload(db)


def get_menu(db: Session) -> list[dict[str, Any]]:
    from app.visualization.catalog_cache import load_catalog_cache

    return load_catalog_cache(db).menu


def repopulate_catalog(db: Session, *, current_user: User) -> dict[str, Any]:
    require_reports_admin(current_user)
    from app.visualization.catalog_seed import seed_visualization_catalog

    summary = seed_visualization_catalog(db)
    reload_catalog_cache(db)
    return summary
