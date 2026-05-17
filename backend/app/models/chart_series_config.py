"""Configuración global de series por tipo de gráfica y modo de agrupación."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChartSeriesConfig(Base):
    """Una fila por serie (código `COLOR` en chart_service) por chart+agrupación."""

    __tablename__ = "chart_series_config"
    __table_args__ = (
        UniqueConstraint(
            "tipo",
            "agrupar_por",
            "series_code",
            name="uq_chart_series_config_tipo_agrup_code",
        ),
        Index("ix_chart_series_config_tipo_agrup", "tipo", "agrupar_por", "sort_index"),
        {"schema": "osemosys"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String(64), nullable=False)
    agrupar_por: Mapped[str] = mapped_column(String(32), nullable=False)
    series_code: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    group_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
