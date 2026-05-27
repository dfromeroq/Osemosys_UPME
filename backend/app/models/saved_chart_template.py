"""Plantilla de gráfica guardada por un usuario para generar reportes.

No referencia `job_id`: la plantilla define el tipo de gráfica y sus filtros,
y el/los `job_id`s se eligen al momento de generar el reporte.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


from app.db.base import Base


class SavedChartTemplate(Base):
    """Configuración reutilizable de una gráfica (sin los escenarios asignados)."""

    __tablename__ = "saved_chart_template"
    __table_args__ = (
        Index("ix_saved_chart_template_user_created", "user_id", "created_at"),
        {"schema": "osemosys"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("core.user.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    tipo: Mapped[str] = mapped_column(String(64), nullable=False)
    un: Mapped[str] = mapped_column(String(16), nullable=False)
    un2: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sub_filtro: Mapped[str | None] = mapped_column(String(64), nullable=True)
    loc: Mapped[str | None] = mapped_column(String(32), nullable=True)
    variable: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agrupar_por: Mapped[str | None] = mapped_column(String(32), nullable=True)

    view_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    compare_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="off")
    bar_orientation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    facet_placement: Mapped[str | None] = mapped_column(String(16), nullable=True)
    facet_legend_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)

    num_scenarios: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    legend_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Título personalizado usado cuando la gráfica se renderiza dentro de un
    #: reporte (export ZIP o dashboard). Si es null, se usa el título auto-generado.
    report_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Años a graficar cuando ``compare_mode == "by-year"``. Null en otros modos.
    years_to_plot: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    #: Series manuales overlay (línea) — lista de dicts `{id, name, color, data: [[y, v], ...]}`.
    synthetic_series: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    #: Solo aplica cuando ``view_mode == "table"``: muestra años cada N
    #: (5 = cada 5 años). ``None`` = todos los años.
    table_period_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Solo aplica cuando ``view_mode == "table"``: si ``True`` los valores
    #: por serie se acumulan a lo largo de las categorías visibles.
    table_cumulative: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    #: Override del orden de las series (lista de nombres). La primera entrada
    #: queda arriba del stack. ``None`` = orden natural.
    custom_series_order: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    #: Override del valor mínimo del eje Y. ``None`` = auto.
    y_axis_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Override del valor máximo del eje Y. ``None`` = auto.
    y_axis_max: Mapped[float | None] = mapped_column(Float, nullable=True)

    #: Si ``True``, la gráfica es visible (solo lectura) para otros usuarios,
    #: que pueden usarla en sus propios reportes. Solo el dueño puede editar.
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
