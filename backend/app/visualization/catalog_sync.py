"""Sync idempotente del catálogo de visualización al arrancar el API.

Cada vez que el API levanta:

    1. Inserta en ``catalog_meta_color_palette`` los colores de los dicts
       hardcodeados (COLORES_GRUPOS / COLOR_MAP_PWR / COLORES_SECTOR /
       COLORES_EMISIONES / COLOR_BASE_FAMILIA) que **aún no estén en BD**.
    2. Inserta en ``catalog_meta_label`` etiquetas faltantes (DISPLAY_NAMES,
       NOMBRES_COMBUSTIBLES, TITULOS_VARIABLES_CAPACIDAD, MAPA_SECTOR).
    3. Inserta módulos / submódulos / chart_configs / sub-filtros de
       ``chart_menu.MENU`` que aún no existan.
    4. Siembra unidades estándar.

**No actualiza** filas existentes — preserva ediciones del curador hechas en
el admin UI. Si alguien agrega una gráfica nueva en código (``chart_menu.MENU``
+ ``configs.CONFIGS``), basta reiniciar el API para que aparezca en BD con
sus defaults.

Si la conexión a BD falla, el sync registra warning y continúa — la app
arranca igual y los charts caen al fallback hardcodeado del ``catalog_reader``.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    CatalogMetaChartConfig,
    CatalogMetaChartModule,
    CatalogMetaChartSubfilter,
    CatalogMetaChartSubmodule,
    CatalogMetaColorPalette,
    CatalogMetaLabel,
    CatalogMetaSectorMapping,
    CatalogMetaTechFamily,
    CatalogMetaVariableUnit,
    Emission,
    Fuel,
    OsemosysOutputParamValue,
    Technology,
)
from app.visualization import chart_menu
from app.visualization.colors import (
    COLOR_BASE_FAMILIA,
    COLOR_MAP_PWR,
    COLORES_EMISIONES,
    COLORES_GRUPOS,
    FAMILIAS_TEC,
)
from app.visualization.configs_legacy import NOMBRES_COMBUSTIBLES, TITULOS_VARIABLES_CAPACIDAD
from app.visualization.configs_comparacion import COLORES_SECTOR, MAPA_SECTOR
from app.visualization.labels import DISPLAY_NAMES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _bulk_insert_ignore(db: Session, model, rows: list[dict[str, Any]], unique_cols: list[str]) -> int:
    """``INSERT ... ON CONFLICT DO NOTHING`` (Postgres). Devuelve filas afectadas.

    No usa SQLite-friendly fallback: este sync sólo aplica en producción/staging
    sobre Postgres. En entornos SQLite (tests locales) la llamada se salta
    elegantemente al detectar el dialect.
    """
    if not rows:
        return 0
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect != "postgresql":
        # Fallback genérico: probar fila a fila e ignorar IntegrityError.
        from sqlalchemy.exc import IntegrityError
        added = 0
        for row in rows:
            try:
                db.execute(model.__table__.insert().values(**row))
                db.commit()
                added += 1
            except IntegrityError:
                db.rollback()
        return added

    pk_col = list(model.__table__.primary_key.columns)[0]
    stmt = (
        pg_insert(model)
        .values(rows)
        .on_conflict_do_nothing(index_elements=unique_cols)
        .returning(pk_col)
    )
    result = db.execute(stmt)
    inserted = len(result.fetchall())
    db.commit()
    return inserted


# ---------------------------------------------------------------------------
#  Color palette
# ---------------------------------------------------------------------------

def _sync_colors(db: Session) -> int:
    existing = {
        (g, k)
        for g, k in db.execute(
            select(CatalogMetaColorPalette.group, CatalogMetaColorPalette.key)
        ).all()
    }

    sources: list[tuple[str, dict[str, str]]] = [
        ("fuel", COLORES_GRUPOS),
        ("pwr", COLOR_MAP_PWR),
        ("sector", COLORES_SECTOR),
        ("emission", COLORES_EMISIONES),
        ("family", COLOR_BASE_FAMILIA),
    ]
    rows: list[dict[str, Any]] = []
    for group, src in sources:
        for i, (key, color) in enumerate(src.items()):
            if (group, key) in existing:
                continue
            rows.append({"group": group, "key": key, "color_hex": color, "sort_order": i})

    return _bulk_insert_ignore(db, CatalogMetaColorPalette, rows, ["group", "key"])


# ---------------------------------------------------------------------------
#  Labels
# ---------------------------------------------------------------------------

def _sync_labels(db: Session) -> int:
    existing = {
        c
        for (c,) in db.execute(select(CatalogMetaLabel.code)).all()
    }

    rows: list[dict[str, Any]] = []
    for i, (code, label) in enumerate(DISPLAY_NAMES.items()):
        if code in existing:
            continue
        rows.append({"code": code, "label_es": label, "category": "technology", "sort_order": i})

    for i, (code, label) in enumerate(NOMBRES_COMBUSTIBLES.items()):
        full = f"FUEL::{code}"
        if full in existing:
            continue
        rows.append({"code": full, "label_es": label, "category": "fuel", "sort_order": i})

    for i, (code, label) in enumerate(TITULOS_VARIABLES_CAPACIDAD.items()):
        full = f"VAR_CAP::{code}"
        if full in existing:
            continue
        rows.append({"code": full, "label_es": label, "category": "var_capacidad", "sort_order": i})

    for i, (pref, sector) in enumerate(MAPA_SECTOR.items()):
        if pref in existing:
            continue
        rows.append({"code": pref, "label_es": sector, "category": "sector", "sort_order": i})

    return _bulk_insert_ignore(db, CatalogMetaLabel, rows, ["code"])


# ---------------------------------------------------------------------------
#  Sector mapping (legacy) + tech families
# ---------------------------------------------------------------------------

def _sync_sectors(db: Session) -> int:
    existing = {
        p
        for (p,) in db.execute(select(CatalogMetaSectorMapping.tech_prefix)).all()
    }
    rows = [
        {"tech_prefix": p, "sector_name": s, "sort_order": i}
        for i, (p, s) in enumerate(MAPA_SECTOR.items())
        if p not in existing
    ]
    return _bulk_insert_ignore(db, CatalogMetaSectorMapping, rows, ["tech_prefix"])


def _sync_tech_families(db: Session) -> int:
    existing = {
        (f, p)
        for f, p in db.execute(
            select(CatalogMetaTechFamily.family_code, CatalogMetaTechFamily.tech_prefix)
        ).all()
    }
    rows: list[dict[str, Any]] = []
    for family, prefixes in FAMILIAS_TEC.items():
        for i, pref in enumerate(prefixes):
            if (family, pref) in existing:
                continue
            rows.append({"family_code": family, "tech_prefix": pref, "sort_order": i})
    return _bulk_insert_ignore(db, CatalogMetaTechFamily, rows, ["family_code", "tech_prefix"])


# ---------------------------------------------------------------------------
#  Chart hierarchy: modules → submodules → chart_configs → subfilters
# ---------------------------------------------------------------------------

def _sync_chart_hierarchy(db: Session) -> dict[str, int]:
    counts = {"modules": 0, "submodules": 0, "charts": 0, "subfilters": 0}

    # 1. Módulos
    existing_modules = {
        code: id_
        for code, id_ in db.execute(
            select(CatalogMetaChartModule.code, CatalogMetaChartModule.id)
        ).all()
    }
    new_modules = [
        {"code": m["code"], "label": m["label"], "icon": m.get("icon"), "sort_order": i}
        for i, m in enumerate(chart_menu.MENU)
        if m["code"] not in existing_modules
    ]
    counts["modules"] = _bulk_insert_ignore(db, CatalogMetaChartModule, new_modules, ["code"])

    # Recargar (incluye los recién insertados).
    module_id_by_code = {
        code: id_
        for code, id_ in db.execute(
            select(CatalogMetaChartModule.code, CatalogMetaChartModule.id)
        ).all()
    }

    # 2. Submódulos
    existing_subs = {
        (mod_id, code): sub_id
        for mod_id, code, sub_id in db.execute(
            select(
                CatalogMetaChartSubmodule.module_id,
                CatalogMetaChartSubmodule.code,
                CatalogMetaChartSubmodule.id,
            )
        ).all()
    }
    new_subs: list[dict[str, Any]] = []
    for m in chart_menu.MENU:
        if not m.get("subs"):
            continue
        mod_id = module_id_by_code.get(m["code"])
        if mod_id is None:
            continue
        for i, sub in enumerate(m["subs"]):
            if (mod_id, sub["code"]) in existing_subs:
                continue
            new_subs.append({
                "module_id": mod_id,
                "code": sub["code"],
                "label": sub["label"],
                "icon": None,
                "sort_order": i,
            })
    counts["submodules"] = _bulk_insert_ignore(db, CatalogMetaChartSubmodule, new_subs, ["module_id", "code"])

    submodule_id_by = {
        (mod_id, code): sub_id
        for mod_id, code, sub_id in db.execute(
            select(
                CatalogMetaChartSubmodule.module_id,
                CatalogMetaChartSubmodule.code,
                CatalogMetaChartSubmodule.id,
            )
        ).all()
    }

    # 3. Chart configs
    existing_charts = {
        tipo: chart_id
        for tipo, chart_id in db.execute(
            select(CatalogMetaChartConfig.tipo, CatalogMetaChartConfig.id)
        ).all()
    }
    new_charts: list[dict[str, Any]] = []
    chart_specs: list[tuple[str, dict[str, Any]]] = []
    sort_idx = 0
    for module, submodule, chart in chart_menu.iter_charts():
        sort_idx += 1
        if chart["tipo"] in existing_charts:
            continue
        mod_id = module_id_by_code.get(module["code"])
        if mod_id is None:
            continue
        sub_id = submodule_id_by.get((mod_id, submodule["code"])) if submodule else None
        new_charts.append({
            "tipo": chart["tipo"],
            "module_id": mod_id,
            "submodule_id": sub_id,
            "label_titulo": chart["label"],
            "variable_default": chart_menu.guess_variable_default(chart),
            "agrupar_por_default": chart.get("default_grouping", "TECNOLOGIA"),
            "agrupaciones_permitidas_json": chart.get("allowed"),
            "flags_json": chart_menu.chart_flags(chart),
            "is_visible": True,
            "sort_order": sort_idx,
        })
        chart_specs.append((chart["tipo"], chart))
    counts["charts"] = _bulk_insert_ignore(db, CatalogMetaChartConfig, new_charts, ["tipo"])

    # 4. Sub-filtros — siempre recalcular qué falta (incluye charts viejos sin
    #    sub-filtros sembrados aún).
    chart_id_by_tipo = {
        tipo: cid
        for tipo, cid in db.execute(
            select(CatalogMetaChartConfig.tipo, CatalogMetaChartConfig.id)
        ).all()
    }
    existing_sf = {
        (cid, code)
        for cid, code in db.execute(
            select(CatalogMetaChartSubfilter.chart_id, CatalogMetaChartSubfilter.code)
        ).all()
    }
    sf_rows: list[dict[str, Any]] = []
    for module, submodule, chart in chart_menu.iter_charts():
        cid = chart_id_by_tipo.get(chart["tipo"])
        if cid is None:
            continue
        for i, code in enumerate(chart.get("sub_filtros") or []):
            if (cid, code) in existing_sf:
                continue
            sf_rows.append({
                "chart_id": cid,
                "group_label": chart.get("sub_label"),
                "code": code,
                "display_label": None,
                "sort_order": i,
                "default_selected": False,
            })
    counts["subfilters"] = _bulk_insert_ignore(db, CatalogMetaChartSubfilter, sf_rows, ["chart_id", "code"])
    return counts


# ---------------------------------------------------------------------------
#  Dynamic labels — extrae tecnologías / combustibles / emisiones de los
#  catálogos de entrada y de los resultados ya producidos por simulaciones
#  hechas en otras ramas.
# ---------------------------------------------------------------------------

def _sync_dynamic_labels(db: Session) -> int:
    """Para cada code presente en BD (catálogos de entrada y resultados de
    simulaciones) que no tenga label en ``catalog_meta_label``, inserta un
    label heurístico vía ``_dynamic_label``.

    Cubre:
        1. ``technology.name``, ``fuel.name``, ``emission.name`` — entradas
           usadas por escenarios de cualquier rama.
        2. ``osemosys_output_param_value.{technology,fuel,emission}_name`` —
           resultados de jobs que ya corrieron.

    Idempotente: sólo INSERTA codes faltantes.
    """
    try:
        from app.visualization.labels import _dynamic_label  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo importar _dynamic_label: %s — salta dynamic seed.", exc)
        return 0

    existing = {
        c
        for (c,) in db.execute(select(CatalogMetaLabel.code)).all()
    }

    sources: list[tuple[str, set[str]]] = []

    # 1) Catálogos de entrada (cubren techs/fuels/emissions de TODOS los
    #    escenarios, incluso los creados en otras ramas que aún no han corrido).
    sources.append(("technology", {n for (n,) in db.execute(select(Technology.name)).all() if n}))
    sources.append(("fuel",       {n for (n,) in db.execute(select(Fuel.name)).all() if n}))
    sources.append(("emission",   {n for (n,) in db.execute(select(Emission.name)).all() if n}))

    # 2) Resultados ya generados (por si algún tech/fuel sólo aparece a través
    #    de variables intermedias y no en el catálogo de entrada).
    for col, category in (
        (OsemosysOutputParamValue.technology_name, "technology"),
        (OsemosysOutputParamValue.fuel_name, "fuel"),
        (OsemosysOutputParamValue.emission_name, "emission"),
    ):
        rows = db.execute(select(col).where(col.is_not(None)).distinct()).all()
        codes = {r[0] for r in rows if r[0]}
        sources.append((category, codes))

    # Combinar — preservando la primera categoría con la que apareció cada code.
    new_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for category, codes in sources:
        for code in sorted(codes):
            if code in existing or code in seen:
                continue
            new_rows.append({
                "code": code,
                "label_es": _dynamic_label(code),
                "category": category,
                "sort_order": 0,
            })
            seen.add(code)

    return _bulk_insert_ignore(db, CatalogMetaLabel, new_rows, ["code"])


# ---------------------------------------------------------------------------
#  Variable units
# ---------------------------------------------------------------------------

def _sync_variable_units(db: Session) -> int:
    existing = {
        v
        for (v,) in db.execute(select(CatalogMetaVariableUnit.variable_name)).all()
    }
    defaults = [
        {
            "variable_name": "__DEFAULT_ENERGY__",
            "unit_base": "PJ",
            "display_units_json": [
                {"code": "PJ",  "label": "PJ",  "factor": 1.0},
                {"code": "GW",  "label": "GW",  "factor": 1.0 / 31.536},
                {"code": "MW",  "label": "MW",  "factor": 1.0 / 0.031536},
                {"code": "TWh", "label": "TWh", "factor": 1.0 / 3.6},
                {"code": "Gpc", "label": "Gpc", "factor": 1.0 / 1.0095581216},
                {"code": "kton", "label": "kton", "factor": None},
            ],
        },
        {
            "variable_name": "__DEFAULT_EMISSION__",
            "unit_base": "MtCO2eq",
            "display_units_json": [
                {"code": "MtCO2eq", "label": "MtCO₂eq", "factor": 1.0},
                {"code": "ktCO2eq", "label": "ktCO₂eq", "factor": 1000.0},
            ],
        },
    ]
    rows = [r for r in defaults if r["variable_name"] not in existing]
    return _bulk_insert_ignore(db, CatalogMetaVariableUnit, rows, ["variable_name"])


# ---------------------------------------------------------------------------
#  Public entrypoint
# ---------------------------------------------------------------------------

def sync_catalog(db: Session | None = None) -> dict[str, int]:
    """Ejecuta el sync completo. Devuelve dict con conteos por sección."""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    assert db is not None  # noqa: S101 — for type narrowing

    summary: dict[str, int] = {}
    try:
        summary["colors"] = _sync_colors(db)
        summary["labels"] = _sync_labels(db)
        summary["sectors"] = _sync_sectors(db)
        summary["tech_families"] = _sync_tech_families(db)
        chart_counts = _sync_chart_hierarchy(db)
        summary.update(chart_counts)
        summary["variable_units"] = _sync_variable_units(db)
        summary["dynamic_labels"] = _sync_dynamic_labels(db)
    finally:
        if own_session:
            db.close()
    return summary


def sync_catalog_safely() -> None:
    """Wrapper para invocar desde startup: nunca lanza, sólo loggea.

    Si Postgres no está disponible o las tablas no existen aún (p.ej. en
    tests SQLite o antes de correr migraciones), registra warning y retorna.
    """
    try:
        summary = sync_catalog()
    except SQLAlchemyError as exc:
        logger.warning(
            "sync_catalog: error de BD — se omite el sync. "
            "Detalle: %s. La app arranca igual; corre `alembic upgrade head` "
            "para crear/poblar las tablas catalog_meta_*.",
            exc,
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_catalog: error inesperado: %s", exc)
        return

    nonzero = {k: v for k, v in summary.items() if v}
    if nonzero:
        logger.info("sync_catalog: agregadas filas — %s", nonzero)
    else:
        logger.info("sync_catalog: BD ya sincronizada (sin cambios).")
