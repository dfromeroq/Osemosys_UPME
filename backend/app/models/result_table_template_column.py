"""Reglas de presentación por columna (categoría / año) para una plantilla de tabla."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ResultTableTemplateColumn(Base):
    """Override por valor de categoría (p. ej. año como string)."""

    __tablename__ = "result_table_template_column"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "category_key",
            name="uq_rtt_col_template_category",
        ),
        Index("ix_rtt_col_template", "template_id"),
        {"schema": "osemosys"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("osemosys.result_table_template.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_key: Mapped[str] = mapped_column(String(64), nullable=False)
    hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    template: Mapped[object] = relationship(
        "ResultTableTemplate",
        back_populates="column_rules",
    )
