"""Plantilla global de tabla de resultados (vista tabla de una gráfica).

Gestionada por usuarios con permiso Admin reportes; visible para todos
los usuarios autenticados cuando está habilitada.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ResultTableTemplate(Base):
    """Definición de una tabla automática en la página de detalle de resultados."""

    __tablename__ = "result_table_template"
    __table_args__ = (
        Index("ix_result_table_template_enabled_sort", "is_enabled", "sort_order"),
        {"schema": "osemosys"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    #: Nombre corto en el panel de administración.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Clave estable para siembra idempotente (Alembic/seed). Null = creado en admin.
    seed_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    #: Título mostrado sobre la tabla; si es null se usa el título del chart-data.
    display_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    tipo: Mapped[str] = mapped_column(String(64), nullable=False)
    un: Mapped[str] = mapped_column(String(16), nullable=False)
    sub_filtro: Mapped[str | None] = mapped_column(String(64), nullable=True)
    loc: Mapped[str | None] = mapped_column(String(32), nullable=True)
    variable: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agrupar_por: Mapped[str | None] = mapped_column(String(32), nullable=True)
    region: Mapped[str | None] = mapped_column(String(16), nullable=True)
    timeslice: Mapped[str | None] = mapped_column(String(32), nullable=True)

    table_period_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_cumulative: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    custom_series_order: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    y_axis_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_axis_max: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    column_rules: Mapped[list["ResultTableTemplateColumn"]] = relationship(
        "ResultTableTemplateColumn",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="ResultTableTemplateColumn.id",
    )
