"""CRUD de plantillas de gráficas por usuario y generación de reportes (ZIP).

El reporte renderiza cada plantilla usando los mismos helpers que usa la
API de exportación individual/facetas (``chart_service.render_chart_visualization_bytes``
y ``chart_service.render_comparison_facet_figure_bytes``), luego comprime
todas las imágenes en un ZIP.
"""

from __future__ import annotations

import io
import logging
import re
import uuid
import zipfile
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models import (
    ReportTemplate,
    ReportTemplateFavorite,
    SavedChartTemplate,
    SavedChartTemplateFavorite,
    User,
)
from app.schemas.saved_chart_template import (
    ReportCategoryExport,
    ReportTemplateItem,
)
from app.schemas.visualization import ChartDataResponse, ChartSeries
from app.services.simulation_service import SimulationService
from app.visualization import chart_service


logger = logging.getLogger(__name__)

_LINE_VIEW_MODES: frozenset[str] = frozenset({"line", "area"})


def _inject_synthetic_series(chart: ChartDataResponse, raw_series: list[dict]) -> None:
    """Agrega las series manuales activas del template a las series del chart.

    Convierte cada serie (pares [año, valor]) a ChartSeries alineada a las
    categorías del chart. Años sin dato quedan como NaN (gap en línea).

    Conserva el styling configurado por el usuario (``lineStyle``,
    ``markerSymbol``, ``markerRadius``, ``lineWidth``) y marca la serie con
    ``is_synthetic=True`` para que el renderer matplotlib pueda aplicarlo.
    """
    for synth in raw_series:
        if synth.get("active", True) is False:
            continue
        data_map: dict[int, float] = {}
        for point in (synth.get("data") or []):
            try:
                year, val = int(point[0]), float(point[1])
                data_map[year] = val
            except (TypeError, ValueError, IndexError):
                logger.debug("Serie sintética '%s': punto inválido %r, omitido", synth.get("name"), point)
                continue
        # ``None`` (no NaN) → serializa a ``null`` en JSON, lo que crea un
        # gap en líneas y "no hay barra/área" en columnas/áreas.
        aligned: list[float | None] = []
        for cat in chart.categories:
            try:
                year = int(str(cat))
            except (TypeError, ValueError):
                aligned.append(None)
                continue
            aligned.append(data_map.get(year))
        chart.series.append(
            ChartSeries(
                name=synth.get("name") or "Serie manual",
                data=aligned,
                color=synth.get("color") or "#999999",
                stack=None,
                is_synthetic=True,
                lineStyle=synth.get("lineStyle"),
                markerSymbol=synth.get("markerSymbol"),
                markerRadius=(
                    float(synth["markerRadius"])
                    if synth.get("markerRadius") is not None
                    else None
                ),
                lineWidth=(
                    float(synth["lineWidth"])
                    if synth.get("lineWidth") is not None
                    else None
                ),
            )
        )


def _slugify(text: str, max_len: int = 80) -> str:
    clean = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in (text or ""))
    clean = re.sub(r"\s+", "_", clean).strip("_")
    return (clean or "grafica")[:max_len]


def _chart_to_public_dict(
    obj: SavedChartTemplate,
    *,
    current_user_id: uuid.UUID,
    owner_username: str | None,
    is_favorite: bool = False,
) -> dict:
    """Convierte ORM → dict para ``SavedChartTemplatePublic``, con is_owner."""
    return {
        "id": obj.id,
        "name": obj.name,
        "description": obj.description,
        "tipo": obj.tipo,
        "un": obj.un,
        "sub_filtro": obj.sub_filtro,
        "loc": obj.loc,
        "variable": obj.variable,
        "agrupar_por": obj.agrupar_por,
        "view_mode": obj.view_mode,
        "compare_mode": obj.compare_mode,
        "bar_orientation": obj.bar_orientation,
        "facet_placement": obj.facet_placement,
        "facet_legend_mode": obj.facet_legend_mode,
        "num_scenarios": obj.num_scenarios,
        "legend_title": obj.legend_title,
        "filename_mode": obj.filename_mode,
        "report_title": obj.report_title,
        "years_to_plot": obj.years_to_plot,
        "synthetic_series": obj.synthetic_series,
        "table_period_years": getattr(obj, "table_period_years", None),
        "table_cumulative": getattr(obj, "table_cumulative", None),
        "custom_series_order": getattr(obj, "custom_series_order", None),
        "y_axis_min": getattr(obj, "y_axis_min", None),
        "y_axis_max": getattr(obj, "y_axis_max", None),
        "created_at": obj.created_at,
        "is_public": bool(getattr(obj, "is_public", False)),
        "owner_username": owner_username,
        "is_owner": obj.user_id == current_user_id,
        "is_favorite": bool(is_favorite),
    }


def _load_chart_favorite_ids(
    db: Session, *, user_id: uuid.UUID
) -> set[int]:
    rows = db.execute(
        select(SavedChartTemplateFavorite.template_id).where(
            SavedChartTemplateFavorite.user_id == user_id,
        )
    ).scalars().all()
    return {int(r) for r in rows}


def _load_report_favorite_ids(
    db: Session, *, user_id: uuid.UUID
) -> set[int]:
    rows = db.execute(
        select(ReportTemplateFavorite.report_id).where(
            ReportTemplateFavorite.user_id == user_id,
        )
    ).scalars().all()
    return {int(r) for r in rows}


