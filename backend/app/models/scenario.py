"""Modelo ORM de escenarios de análisis OSEMOSYS."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.scenario_tag import ScenarioTag


class Scenario(Base):
    """Escenario de trabajo (schema `osemosys`).

    `edit_policy` restringe quién puede modificar: OWNER_ONLY | OPEN | RESTRICTED.
    """

    __tablename__ = "scenario"
    __table_args__ = (
        CheckConstraint(
            "edit_policy IN ('OWNER_ONLY','OPEN','RESTRICTED')",
            name="scenario_edit_policy",
        ),
        CheckConstraint(
            "simulation_type IN ('NATIONAL','REGIONAL')",
            name="scenario_simulation_type",
        ),
        CheckConstraint(
            "processing_mode IN ('STANDARD','PREPROCESSED_CSV')",
            name="scenario_processing_mode",
        ),
        Index("ix_scenario_base_scenario_id", "base_scenario_id"),
        {"schema": "osemosys"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    base_scenario_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("osemosys.scenario.id", ondelete="RESTRICT"),
        nullable=True,
    )
    changed_param_names: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=None)
    edit_policy: Mapped[str] = mapped_column(String(20), nullable=False, default="OWNER_ONLY")
    simulation_type: Mapped[str] = mapped_column(String(20), nullable=False, default="NATIONAL")
    processing_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="STANDARD")
    is_template: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    udc_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    # Warnings de calidad de datos detectados por data_validation.
    # Estructura: ver DataQualityReport.to_dict().
    data_quality_warnings: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None
    )

    tags: Mapped[list["ScenarioTag"]] = relationship(
        "ScenarioTag",
        secondary="osemosys.scenario_tag_link",
        back_populates="scenarios",
    )
