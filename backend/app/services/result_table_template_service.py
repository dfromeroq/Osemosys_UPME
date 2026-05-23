"""CRUD de plantillas globales de tablas de resultados (admin reportes)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete as sql_delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models import ResultTableTemplate, ResultTableTemplateColumn, User


def _template_load_options():
    return (selectinload(ResultTableTemplate.column_rules),)


def _fetch_template_loaded(db: Session, template_id: int) -> ResultTableTemplate:
    stmt = (
        select(ResultTableTemplate)
        .where(ResultTableTemplate.id == template_id)
        .options(*_template_load_options())
    )
    obj = db.scalars(stmt).first()
    if obj is None:
        raise NotFoundError("Plantilla de tabla no encontrada.")
    return obj


class ResultTableTemplateService:
    @staticmethod
    def _is_admin_reports(user: User) -> bool:
        return bool(
            getattr(user, "is_admin_reports", False)
            or getattr(user, "can_manage_scenarios", False)
        )

    @staticmethod
    def require_reports_admin(current_user: User) -> None:
        if not ResultTableTemplateService._is_admin_reports(current_user):
            raise ForbiddenError("Se requiere permiso de administración de reportes.")

    @staticmethod
    def _replace_column_rules(
        db: Session, *, template_id: int, items: list[dict[str, Any]]
    ) -> None:
        db.execute(
            sql_delete(ResultTableTemplateColumn).where(
                ResultTableTemplateColumn.template_id == template_id
            )
        )
        for it in items:
            ck = str(it["category_key"]).strip()[:64]
            if not ck:
                continue
            db.add(
                ResultTableTemplateColumn(
                    template_id=template_id,
                    category_key=ck,
                    hidden=bool(it.get("hidden", False)),
                    sort_order=it.get("sort_order"),
                )
            )

    @staticmethod
    def list_enabled(db: Session) -> list[ResultTableTemplate]:
        stmt = (
            select(ResultTableTemplate)
            .where(ResultTableTemplate.is_enabled.is_(True))
            .options(*_template_load_options())
            .order_by(ResultTableTemplate.sort_order.asc(), ResultTableTemplate.id.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_all(db: Session, *, current_user: User) -> list[ResultTableTemplate]:
        if not ResultTableTemplateService._is_admin_reports(current_user):
            raise ForbiddenError("Se requiere permiso de administración de reportes.")
        stmt = (
            select(ResultTableTemplate)
            .options(*_template_load_options())
            .order_by(ResultTableTemplate.sort_order.asc(), ResultTableTemplate.id.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get(db: Session, template_id: int, *, current_user: User) -> ResultTableTemplate:
        stmt = (
            select(ResultTableTemplate)
            .where(ResultTableTemplate.id == template_id)
            .options(*_template_load_options())
        )
        obj = db.scalars(stmt).first()
        if obj is None:
            raise NotFoundError("Plantilla de tabla no encontrada.")
        if not obj.is_enabled and not ResultTableTemplateService._is_admin_reports(
            current_user
        ):
            raise NotFoundError("Plantilla de tabla no encontrada.")
        return obj

    @staticmethod
    def create(
        db: Session,
        *,
        current_user: User,
        data: dict[str, Any],
    ) -> ResultTableTemplate:
        if not ResultTableTemplateService._is_admin_reports(current_user):
            raise ForbiddenError("Se requiere permiso de administración de reportes.")
        column_items = list(data.pop("column_rules", []) or [])
        max_sort = db.scalar(select(func.max(ResultTableTemplate.sort_order)))
        next_sort = (max_sort if max_sort is not None else -1) + 1
        sort_order = data.get("sort_order")
        if sort_order is None:
            sort_order = next_sort
        obj = ResultTableTemplate(
            name=str(data["name"]).strip()[:255],
            display_title=(
                str(data["display_title"]).strip()[:255]
                if data.get("display_title")
                else None
            ),
            sort_order=int(sort_order),
            is_enabled=bool(data.get("is_enabled", True)),
            tipo=str(data["tipo"]).strip()[:64],
            un=str(data["un"]).strip()[:16],
            sub_filtro=(
                str(data["sub_filtro"]).strip()[:64] if data.get("sub_filtro") else None
            ),
            loc=str(data["loc"]).strip()[:32] if data.get("loc") else None,
            variable=(
                str(data["variable"]).strip()[:64] if data.get("variable") else None
            ),
            agrupar_por=(
                str(data["agrupar_por"]).strip()[:32]
                if data.get("agrupar_por")
                else None
            ),
            region=(
                str(data["region"]).strip()[:16] if data.get("region") else None
            ),
            timeslice=(
                str(data["timeslice"]).strip()[:32]
                if data.get("timeslice")
                else None
            ),
            table_period_years=data.get("table_period_years"),
            table_cumulative=data.get("table_cumulative"),
            custom_series_order=data.get("custom_series_order"),
            y_axis_min=data.get("y_axis_min"),
            y_axis_max=data.get("y_axis_max"),
            created_by_user_id=current_user.id,
        )
        db.add(obj)
        db.flush()
        ResultTableTemplateService._replace_column_rules(
            db, template_id=obj.id, items=column_items
        )
        db.commit()
        return _fetch_template_loaded(db, obj.id)

    @staticmethod
    def update(
        db: Session,
        *,
        current_user: User,
        template_id: int,
        data: dict[str, Any],
    ) -> ResultTableTemplate:
        if not ResultTableTemplateService._is_admin_reports(current_user):
            raise ForbiddenError("Se requiere permiso de administración de reportes.")
        obj = db.get(ResultTableTemplate, template_id)
        if obj is None:
            raise NotFoundError("Plantilla de tabla no encontrada.")
        column_items = data.pop("column_rules", None)
        if "name" in data and data["name"] is not None:
            obj.name = str(data["name"]).strip()[:255]
        if "display_title" in data:
            dt = data["display_title"]
            obj.display_title = (
                str(dt).strip()[:255] if dt not in (None, "") else None
            )
        if "sort_order" in data and data["sort_order"] is not None:
            obj.sort_order = int(data["sort_order"])
        if "is_enabled" in data and data["is_enabled"] is not None:
            obj.is_enabled = bool(data["is_enabled"])
        if "tipo" in data and data["tipo"] is not None:
            obj.tipo = str(data["tipo"]).strip()[:64]
        if "un" in data and data["un"] is not None:
            obj.un = str(data["un"]).strip()[:16]
        if "sub_filtro" in data:
            sf = data["sub_filtro"]
            obj.sub_filtro = str(sf).strip()[:64] if sf not in (None, "") else None
        if "loc" in data:
            v = data["loc"]
            obj.loc = str(v).strip()[:32] if v not in (None, "") else None
        if "variable" in data:
            v = data["variable"]
            obj.variable = str(v).strip()[:64] if v not in (None, "") else None
        if "agrupar_por" in data:
            v = data["agrupar_por"]
            obj.agrupar_por = str(v).strip()[:32] if v not in (None, "") else None
        if "region" in data:
            v = data["region"]
            obj.region = str(v).strip()[:16] if v not in (None, "") else None
        if "timeslice" in data:
            v = data["timeslice"]
            obj.timeslice = str(v).strip()[:32] if v not in (None, "") else None
        if "table_period_years" in data:
            obj.table_period_years = data["table_period_years"]
        if "table_cumulative" in data:
            obj.table_cumulative = data["table_cumulative"]
        if "custom_series_order" in data:
            obj.custom_series_order = data["custom_series_order"]
        if "y_axis_min" in data:
            obj.y_axis_min = data["y_axis_min"]
        if "y_axis_max" in data:
            obj.y_axis_max = data["y_axis_max"]
        db.add(obj)
        if column_items is not None:
            ResultTableTemplateService._replace_column_rules(
                db, template_id=obj.id, items=list(column_items)
            )
        db.commit()
        return _fetch_template_loaded(db, obj.id)

    @staticmethod
    def delete(db: Session, *, current_user: User, template_id: int) -> None:
        if not ResultTableTemplateService._is_admin_reports(current_user):
            raise ForbiddenError("Se requiere permiso de administración de reportes.")
        obj = db.get(ResultTableTemplate, template_id)
        if obj is None:
            raise NotFoundError("Plantilla de tabla no encontrada.")
        db.delete(obj)
        db.commit()

    @staticmethod
    def reorder(
        db: Session, *, current_user: User, ordered_ids: list[int]
    ) -> list[ResultTableTemplate]:
        if not ResultTableTemplateService._is_admin_reports(current_user):
            raise ForbiddenError("Se requiere permiso de administración de reportes.")
        for pos, tid in enumerate(ordered_ids):
            row = db.get(ResultTableTemplate, tid)
            if row is None:
                raise NotFoundError("Plantilla de tabla no encontrada.")
            row.sort_order = pos
            db.add(row)
        db.commit()
        stmt = (
            select(ResultTableTemplate)
            .options(*_template_load_options())
            .order_by(ResultTableTemplate.sort_order.asc(), ResultTableTemplate.id.asc())
        )
        return list(db.scalars(stmt).all())