class SavedChartTemplateService:
    # ---------------- CRUD ----------------

    @staticmethod
    def list_accessible(
        db: Session,
        *,
        user_id: uuid.UUID,
        current_user: User | None = None,
    ) -> list[dict]:
        """Propias + públicas de otros usuarios; anota is_owner/owner/is_favorite.

        Admin Reportes ve además todas las plantillas privadas ajenas (read-only),
        para poder abrir/editar reportes que las referencian.

        Orden: **favoritos primero**, luego propios, luego por fecha desc.
        """
        fav_ids = _load_chart_favorite_ids(db, user_id=user_id)
        is_admin_reports = bool(
            current_user is not None
            and (
                getattr(current_user, "is_admin_reports", False)
                or getattr(current_user, "can_manage_scenarios", False)
            )
        )
        visibility_filter = (
            None
            if is_admin_reports
            else or_(
                SavedChartTemplate.user_id == user_id,
                SavedChartTemplate.is_public.is_(True),
            )
        )
        stmt = (
            select(SavedChartTemplate, User.username)
            .join(User, User.id == SavedChartTemplate.user_id)
            .order_by(
                (SavedChartTemplate.user_id == user_id).desc(),
                SavedChartTemplate.created_at.desc(),
            )
        )
        if visibility_filter is not None:
            stmt = stmt.where(visibility_filter)
        rows = db.execute(stmt).all()
        out = [
            _chart_to_public_dict(
                obj,
                current_user_id=user_id,
                owner_username=username,
                is_favorite=int(obj.id) in fav_ids,
            )
            for obj, username in rows
        ]
        # Favoritos al tope manteniendo el orden relativo (stable sort).
        out.sort(key=lambda d: 0 if d.get("is_favorite") else 1)
        return out

    @staticmethod
    def get_accessible(
        db: Session,
        *,
        user_id: uuid.UUID,
        template_id: int,
        current_user: User | None = None,
    ) -> tuple[SavedChartTemplate, str | None]:
        """Devuelve (obj, owner_username) si el usuario la puede ver.

        Reglas:
          - dueño o plantilla pública → accesible;
          - Admin Reportes (``is_admin_reports`` o ``can_manage_scenarios``) →
            accede también a privadas ajenas (solo lectura — mutaciones siguen
            restringidas en ``update``/``delete``).
        """
        row = db.execute(
            select(SavedChartTemplate, User.username)
            .join(User, User.id == SavedChartTemplate.user_id)
            .where(SavedChartTemplate.id == template_id)
        ).one_or_none()
        if row is None:
            raise NotFoundError("Plantilla de gráfica no encontrada.")
        obj, username = row
        if obj.user_id != user_id and not bool(getattr(obj, "is_public", False)):
            is_admin_reports = bool(
                current_user is not None
                and (
                    getattr(current_user, "is_admin_reports", False)
                    or getattr(current_user, "can_manage_scenarios", False)
                )
            )
            if not is_admin_reports:
                raise NotFoundError("Plantilla de gráfica no encontrada.")
        return obj, username

    @staticmethod
    def get_for_user(
        db: Session, *, user_id: uuid.UUID, template_id: int
    ) -> SavedChartTemplate:
        """Dueño exclusivamente (para mutaciones)."""
        obj = db.get(SavedChartTemplate, template_id)
        if obj is None or obj.user_id != user_id:
            raise NotFoundError("Plantilla de gráfica no encontrada.")
        return obj

    @staticmethod
    def _resolve_owner_username(
        db: Session, *, user_id: uuid.UUID
    ) -> str | None:
        return db.scalar(select(User.username).where(User.id == user_id))

    @staticmethod
    def create(
        db: Session,
        *,
        user_id: uuid.UUID,
        payload: dict,
    ) -> dict:
        obj = SavedChartTemplate(user_id=user_id, **payload)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        username = SavedChartTemplateService._resolve_owner_username(
            db, user_id=user_id
        )
        return _chart_to_public_dict(
            obj,
            current_user_id=user_id,
            owner_username=username,
            is_favorite=False,
        )

    @staticmethod
    def update(
        db: Session,
        *,
        current_user: User,
        template_id: int,
        data: dict,
    ) -> dict:
        """Actualiza una plantilla.

        Reglas:
          - El dueño puede cambiar todos los campos.
          - Admin Reportes (``is_admin_reports`` o ``can_manage_scenarios``) puede
            cambiar únicamente ``report_title`` sobre plantillas accesibles
            (propias, públicas, o que él tenga visibilidad).
        """
        user_id = current_user.id
        # Carga con semántica "accesible" para permitir admin_reports sobre no-propias.
        row = db.execute(
            select(SavedChartTemplate, User.username)
            .join(User, User.id == SavedChartTemplate.user_id)
            .where(SavedChartTemplate.id == template_id)
        ).one_or_none()
        if row is None:
            raise NotFoundError("Plantilla de gráfica no encontrada.")
        obj, username = row
        is_owner = obj.user_id == user_id
        is_admin_reports = bool(
            getattr(current_user, "is_admin_reports", False)
            or getattr(current_user, "can_manage_scenarios", False)
        )
        is_public_template = bool(getattr(obj, "is_public", False))

        if not is_owner and not (is_admin_reports and is_public_template):
            raise NotFoundError("Plantilla de gráfica no encontrada.")

        touches_general = any(
            k in data for k in ("name", "description", "is_public")
        )
        if touches_general and not is_owner:
            raise ForbiddenError(
                "Solo el dueño puede cambiar nombre, descripción o visibilidad."
            )

        if "name" in data and data["name"] is not None:
            obj.name = str(data["name"]).strip()
        if "description" in data:
            obj.description = data["description"]
        if "is_public" in data and data["is_public"] is not None:
            obj.is_public = bool(data["is_public"])
        if "report_title" in data:
            raw = data["report_title"]
            cleaned = (raw or "").strip() if isinstance(raw, str) else None
            obj.report_title = cleaned if cleaned else None
        if "view_mode" in data and data["view_mode"] in (
            "column", "line", "area", "pareto", "table",
        ):
            obj.view_mode = data["view_mode"]
        if "table_period_years" in data:
            v = data["table_period_years"]
            obj.table_period_years = int(v) if v is not None else None  # type: ignore[assignment]
        if "table_cumulative" in data:
            v = data["table_cumulative"]
            obj.table_cumulative = bool(v) if v is not None else None  # type: ignore[assignment]
        if "custom_series_order" in data:
            v = data["custom_series_order"]
            obj.custom_series_order = (
                list(v) if isinstance(v, list) and v else None
            )  # type: ignore[assignment]
        if "y_axis_min" in data:
            v = data["y_axis_min"]
            obj.y_axis_min = float(v) if v is not None else None  # type: ignore[assignment]
        if "y_axis_max" in data:
            v = data["y_axis_max"]
            obj.y_axis_max = float(v) if v is not None else None  # type: ignore[assignment]
        db.commit()
        db.refresh(obj)
        username = SavedChartTemplateService._resolve_owner_username(
            db, user_id=obj.user_id
        )
        fav = db.execute(
            select(SavedChartTemplateFavorite).where(
                SavedChartTemplateFavorite.user_id == user_id,
                SavedChartTemplateFavorite.template_id == template_id,
            )
        ).scalar_one_or_none()
        return _chart_to_public_dict(
            obj,
            current_user_id=user_id,
            owner_username=username,
            is_favorite=fav is not None,
        )

    @staticmethod
    def delete(db: Session, *, user_id: uuid.UUID, template_id: int) -> None:
        obj = SavedChartTemplateService.get_for_user(
            db, user_id=user_id, template_id=template_id
        )
        db.delete(obj)
        db.commit()

    # ---------------- Favoritos ----------------

    @staticmethod
    def set_favorite(
        db: Session,
        *,
        user_id: uuid.UUID,
        template_id: int,
        is_favorite: bool,
    ) -> dict:
        # Verifica accesibilidad (propia o pública).
        obj, username = SavedChartTemplateService.get_accessible(
            db, user_id=user_id, template_id=template_id
        )
        existing = db.execute(
            select(SavedChartTemplateFavorite).where(
                SavedChartTemplateFavorite.user_id == user_id,
                SavedChartTemplateFavorite.template_id == template_id,
            )
        ).scalar_one_or_none()
        if is_favorite and existing is None:
            db.add(
                SavedChartTemplateFavorite(
                    user_id=user_id, template_id=template_id,
                )
            )
            db.commit()
        elif not is_favorite and existing is not None:
            db.delete(existing)
            db.commit()
        return _chart_to_public_dict(
            obj,
            current_user_id=user_id,
            owner_username=username,
            is_favorite=bool(is_favorite),
        )

    # ---------------- Report generation ----------------

    @staticmethod
    def _render_template(
        db: Session,
        *,
        template: SavedChartTemplate,
        job_ids: list[int],
        fmt: str,
        job_display_overrides: dict[int, str] | None = None,
        scenario_alias_for_title: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> tuple[bytes, str]:
        """Renderiza una plantilla y devuelve (bytes, extensión-sin-punto).

        Si ``year_from`` o ``year_to`` están dados, las categorías-año (y los
        valores de cada serie) se recortan al rango antes de renderizar.

        Aplica los modificadores persistidos del template:
          - ``custom_series_order``: reordena las series antes del render.
          - ``y_axis_min`` / ``y_axis_max``: override del rango Y al renderer.
        """
        # Modificadores persistidos en la plantilla.
        custom_order: list[str] | None = list(
            getattr(template, "custom_series_order", None) or []
        ) or None
        y_min = getattr(template, "y_axis_min", None)
        y_max = getattr(template, "y_axis_max", None)
        # Líneas totales multi-escenario: una línea por escenario sobre el mismo eje.
        if template.compare_mode == "line-total":
            if len(job_ids) < 2:
                raise ValueError(
                    f"La plantilla '{template.name}' requiere al menos 2 escenarios."
                )
            chart = chart_service.build_comparison_line_data(
                db=db,
                job_ids=job_ids,
                tipo=template.tipo,
                un=template.un,
                sub_filtro=template.sub_filtro,
                loc=template.loc,
                job_display_overrides=job_display_overrides,
            )
            if not chart.series:
                raise ValueError(
                    f"Plantilla '{template.name}': sin datos para líneas totales."
                )
            chart_service.filter_chart_by_year_range(chart, year_from, year_to)
            chart_service.reorder_chart_series(chart, custom_order)
            if template.synthetic_series:
                _inject_synthetic_series(chart, template.synthetic_series)
            rt = (getattr(template, "report_title", None) or "").strip()
            if rt:
                chart.title = rt
            sx = (scenario_alias_for_title or "").strip()
            if sx:
                chart.title = f"{chart.title} — {sx}"
            img_bytes = chart_service.render_chart_visualization_bytes(
                chart, fmt=fmt, view_mode="line",
                y_axis_min=y_min, y_axis_max=y_max,
            )
            return img_bytes, fmt

        # Comparación por año (subplots por año): usa renderer dedicado.
        if template.compare_mode == "by-year":
            if len(job_ids) < 2:
                raise ValueError(
                    f"La plantilla '{template.name}' requiere al menos 2 escenarios."
                )
            years = list(template.years_to_plot or [])
            # Recortar la lista de años explícita al rango, si aplica.
            if year_from is not None or year_to is not None:
                years = [
                    y for y in years
                    if (year_from is None or y >= year_from)
                    and (year_to is None or y <= year_to)
                ]
                if not years:
                    raise ValueError(
                        f"Plantilla '{template.name}': el rango de años "
                        f"[{year_from}, {year_to}] no incluye ninguno de "
                        f"los años de la plantilla."
                    )
            cmp_data = chart_service.build_comparison_data(
                db=db,
                job_ids=job_ids,
                tipo=template.tipo,
                un=template.un,
                years_to_plot=years or None,
                agrupacion=template.agrupar_por,
                sub_filtro=template.sub_filtro,
                loc=template.loc,
                job_display_overrides=job_display_overrides,
            )
            if not cmp_data.subplots or not any(
                s.series for s in cmp_data.subplots
            ):
                raise ValueError(
                    f"Plantilla '{template.name}': sin datos para comparación por año."
                )
            # Reordenar series dentro de cada subplot.
            if custom_order:
                for sp in cmp_data.subplots:
                    chart_service.reorder_chart_series(sp, custom_order)
            rt = (getattr(template, "report_title", None) or "").strip()
            if rt:
                cmp_data.title = rt
            sx = (scenario_alias_for_title or "").strip()
            if sx:
                cmp_data.title = f"{cmp_data.title} — {sx}"
            img_bytes = chart_service.render_comparison_by_year_bytes(
                cmp_data, fmt=fmt,
                y_axis_min=y_min, y_axis_max=y_max,
            )
            return img_bytes, fmt

        if template.compare_mode == "facet":
            if len(job_ids) < 2:
                raise ValueError(
                    f"La plantilla '{template.name}' requiere al menos 2 escenarios."
                )
            facet_payload = chart_service.build_comparison_facet_data(
                db=db,
                job_ids=job_ids,
                tipo=template.tipo,
                un=template.un,
                sub_filtro=template.sub_filtro,
                loc=template.loc,
                variable=template.variable,
                agrupar_por=template.agrupar_por,
                job_display_overrides=job_display_overrides,
            )
            if not facet_payload.facets or not any(f.series for f in facet_payload.facets):
                raise ValueError(
                    f"Plantilla '{template.name}': sin datos con los filtros y escenarios seleccionados."
                )
            chart_service.filter_chart_by_year_range(facet_payload, year_from, year_to)
            # Reordenar series dentro de cada facet.
            if custom_order:
                for f in facet_payload.facets:
                    chart_service.reorder_chart_series(f, custom_order)
            rt = (getattr(template, "report_title", None) or "").strip()
            if rt:
                facet_payload.title = rt
            sx = (scenario_alias_for_title or "").strip()
            if sx:
                facet_payload.title = f"{facet_payload.title} — {sx}"
            img_bytes = chart_service.render_comparison_facet_figure_bytes(
                facet_payload,
                fmt=fmt,
                legend_title=template.legend_title,
                y_axis_min=y_min,
                y_axis_max=y_max,
                series_order=custom_order,
            )
            return img_bytes, fmt

        # compare_mode == 'off' → single chart
        if len(job_ids) < 1:
            raise ValueError(
                f"La plantilla '{template.name}' requiere un escenario."
            )

        if (template.view_mode or "").lower() == "pareto":
            pareto = chart_service.build_pareto_data(
                db=db,
                job_id=job_ids[0],
                tipo=template.tipo,
                un=template.un,
                sub_filtro=template.sub_filtro,
                loc=template.loc,
            )
            if not pareto.values:
                raise ValueError(
                    f"Plantilla '{template.name}': sin datos para Pareto."
                )
            rt = (getattr(template, "report_title", None) or "").strip()
            if rt:
                pareto.title = rt
            sx = (scenario_alias_for_title or "").strip()
            if sx:
                pareto.title = f"{pareto.title} — {sx}"
            img_bytes = chart_service.render_pareto_chart_bytes(pareto, fmt=fmt)
            return img_bytes, fmt

        chart = chart_service.build_chart_data(
            db=db,
            job_id=job_ids[0],
            tipo=template.tipo,
            un=template.un,
            sub_filtro=template.sub_filtro,
            loc=template.loc,
            variable=template.variable,
            agrupar_por=template.agrupar_por,
        )
        if not chart.series:
            raise ValueError(
                f"Plantilla '{template.name}': sin datos con los filtros y escenario seleccionados."
            )
        view_mode = template.view_mode or "column"
        # ── Modo tabla: acumular ANTES de filtrar/recortar (para que el
        # valor en cada año represente la suma desde el inicio del horizonte).
        if view_mode == "table" and bool(getattr(template, "table_cumulative", False)):
            chart_service.apply_cumulative_series(chart)
        chart_service.filter_chart_by_year_range(chart, year_from, year_to)
        if view_mode == "table":
            tpy = getattr(template, "table_period_years", None)
            if tpy and tpy >= 2:
                chart_service.apply_period_years(chart, int(tpy))
        # Reordenar series del chart single (column/line/area).
        chart_service.reorder_chart_series(chart, custom_order)
        if template.synthetic_series and view_mode in _LINE_VIEW_MODES:
            _inject_synthetic_series(chart, template.synthetic_series)
        rt = (getattr(template, "report_title", None) or "").strip()
        if rt:
            chart.title = rt
        sx = (scenario_alias_for_title or "").strip()
        if sx:
            chart.title = f"{chart.title} — {sx}"
        img_bytes = chart_service.render_chart_visualization_bytes(
            chart,
            fmt=fmt,
            view_mode=view_mode,
            y_axis_min=y_min,
            y_axis_max=y_max,
        )
        return img_bytes, fmt

    @staticmethod
    def _validate_access_jobs(
        db: Session,
        *,
        current_user: User,
        job_ids: list[int],
    ) -> None:
        for jid in job_ids:
            try:
                job = SimulationService.get_by_id(
                    db, current_user=current_user, job_id=jid
                )
            except NotFoundError as e:
                raise ForbiddenError(f"Job {jid} no encontrado o sin acceso.") from e
            if job["status"] != "SUCCEEDED":
                raise ValueError(f"Job {jid} no está en estado SUCCEEDED.")

    @staticmethod
    def _collect_items_from_categories(
        categories: list[ReportCategoryExport],
    ) -> list[ReportTemplateItem]:
        """Aplana el árbol de categorías a la lista de items (para validación)."""
        out: list[ReportTemplateItem] = []
        for cat in categories:
            out.extend(cat.items)
            for sub in cat.subcategories:
                out.extend(sub.items)
        return out

    @staticmethod
    def generate_report_zip(
        db: Session,
        *,
        current_user: User,
        items: list[ReportTemplateItem],
        fmt: str,
        organize_by_category: bool = False,
        categories: list[ReportCategoryExport] | None = None,
        job_display_overrides: dict[str, str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> tuple[io.BytesIO, str]:
        """Construye un ZIP con una imagen por plantilla.

        Dos modos:
          * Plano (default): itera ``items`` en orden, ``01_nombre.ext``, ...
          * Estructurado (``organize_by_category=True``): usa ``categories`` y
            genera rutas ``01_Categoria/[01_Sub/]01_nombre.ext``.
        """
        if fmt not in ("png", "svg"):
            raise ValueError("fmt debe ser 'png' o 'svg'")

        # Validar rango de años (si ambos están dados, year_from <= year_to).
        if year_from is not None and year_to is not None and year_from > year_to:
            raise ValueError(
                f"Rango de años inválido: year_from ({year_from}) > "
                f"year_to ({year_to})."
            )

        structured = organize_by_category and bool(categories)
        if structured:
            effective_items = SavedChartTemplateService._collect_items_from_categories(
                categories or []
            )
        else:
            effective_items = list(items)

        if not effective_items:
            raise ValueError("El reporte debe tener al menos una gráfica.")

        # Normalizar overrides: JSON trae claves como str; convertimos a int y
        # descartamos valores vacíos (para que caiga al display_name real).
        overrides_int: dict[int, str] | None = None
        if job_display_overrides:
            tmp: dict[int, str] = {}
            for k, v in job_display_overrides.items():
                try:
                    key = int(k)
                except (TypeError, ValueError):
                    continue
                clean = (v or "").strip()
                if clean:
                    tmp[key] = clean
            overrides_int = tmp or None

        # Validar todas las plantillas (incluyendo públicas) y accesos antes de renderizar.
        # Pasamos ``current_user`` para que la rama de Admin Reportes/Admin
        # Escenarios active el escape hatch y pueda exportar reportes que
        # referencien plantillas privadas ajenas.
        #
        # NOTA: este cache solo guarda el OBJETO ORM por ``template_id``, no
        # los ``job_ids`` ni el alias. Esos son **por-item**: dos items con
        # el mismo ``template_id`` pueden tener ``job_ids``/aliases distintos
        # (caso típico: misma gráfica para 2 escenarios). En las loops de
        # escritura recuperamos los valores desde cada ``item`` directamente.
        templates_by_id: dict[int, SavedChartTemplate] = {}
        all_jobs: set[int] = set()
        missing_ids: list[int] = []
        for item in effective_items:
            if item.template_id not in templates_by_id:
                try:
                    template, _owner = SavedChartTemplateService.get_accessible(
                        db,
                        user_id=current_user.id,
                        template_id=item.template_id,
                        current_user=current_user,
                    )
                except NotFoundError:
                    missing_ids.append(item.template_id)
                    continue
                templates_by_id[item.template_id] = template
            else:
                template = templates_by_id[item.template_id]
            if len(item.job_ids) != template.num_scenarios:
                raise ValueError(
                    f"Plantilla '{template.name}' requiere {template.num_scenarios} escenario(s); "
                    f"recibidos {len(item.job_ids)}."
                )
            all_jobs.update(item.job_ids)

        if missing_ids:
            unique_missing = sorted(set(missing_ids))
            raise NotFoundError(
                "No se pudieron cargar las siguientes plantillas (eliminadas, "
                f"privadas o sin acceso): {unique_missing}. "
                "Edita el reporte para reemplazarlas o pide al dueño que las "
                "vuelva a hacer públicas."
            )

        # Helper para obtener (template, job_ids, alias) por item — siempre
        # mira el item, no un cache compartido.
        def _resolve_item(it: ReportTemplateItem) -> tuple[SavedChartTemplate, list[int], str | None]:
            tpl = templates_by_id[it.template_id]
            jobs = list(it.job_ids)
            alias = (getattr(it, "scenario_alias_for_title", None) or "").strip() or None
            return tpl, jobs, alias

        SavedChartTemplateService._validate_access_jobs(
            db, current_user=current_user, job_ids=sorted(all_jobs)
        )

        buffer = io.BytesIO()
        used_names: dict[str, int] = {}
        manifest_lines: list[str] = [
            "Reporte generado con OSeMOSYS UPME",
            f"Usuario: {current_user.username}",
            f"Fecha: {datetime.now(timezone.utc).isoformat()}",
            f"Formato: {fmt}",
            f"Estructura: {'carpetas por categoría' if structured else 'plana'}",
            f"Plantillas únicas: {len(templates_by_id)} ({len(effective_items)} items)",
            "",
        ]

        def _write_one(
            zf: zipfile.ZipFile,
            *,
            idx: int,
            template: SavedChartTemplate,
            job_ids: list[int],
            scenario_alias: str | None,
            folder: str,
            depth_prefix: str,
        ) -> str | None:
            """Renderiza y escribe una imagen; devuelve el arcname o None si fue omitida."""
            try:
                img_bytes, ext = SavedChartTemplateService._render_template(
                    db,
                    template=template,
                    job_ids=job_ids,
                    fmt=fmt,
                    job_display_overrides=overrides_int,
                    scenario_alias_for_title=scenario_alias,
                    year_from=year_from,
                    year_to=year_to,
                )
            except ValueError as e:
                logger.warning("Skip plantilla %s durante reporte: %s", template.id, e)
                manifest_lines.append(
                    f"{depth_prefix}{idx:02d}. [OMITIDA] {template.name} — {e}"
                )
                return None

            base = _slugify(template.name)
            dedup_key = f"{folder}/{base}" if folder else base
            count = used_names.get(dedup_key, 0) + 1
            used_names[dedup_key] = count
            suffix = f"_{count}" if count > 1 else ""
            filename = f"{idx:02d}_{base}{suffix}.{ext}"
            arcname = f"{folder}/{filename}" if folder else filename
            zf.writestr(arcname, img_bytes)
            manifest_lines.append(
                f"{depth_prefix}{idx:02d}. {template.name}  →  {arcname}  "
                f"(tipo={template.tipo}, un={template.un}, "
                f"jobs={','.join(str(j) for j in job_ids)})"
            )
            return arcname

        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            if structured:
                assert categories is not None
                for c_idx, cat in enumerate(categories, start=1):
                    cat_slug = _slugify(cat.label)
                    cat_folder = f"{c_idx:02d}_{cat_slug}"
                    manifest_lines.append(f"[{c_idx:02d}] {cat.label}/")
                    # Ítems directos de la categoría
                    for i_idx, item in enumerate(cat.items, start=1):
                        tpl, jobs, alias = _resolve_item(item)
                        _write_one(
                            zf,
                            idx=i_idx,
                            template=tpl,
                            job_ids=jobs,
                            scenario_alias=alias,
                            folder=cat_folder,
                            depth_prefix="  ",
                        )
                    # Subcategorías
                    for s_idx, sub in enumerate(cat.subcategories, start=1):
                        sub_slug = _slugify(sub.label)
                        sub_folder = f"{cat_folder}/{s_idx:02d}_{sub_slug}"
                        manifest_lines.append(
                            f"  [{s_idx:02d}] {sub.label}/"
                        )
                        for i_idx, item in enumerate(sub.items, start=1):
                            tpl, jobs, alias = _resolve_item(item)
                            _write_one(
                                zf,
                                idx=i_idx,
                                template=tpl,
                                job_ids=jobs,
                                scenario_alias=alias,
                                folder=sub_folder,
                                depth_prefix="    ",
                            )
            else:
                for idx, item in enumerate(items, start=1):
                    tpl, jobs, alias = _resolve_item(item)
                    _write_one(
                        zf,
                        idx=idx,
                        template=tpl,
                        job_ids=jobs,
                        scenario_alias=alias,
                        folder="",
                        depth_prefix="",
                    )

            zf.writestr("README.txt", "\n".join(manifest_lines))

        buffer.seek(0)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"Reporte_OSeMOSYS_{ts}.zip"
        return buffer, filename


def _report_to_public_dict(
    obj: ReportTemplate,
    *,
    current_user_id: uuid.UUID,
    owner_username: str | None,
    is_favorite: bool = False,
) -> dict:
    return {
        "id": obj.id,
        "name": obj.name,
        "description": obj.description,
        "fmt": obj.fmt,
        "items": list(obj.items or []),
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
        "is_public": bool(getattr(obj, "is_public", False)),
        "is_official": bool(getattr(obj, "is_official", False)),
        "owner_username": owner_username,
        "is_owner": obj.user_id == current_user_id,
        "layout": getattr(obj, "layout", None),
        "scenario_aliases": getattr(obj, "scenario_aliases", None),
        "default_job_ids": getattr(obj, "default_job_ids", None),
        "year_from": getattr(obj, "year_from", None),
        "year_to": getattr(obj, "year_to", None),
        "is_favorite": bool(is_favorite),
    }


class ReportTemplateService:
    """CRUD de reportes guardados (colecciones ordenadas de chart-templates).

    Visibilidad:
      - Dueño: acceso total (ver, editar, eliminar).
      - ``is_public=True``: otros usuarios autenticados pueden verlo y
        cargarlo en su generador (no editarlo).
      - ``is_official=True``: reporte curado, visible a todos; solo editable
        por usuarios con ``can_manage_catalogs``. Al marcarse oficial, fuerza
        ``is_public=True``.
    """

    @staticmethod
    def _promote_items_to_public(
        db: Session, *, item_ids: list[int]
    ) -> int:
        """Marca como públicas todas las plantillas indicadas (idempotente).

        Devuelve el número de filas promovidas. Se usa al marcar un reporte
        como oficial: así cualquier usuario que cargue el reporte puede ver
        las gráficas referenciadas aunque el dueño las tuviera privadas.
        """
        if not item_ids:
            return 0
        rows = (
            db.query(SavedChartTemplate)
            .filter(
                SavedChartTemplate.id.in_(item_ids),
                SavedChartTemplate.is_public.is_(False),
            )
            .all()
        )
        for r in rows:
            r.is_public = True
        return len(rows)

    @staticmethod
    def _normalize_items(
        db: Session,
        *,
        user_id: uuid.UUID,
        items: list[int],
        current_user: User | None = None,
    ) -> list[int]:
        """Valida que las plantillas existan y sean accesibles.

        Accesibles para el reporte si: son del dueño del reporte (``user_id``),
        son públicas, o pertenecen al usuario que realiza la operación
        (``current_user``) — caso típico: Admin Reportes agrega a un reporte
        ajeno sus propias plantillas recién creadas, o un usuario dueño agrega
        sus propias privadas.
        """
        cleaned = [int(x) for x in items]
        if not cleaned:
            raise ValueError("El reporte debe tener al menos una gráfica.")
        # Los reportes permiten duplicados (misma plantilla con distintos
        # escenarios), así que NO deduplicamos. Sólo validamos accesibilidad
        # sobre el conjunto de ids distintos.
        unique_ids = list({int(t) for t in cleaned})
        visibility = [
            SavedChartTemplate.user_id == user_id,
            SavedChartTemplate.is_public.is_(True),
        ]
        if current_user is not None:
            visibility.append(SavedChartTemplate.user_id == current_user.id)
            if bool(
                getattr(current_user, "is_admin_reports", False)
                or getattr(current_user, "can_manage_scenarios", False)
            ):
                # Admin Reportes puede referenciar cualquier plantilla existente.
                visibility = [SavedChartTemplate.id == SavedChartTemplate.id]
        rows = db.execute(
            select(SavedChartTemplate).where(
                SavedChartTemplate.id.in_(unique_ids),
                or_(*visibility),
            )
        ).scalars().all()
        existing = {int(r.id) for r in rows}
        missing = [tid for tid in unique_ids if tid not in existing]
        if missing:
            raise NotFoundError(
                f"Plantillas no encontradas o sin acceso: {missing}"
            )
        return cleaned

    @staticmethod
    def list_accessible(
        db: Session,
        *,
        current_user: User,
        include_others_private: bool = False,
    ) -> list[dict]:
        """Lista reportes accesibles con orden: oficiales → favoritos → resto.

        Si ``include_others_private=True`` y el usuario tiene ``is_admin_reports``
        (o ``is_admin`` como superconjunto), también se incluyen reportes
        privados de otros usuarios (solo lectura).
        """
        user_id = current_user.id
        is_admin_reports = bool(
            getattr(current_user, "is_admin_reports", False)
            or getattr(current_user, "can_manage_scenarios", False)
        )
        fav_ids = _load_report_favorite_ids(db, user_id=user_id)

        visibility_clause = or_(
            ReportTemplate.user_id == user_id,
            ReportTemplate.is_public.is_(True),
            ReportTemplate.is_official.is_(True),
        )
        # Admin reports con opt-in: amplía para cubrir privados ajenos.
        if include_others_private and is_admin_reports:
            visibility_clause = None  # ver todos los reportes

        stmt = (
            select(ReportTemplate, User.username)
            .join(User, User.id == ReportTemplate.user_id)
        )
        if visibility_clause is not None:
            stmt = stmt.where(visibility_clause)
        stmt = stmt.order_by(
            ReportTemplate.is_official.desc(),
            (ReportTemplate.user_id == user_id).desc(),
            ReportTemplate.updated_at.desc(),
        )
        rows = db.execute(stmt).all()
        out = [
            _report_to_public_dict(
                obj,
                current_user_id=user_id,
                owner_username=username,
                is_favorite=int(obj.id) in fav_ids,
            )
            for obj, username in rows
        ]
        # Orden final: oficiales primero, luego favoritos, luego el resto
        # (stable: mantiene el orden previo dentro de cada grupo).
        def _rank(d: dict) -> int:
            if d.get("is_official"):
                return 0
            if d.get("is_favorite"):
                return 1
            return 2

        out.sort(key=_rank)
        return out

    @staticmethod
    def get_accessible(
        db: Session,
        *,
        current_user: User,
        report_id: int,
    ) -> tuple[ReportTemplate, str | None]:
        row = db.execute(
            select(ReportTemplate, User.username)
            .join(User, User.id == ReportTemplate.user_id)
            .where(ReportTemplate.id == report_id)
        ).one_or_none()
        if row is None:
            raise NotFoundError("Reporte no encontrado.")
        obj, username = row
        is_admin_reports = bool(
            getattr(current_user, "is_admin_reports", False)
            or getattr(current_user, "can_manage_scenarios", False)
        )
        if (
            obj.user_id != current_user.id
            and not bool(getattr(obj, "is_public", False))
            and not bool(getattr(obj, "is_official", False))
            and not is_admin_reports
        ):
            raise NotFoundError("Reporte no encontrado.")
        return obj, username

    @staticmethod
    def get_for_user(
        db: Session, *, user_id: uuid.UUID, report_id: int
    ) -> ReportTemplate:
        """Owner-only (para mutaciones que no requieren admin)."""
        obj = db.get(ReportTemplate, report_id)
        if obj is None or obj.user_id != user_id:
            raise NotFoundError("Reporte no encontrado.")
        return obj

    @staticmethod
    def _resolve_owner_username(
        db: Session, *, user_id: uuid.UUID
    ) -> str | None:
        return db.scalar(select(User.username).where(User.id == user_id))

    @staticmethod
    def _is_admin_reports(user: User) -> bool:
        return bool(
            getattr(user, "is_admin_reports", False)
            or getattr(user, "can_manage_scenarios", False)
        )

    @staticmethod
    def create(
        db: Session,
        *,
        current_user: User,
        name: str,
        description: str | None,
        fmt: str,
        items: list[int],
        is_public: bool = False,
        is_official: bool = False,
        layout: dict | None = None,
        scenario_aliases: list[str] | None = None,
        default_job_ids: list[int | None] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> dict:
        if is_official and not ReportTemplateService._is_admin_reports(current_user):
            raise ForbiddenError(
                "Se requiere permiso 'Admin Reportes' para marcar un reporte como oficial."
            )
        ordered = ReportTemplateService._normalize_items(
            db, user_id=current_user.id, items=items, current_user=current_user
        )
        obj = ReportTemplate(
            user_id=current_user.id,
            name=name.strip()[:255],
            description=description,
            fmt=fmt,
            items=ordered,
            is_public=bool(is_public) or bool(is_official),
            is_official=bool(is_official),
            layout=layout,
            scenario_aliases=(list(scenario_aliases) if scenario_aliases else None),
            default_job_ids=(list(default_job_ids) if default_job_ids else None),
            year_from=year_from,
            year_to=year_to,
        )
        db.add(obj)
        # Si el reporte es compartido (público u oficial), promovemos las
        # plantillas referenciadas a públicas — así cualquier usuario que
        # cargue el reporte ve y usa todas las gráficas en su generador.
        if obj.is_public or obj.is_official:
            ReportTemplateService._promote_items_to_public(
                db, item_ids=ordered
            )
        db.commit()
        db.refresh(obj)
        username = ReportTemplateService._resolve_owner_username(
            db, user_id=current_user.id
        )
        return _report_to_public_dict(
            obj,
            current_user_id=current_user.id,
            owner_username=username,
            is_favorite=False,
        )

    @staticmethod
    def update(
        db: Session,
        *,
        current_user: User,
        report_id: int,
        name: str | None,
        description: str | None | object = ...,
        fmt: str | None,
        items: list[int] | None,
        is_public: bool | None = None,
        is_official: bool | None = None,
        layout: dict | None | object = ...,
        scenario_aliases: list[str] | None | object = ...,
        default_job_ids: list[int | None] | None | object = ...,
        year_from: int | None | object = ...,
        year_to: int | None | object = ...,
    ) -> dict:
        """Actualiza el reporte con reglas de acceso granulares.

        Reglas:
          - Dueño: edita todo excepto ``is_official`` (requiere Admin Reportes).
          - Admin Reportes (no dueño):
            * Reportes oficiales → edita todo.
            * Reportes públicos no oficiales → puede renombrar + toggle oficial.
            * Reportes privados → lectura (no edita).
          - Otros usuarios: no pueden editar reportes que no son suyos.
        """
        is_admin_reports = ReportTemplateService._is_admin_reports(current_user)
        obj = db.get(ReportTemplate, report_id)
        if obj is None:
            raise NotFoundError("Reporte no encontrado.")

        is_owner = obj.user_id == current_user.id
        is_official_current = bool(getattr(obj, "is_official", False))
        is_public_current = bool(getattr(obj, "is_public", False))

        if not is_owner and not is_admin_reports:
            raise NotFoundError("Reporte no encontrado.")

        # Ámbito de mutaciones permitidas según combinación de rol + visibilidad.
        full_edit = is_owner or (is_admin_reports and is_official_current)
        rename_and_official_only = (
            is_admin_reports
            and not is_owner
            and is_public_current
            and not is_official_current
        )

        # Cambiar is_official requiere Admin Reportes.
        if is_official is not None and not is_admin_reports:
            raise ForbiddenError(
                "Solo Admin Reportes puede cambiar el estado 'oficial'."
            )

        # Si NO se tiene edit full, validar que solo vengan cambios permitidos.
        if not full_edit:
            if not rename_and_official_only:
                raise ForbiddenError(
                    "No tienes permiso para editar este reporte."
                )
            # En modo rename/official-only, permitir solo `name` e `is_official`.
            disallowed = [
                (description is not ..., "description"),
                (fmt is not None, "fmt"),
                (items is not None, "items"),
                (is_public is not None, "is_public"),
                (layout is not ..., "layout"),
                (scenario_aliases is not ..., "scenario_aliases"),
                (default_job_ids is not ..., "default_job_ids"),
                (year_from is not ..., "year_from"),
                (year_to is not ..., "year_to"),
            ]
            bad = [n for (flag, n) in disallowed if flag]
            if bad:
                raise ForbiddenError(
                    "En reportes públicos ajenos solo puedes cambiar 'name' "
                    "y 'is_official'. Campos no permitidos: " + ", ".join(bad)
                )

        if name is not None:
            obj.name = name.strip()[:255]
        if description is not ...:
            obj.description = description
        if fmt is not None:
            obj.fmt = fmt
        if items is not None:
            obj.items = ReportTemplateService._normalize_items(
                db, user_id=obj.user_id, items=items, current_user=current_user
            )
        if is_public is not None:
            obj.is_public = bool(is_public)
        if is_official is not None:
            obj.is_official = bool(is_official)
            if obj.is_official:
                obj.is_public = True  # un oficial siempre es público
        if layout is not ...:
            obj.layout = layout
        if scenario_aliases is not ...:
            obj.scenario_aliases = (
                list(scenario_aliases) if scenario_aliases else None
            )
        if default_job_ids is not ...:
            obj.default_job_ids = (
                list(default_job_ids) if default_job_ids else None
            )
        if year_from is not ...:
            obj.year_from = year_from  # type: ignore[assignment]
        if year_to is not ...:
            obj.year_to = year_to  # type: ignore[assignment]
        # Si el reporte quedó compartido (público u oficial), promovemos sus
        # plantillas a públicas.
        if obj.is_public or obj.is_official:
            ReportTemplateService._promote_items_to_public(
                db, item_ids=list(obj.items or [])
            )
        db.commit()
        db.refresh(obj)
        username = ReportTemplateService._resolve_owner_username(
            db, user_id=obj.user_id
        )
        fav = db.execute(
            select(ReportTemplateFavorite).where(
                ReportTemplateFavorite.user_id == current_user.id,
                ReportTemplateFavorite.report_id == obj.id,
            )
        ).scalar_one_or_none()
        return _report_to_public_dict(
            obj,
            current_user_id=current_user.id,
            owner_username=username,
            is_favorite=fav is not None,
        )

    @staticmethod
    def delete(
        db: Session, *, current_user: User, report_id: int
    ) -> None:
        """Borra el reporte. Dueño puede borrar el suyo; Admin Reportes puede
        borrar oficiales. No puede borrar reportes públicos no oficiales ajenos
        ni privados ajenos.
        """
        is_admin_reports = ReportTemplateService._is_admin_reports(current_user)
        obj = db.get(ReportTemplate, report_id)
        if obj is None:
            raise NotFoundError("Reporte no encontrado.")
        is_owner = obj.user_id == current_user.id
        is_official = bool(getattr(obj, "is_official", False))
        if not is_owner and not (is_admin_reports and is_official):
            raise ForbiddenError("No tienes permiso para borrar este reporte.")
        db.delete(obj)
        db.commit()

    # ---------------- Favoritos ----------------

    @staticmethod
    def set_favorite(
        db: Session,
        *,
        current_user: User,
        report_id: int,
        is_favorite: bool,
    ) -> dict:
        obj, username = ReportTemplateService.get_accessible(
            db, current_user=current_user, report_id=report_id
        )
        existing = db.execute(
            select(ReportTemplateFavorite).where(
                ReportTemplateFavorite.user_id == current_user.id,
                ReportTemplateFavorite.report_id == report_id,
            )
        ).scalar_one_or_none()
        if is_favorite and existing is None:
            db.add(
                ReportTemplateFavorite(
                    user_id=current_user.id, report_id=report_id,
                )
            )
            db.commit()
        elif not is_favorite and existing is not None:
            db.delete(existing)
            db.commit()
        return _report_to_public_dict(
            obj,
            current_user_id=current_user.id,
            owner_username=username,
            is_favorite=bool(is_favorite),
        )

    # ---------------- Copy ----------------

    @staticmethod
    def copy_report(
        db: Session,
        *,
        current_user: User,
        report_id: int,
        new_name: str | None = None,
    ) -> dict:
        """Crea una copia del reporte para el usuario actual.

        Para las plantillas de gráfica referenciadas:
          - Si la plantilla es accesible (propia o pública), se reutiliza.
          - Si NO es accesible (privada ajena — solo visible porque el caller
            es Admin Reportes mirando reportes privados), se clona una copia
            privada para el usuario y se referencia esa.
        La copia del reporte nace como PRIVADA y no oficial, dueño = caller.
        El layout se clona tal cual, reemplazando referencias a IDs clonados.
        """
        src, _ = ReportTemplateService.get_accessible(
            db, current_user=current_user, report_id=report_id
        )
        original_ids = list(src.items or [])

        # Resolver accesibilidad de cada plantilla.
        accessible_rows = db.execute(
            select(SavedChartTemplate).where(
                SavedChartTemplate.id.in_(original_ids),
                or_(
                    SavedChartTemplate.user_id == current_user.id,
                    SavedChartTemplate.is_public.is_(True),
                ),
            )
        ).scalars().all()
        accessible_set = {int(r.id) for r in accessible_rows}

        # Mapa oldId -> nuevoId (solo para los clonados).
        id_map: dict[int, int] = {}
        # Clonar las que no son accesibles.
        inaccessible_ids = [i for i in original_ids if i not in accessible_set]
        if inaccessible_ids:
            originals = db.execute(
                select(SavedChartTemplate).where(
                    SavedChartTemplate.id.in_(inaccessible_ids),
                )
            ).scalars().all()
            for orig in originals:
                clone = SavedChartTemplate(
                    user_id=current_user.id,
                    name=orig.name,
                    description=orig.description,
                    tipo=orig.tipo,
                    un=orig.un,
                    sub_filtro=orig.sub_filtro,
                    loc=orig.loc,
                    variable=orig.variable,
                    agrupar_por=orig.agrupar_por,
                    view_mode=orig.view_mode,
                    compare_mode=orig.compare_mode,
                    bar_orientation=orig.bar_orientation,
                    facet_placement=orig.facet_placement,
                    facet_legend_mode=orig.facet_legend_mode,
                    num_scenarios=orig.num_scenarios,
                    legend_title=orig.legend_title,
                    filename_mode=orig.filename_mode,
                    table_period_years=getattr(orig, "table_period_years", None),
                    table_cumulative=getattr(orig, "table_cumulative", None),
                    custom_series_order=getattr(orig, "custom_series_order", None),
                    y_axis_min=getattr(orig, "y_axis_min", None),
                    y_axis_max=getattr(orig, "y_axis_max", None),
                    is_public=False,  # privadas en la copia
                )
                db.add(clone)
                db.flush()
                id_map[int(orig.id)] = int(clone.id)

        # Construir la nueva lista de items.
        new_items = [id_map.get(i, i) for i in original_ids]

        # Reescribir el layout reemplazando las referencias a ids antiguos.
        def _remap_layout(layout: dict | None) -> dict | None:
            if not isinstance(layout, dict):
                return layout
            cats = layout.get("categories") or []
            new_cats = []
            for c in cats:
                new_c = {
                    **c,
                    "items": [id_map.get(int(i), int(i)) for i in c.get("items", [])],
                    "subcategories": [
                        {
                            **s,
                            "items": [
                                id_map.get(int(i), int(i)) for i in s.get("items", [])
                            ],
                        }
                        for s in c.get("subcategories", [])
                    ],
                }
                new_cats.append(new_c)
            return {**layout, "categories": new_cats}

        copy_name = (new_name or f"{src.name} (copia)").strip()[:255]
        copy = ReportTemplate(
            user_id=current_user.id,
            name=copy_name,
            description=src.description,
            fmt=src.fmt,
            items=new_items,
            is_public=False,
            is_official=False,
            layout=_remap_layout(src.layout),
            year_from=getattr(src, "year_from", None),
            year_to=getattr(src, "year_to", None),
        )
        db.add(copy)
        db.commit()
        db.refresh(copy)
        username = ReportTemplateService._resolve_owner_username(
            db, user_id=current_user.id
        )
        return _report_to_public_dict(
            copy,
            current_user_id=current_user.id,
            owner_username=username,
            is_favorite=False,
        )
