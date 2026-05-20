"""CRUD y población de `chart_series_config` (series globales por tipo de gráfica)."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models import ChartSeriesConfig, Emission, Fuel, Region, Technology, User
from app.visualization.colors import (
    COLORES_EMISIONES,
    COLORES_GRUPOS,
    COLOR_MAP_PWR,
    FAMILIAS_TEC,
    _TECHS_CLASIFICADAS,
    _color_electricidad,
    asignar_grupo,
)
from app.visualization.configs import CONFIGS
from app.visualization.configs_comparacion import CONFIGS_COMPARACION, COLORES_SECTOR, MAPA_SECTOR
from app.visualization.data_explorer_filters import get_data_explorer_filters
from app.visualization.labels import get_label
from app.visualization.regional import REGION_COLORS


def normalize_agrupar_por(agrupar_por: str | None, cfg_default: str | None) -> str:
    ap = (agrupar_por or cfg_default or "TECNOLOGIA").strip().upper()
    if ap == "COMBUSTIBLE":
        return "FUEL"
    return ap


def _is_reports_admin(user: User) -> bool:
    return bool(
        getattr(user, "is_admin_reports", False)
        or getattr(user, "can_manage_scenarios", False)
    )


def require_reports_admin(user: User) -> None:
    if not _is_reports_admin(user):
        raise ForbiddenError("Se requiere permiso de administración de reportes.")


# Grupos de transporte (mismos valores que `COLOR` en modo TRANSPORTE_GRUPO)
_TRANSPORTE_GRUPOS_ORDER: list[str] = [
    "Motos",
    "Livianos",
    "Buses",
    "Microbuses",
    "Carga",
    "Barcos",
    "Metro",
    "Aviación",
    "Otros",
]

_H2_PRODUCTION_LABELS: dict[str, str] = {
    "Hidrógeno verde": "#10b981",
    "Hidrógeno azul": "#3b82f6",
    "Hidrógeno gris": "#6b7280",
}


def _uses_pwr_family_order(cfg: dict) -> bool:
    return cfg.get("color_fn") is _color_electricidad


def _order_electric_techs(codes: Sequence[str]) -> list[str]:
    present = set(codes)
    orden_familias = [
        "OTRAS",
        "BIOMASA_RESIDUOS",
        "TERMICA_FOSIL",
        "NUCLEAR",
        "HIDRO",
        "SOLAR",
        "EOLICA",
    ]
    orden_final: list[str] = []
    for familia in orden_familias:
        techs_familia = [t for t in FAMILIAS_TEC[familia] if t in present]
        orden_final.extend(sorted(techs_familia))
    techs_no_clasificadas = [
        t for t in present if str(t) not in _TECHS_CLASIFICADAS
    ]
    orden_final.extend(sorted(techs_no_clasificadas))
    return orden_final


def _initial_color_for_tech(code: str) -> str:
    c = str(code)
    if c.startswith("PWR"):
        return COLOR_MAP_PWR.get(c, "#CCCCCC")
    g = asignar_grupo(c)
    return COLORES_GRUPOS.get(g, "#999999")


def _initial_group_for_tech(code: str) -> str | None:
    c = str(code)
    if not c.startswith("PWR"):
        return None
    for fam, techs in FAMILIAS_TEC.items():
        if c in techs:
            return fam.replace("_", " ").title()
    return None


def _sector_label_codes() -> list[str]:
    names = sorted(set(MAPA_SECTOR.values()) | {"Generación Electricidad", "Otros"})
    return names


def _resolve_metadata(
    *,
    tipo: str,
    variable: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    """Metadata de CONFIGS o CONFIGS_COMPARACION + dict tipo DATA_EXPLORER_FILTERS."""
    t = tipo.strip()
    cfg = CONFIGS.get(t)
    if cfg is not None:
        var_default = (
            variable if (variable and str(variable).strip()) else cfg.get("variable_default")
        )
        de = get_data_explorer_filters(t, var_default)
        return cfg, de, var_default
    ccomp = CONFIGS_COMPARACION.get(t)
    if ccomp is not None:
        var_default = str(ccomp.get("variable_default") or "")
        prefijo = ccomp["prefijo"]
        prefixes = list(prefijo) if isinstance(prefijo, tuple) else [prefijo]
        de = {"technology_prefixes": prefixes, "fuel_names": [], "fuel_prefixes": []}
        return ccomp, de, var_default
    return None, {}, None


def _iter_populate_rows(
    db: Session,
    *,
    tipo: str,
    agrupar_por: str,
    variable: str | None = None,
) -> Iterator[tuple[str, str, str | None, str | None, int]]:
    """Yields (series_code, display_name, color, group_key, sort_index)."""
    cfg, de, _vd = _resolve_metadata(tipo=tipo, variable=variable)
    if cfg is None:
        return
    ap = agrupar_por.strip().upper()
    if ap == "TECNOLOGIA":
        from sqlalchemy import or_

        prefixes = list(de.get("technology_prefixes") or [])
        if not prefixes:
            return
        conds = [Technology.name.startswith(p) for p in prefixes]
        stmt = (
            select(Technology.name)
            .where(Technology.is_active.is_(True))
            .where(or_(*conds))
        )
        codes = [str(c) for c in db.scalars(stmt).all()]
        single_cfg = CONFIGS.get(tipo.strip())
        use_elec = bool(single_cfg and _uses_pwr_family_order(single_cfg))
        if use_elec:
            ordered = _order_electric_techs(codes)
        else:
            ordered = sorted(codes, key=lambda x: get_label(x))
        for i, code in enumerate(ordered):
            yield (
                code,
                get_label(code),
                _initial_color_for_tech(code),
                _initial_group_for_tech(code),
                i * 10,
            )

    elif ap == "GROUP":
        from sqlalchemy import or_

        prefixes = list(de.get("technology_prefixes") or [])
        if not prefixes:
            stmt = select(Technology.name).where(Technology.is_active.is_(True))
        else:
            conds = [Technology.name.startswith(p) for p in prefixes]
            stmt = (
                select(Technology.name)
                .where(Technology.is_active.is_(True))
                .where(or_(*conds))
            )
        codes = {str(c) for c in db.scalars(stmt).all()}
        groups: dict[str, str] = {}
        for code in codes:
            g = asignar_grupo(code)
            groups[g] = COLORES_GRUPOS.get(g, "#999999")
        ordered_g = sorted(groups.keys(), key=lambda x: get_label(x))
        for i, gcode in enumerate(ordered_g):
            yield (
                gcode,
                get_label(gcode),
                groups[gcode],
                None,
                i * 10,
            )

    elif ap == "FUEL":
        from sqlalchemy import or_

        fuel_names = list(de.get("fuel_names") or [])
        fuel_prefixes = list(de.get("fuel_prefixes") or [])
        stmt = select(Fuel.name).where(Fuel.is_active.is_(True))
        fuel_conds: list[Any] = []
        if fuel_names:
            fuel_conds.append(Fuel.name.in_(fuel_names))
        if fuel_prefixes:
            fuel_conds.append(or_(*[Fuel.name.startswith(p) for p in fuel_prefixes]))
        if not fuel_conds:
            stmt = select(Fuel.name).where(Fuel.is_active.is_(True)).order_by(
                Fuel.name.asc()
            )
            fuel_codes = [str(c) for c in db.scalars(stmt).all()]
        else:
            stmt = stmt.where(or_(*fuel_conds))
            fuel_codes = [str(c) for c in db.scalars(stmt.order_by(Fuel.name.asc())).all()]
        group_codes: dict[str, str] = {}
        for f in fuel_codes:
            g = asignar_grupo(f) if f else "OTRO"
            if g not in group_codes:
                group_codes[g] = COLORES_GRUPOS.get(g, "#999999")
        ordered = sorted(group_codes.keys(), key=lambda x: get_label(x))
        for i, gcode in enumerate(ordered):
            yield (
                gcode,
                get_label(gcode),
                group_codes[gcode],
                None,
                i * 10,
            )

    elif ap == "SECTOR":
        for i, name in enumerate(_sector_label_codes()):
            col = COLORES_SECTOR.get(name, "#999999")
            yield (name, name, col, None, i * 10)

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
        for i, code in enumerate(codes):
            yield (
                code,
                get_label(code),
                COLORES_EMISIONES.get(code, "#999999"),
                None,
                i * 10,
            )

    elif ap == "REGION":
        stmt = (
            select(Region.name)
            .where(Region.is_active.is_(True))
            .order_by(Region.name.asc())
        )
        codes = [str(c) for c in db.scalars(stmt).all()]
        for i, code in enumerate(codes):
            yield (
                code,
                get_label(code),
                REGION_COLORS.get(code, "#999999"),
                None,
                i * 10,
            )

    elif ap == "H2_PRODUCCION":
        for i, (label, hex_c) in enumerate(sorted(_H2_PRODUCTION_LABELS.items())):
            yield (label, label, hex_c, None, i * 10)

    elif ap == "TRANSPORTE_GRUPO":
        for i, label in enumerate(_TRANSPORTE_GRUPOS_ORDER):
            yield (
                label,
                label,
                COLORES_GRUPOS.get(label, "#999999"),
                None,
                i * 10,
            )

    elif ap == "YEAR":
        yield ("Total", "Total", "#4472c4", None, 0)


def populate_chart_type(
    db: Session,
    *,
    tipo: str,
    agrupar_por: str | None = None,
    variable: str | None = None,
) -> int:
    """Inserta filas faltantes. No modifica las existentes. Retorna N insertadas."""
    t = tipo.strip()
    cfg = CONFIGS.get(t)
    ccomp = CONFIGS_COMPARACION.get(t)
    if cfg is None and ccomp is None:
        raise ValueError(f"tipo desconocido: {tipo}")
    if cfg is not None:
        default_ap = cfg.get("agrupar_por")
    else:
        default_ap = ccomp.get("agrupacion_fija") or ccomp.get(
            "agrupacion_default", "TECNOLOGIA"
        )
    ap = normalize_agrupar_por(agrupar_por, default_ap)

    added = 0
    for series_code, display_name, color, group_key, sort_idx in _iter_populate_rows(
        db, tipo=tipo.strip(), agrupar_por=ap, variable=variable
    ):
        exists = db.scalar(
            select(ChartSeriesConfig.id).where(
                ChartSeriesConfig.tipo == tipo.strip(),
                ChartSeriesConfig.agrupar_por == ap,
                ChartSeriesConfig.series_code == series_code,
            )
        )
        if exists is not None:
            continue
        db.add(
            ChartSeriesConfig(
                tipo=tipo.strip(),
                agrupar_por=ap,
                series_code=series_code,
                display_name=display_name,
                color=color,
                hidden=False,
                sort_index=sort_idx,
                group_key=group_key,
            )
        )
        added += 1
    if added:
        db.commit()
    return added


def populate_all_chart_types(db: Session) -> int:
    total = 0
    for tipo in CONFIGS.keys():
        if tipo in ("recursos_vs_demanda", "recursos_vs_demanda_gas"):
            continue
        cfg = CONFIGS[tipo]
        ap = normalize_agrupar_por(None, cfg.get("agrupar_por"))
        try:
            total += populate_chart_type(db, tipo=tipo, agrupar_por=ap)
        except ValueError:
            continue
    for tipo, ccfg in CONFIGS_COMPARACION.items():
        ap_raw = ccfg.get("agrupacion_fija") or ccfg.get(
            "agrupacion_default", "TECNOLOGIA"
        )
        ap = normalize_agrupar_por(ap_raw, ap_raw)
        try:
            total += populate_chart_type(
                db,
                tipo=tipo,
                agrupar_por=ap,
                variable=ccfg.get("variable_default"),
            )
        except ValueError:
            continue
    return total


def list_configs(
    db: Session, *, tipo: str, agrupar_por: str
) -> list[ChartSeriesConfig]:
    stmt = (
        select(ChartSeriesConfig)
        .where(
            ChartSeriesConfig.tipo == tipo.strip(),
            ChartSeriesConfig.agrupar_por == agrupar_por.strip().upper(),
        )
        .order_by(ChartSeriesConfig.sort_index.asc(), ChartSeriesConfig.id.asc())
    )
    return list(db.scalars(stmt).all())


def create_config(
    db: Session,
    *,
    tipo: str,
    agrupar_por: str | None,
    cfg_default_agrupar: str | None,
    series_code: str,
    display_name: str | None,
    color: str | None,
    hidden: bool,
    sort_index: int | None,
    group_key: str | None,
    notes: str | None,
    current_user: User,
) -> ChartSeriesConfig:
    """Alta manual de una fila (p. ej. código presente en simulación pero fuera del populate)."""
    require_reports_admin(current_user)
    t = str(tipo).strip()[:64]
    code = str(series_code).strip()[:512]
    if not t or not code:
        raise ConflictError("tipo y series_code son obligatorios.")
    ap = normalize_agrupar_por(agrupar_por, cfg_default_agrupar)
    existing = db.scalar(
        select(ChartSeriesConfig.id).where(
            ChartSeriesConfig.tipo == t,
            ChartSeriesConfig.agrupar_por == ap,
            ChartSeriesConfig.series_code == code,
        )
    )
    if existing is not None:
        raise ConflictError(
            f"Ya existe configuración para tipo={t!r}, agrupación={ap!r}, código={code!r}."
        )

    max_si = db.scalar(
        select(func.max(ChartSeriesConfig.sort_index)).where(
            ChartSeriesConfig.tipo == t,
            ChartSeriesConfig.agrupar_por == ap,
        )
    )
    next_si = (int(max_si) + 10) if max_si is not None else 0
    si = int(sort_index) if sort_index is not None else next_si

    dn = str(display_name).strip()[:512] if display_name else get_label(code)
    if not dn:
        dn = code
    col: str | None = None
    if color not in (None, ""):
        col = str(color).strip()[:32]
    gk = str(group_key).strip()[:255] if group_key not in (None, "") else None
    nt = str(notes).strip() if notes not in (None, "") else None

    row = ChartSeriesConfig(
        tipo=t,
        agrupar_por=ap,
        series_code=code,
        display_name=dn,
        color=col,
        hidden=hidden,
        sort_index=si,
        group_key=gk,
        notes=nt,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def chart_types_catalog() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tipo, cfg in CONFIGS.items():
        if tipo in ("recursos_vs_demanda", "recursos_vs_demanda_gas"):
            continue
        out.append(
            {
                "tipo": tipo,
                "agrupar_por_default": normalize_agrupar_por(None, cfg.get("agrupar_por")),
                "source": "single",
            }
        )
    for tipo, cfg in CONFIGS_COMPARACION.items():
        ap_raw = cfg.get("agrupacion_fija") or cfg.get("agrupacion_default", "TECNOLOGIA")
        out.append(
            {
                "tipo": tipo,
                "agrupar_por_default": normalize_agrupar_por(ap_raw, ap_raw),
                "source": "comparison",
            }
        )
    return sorted(out, key=lambda x: (x["tipo"], x["source"]))


def update_config(
    db: Session,
    *,
    row_id: int,
    data: dict[str, Any],
    current_user: User,
) -> ChartSeriesConfig:
    require_reports_admin(current_user)
    row = db.get(ChartSeriesConfig, row_id)
    if row is None:
        raise NotFoundError("Configuración de serie no encontrada.")
    if "display_name" in data and data["display_name"] is not None:
        row.display_name = str(data["display_name"]).strip()[:512]
    if "color" in data:
        c = data["color"]
        row.color = str(c).strip()[:32] if c not in (None, "") else None
    if "hidden" in data and data["hidden"] is not None:
        row.hidden = bool(data["hidden"])
    if "is_global" in data and data["is_global"] is not None:
        row.is_global = bool(data["is_global"])
    if "sort_index" in data and data["sort_index"] is not None:
        row.sort_index = int(data["sort_index"])
    if "group_key" in data:
        g = data["group_key"]
        row.group_key = str(g).strip()[:255] if g not in (None, "") else None
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_config(db: Session, *, row_id: int, current_user: User) -> None:
    require_reports_admin(current_user)
    row = db.get(ChartSeriesConfig, row_id)
    if row is None:
        raise NotFoundError("Configuración de serie no encontrada.")
    db.delete(row)
    db.commit()


def reorder_configs(
    db: Session, *, ordered_ids: list[int], current_user: User
) -> list[ChartSeriesConfig]:
    require_reports_admin(current_user)
    if not ordered_ids:
        return []
    first = db.get(ChartSeriesConfig, ordered_ids[0])
    if first is None:
        raise NotFoundError("Configuración de serie no encontrada.")
    rows_list = list_configs(db, tipo=first.tipo, agrupar_por=first.agrupar_por)
    rows = {r.id: r for r in rows_list if r.id in ordered_ids}
    for i, rid in enumerate(ordered_ids):
        r = rows.get(rid)
        if r:
            r.sort_index = i * 10
            db.add(r)
    db.commit()
    return list_configs(db, tipo=first.tipo, agrupar_por=first.agrupar_por)


def _global_configs_by_code(db: Session) -> dict[str, ChartSeriesConfig]:
    """Filas marcadas is_global: una entrada por series_code (primera por id)."""
    rows = db.scalars(
        select(ChartSeriesConfig)
        .where(ChartSeriesConfig.is_global.is_(True))
        .order_by(ChartSeriesConfig.id.asc())
    ).all()
    out: dict[str, ChartSeriesConfig] = {}
    for r in rows:
        if r.series_code not in out:
            out[r.series_code] = r
    return out


def apply_global_series_config(
    db: Session,
    *,
    tipo: str,
    agrupar_por: str,
    orden_color: Sequence[Any],
    color_dict: Mapping[Any, str],
    default_name: Callable[[Any], str],
) -> list[tuple[Any, str, str]]:
    """Filtra ocultas, reordena y devuelve [(code, color, display_name), ...].

    Resolución por ``series_code``: fila local (tipo+agrupación) gana sobre fila
    ``is_global`` del mismo código.
    """
    ap = agrupar_por.strip().upper()
    local_rows = list_configs(db, tipo=tipo.strip(), agrupar_por=ap)
    local_map: dict[str, ChartSeriesConfig] = {r.series_code: r for r in local_rows}
    global_map = _global_configs_by_code(db)

    def resolve(key: str) -> ChartSeriesConfig | None:
        if key in local_map:
            return local_map[key]
        return global_map.get(key)

    if not local_map and not global_map:
        return [
            (tech, str(color_dict.get(tech, "#999999")), default_name(tech))
            for tech in orden_color
        ]

    pending: list[tuple[int, int, Any, ChartSeriesConfig]] = []
    rest: list[Any] = []
    for orig_i, tech in enumerate(orden_color):
        key = str(tech)
        r = resolve(key)
        if r and r.hidden:
            continue
        if r:
            pending.append((r.sort_index, orig_i, tech, r))
        else:
            rest.append(tech)
    pending.sort(key=lambda x: (x[0], x[1]))
    new_order = [t for *_, t, __ in pending] + rest

    out: list[tuple[Any, str, str]] = []
    for tech in new_order:
        key = str(tech)
        r = resolve(key)
        col = str(color_dict.get(tech, "#999999"))
        if r and r.color:
            col = r.color
        name = r.display_name if r else default_name(tech)
        out.append((tech, col, name))
    return out


def delete_all_for_tipo(db: Session, *, tipo: str, agrupar_por: str) -> int:
    """Solo para tests o mantenimiento."""
    res = db.execute(
        delete(ChartSeriesConfig).where(
            ChartSeriesConfig.tipo == tipo.strip(),
            ChartSeriesConfig.agrupar_por == agrupar_por.strip().upper(),
        )
    )
    db.commit()
    return res.rowcount or 0
