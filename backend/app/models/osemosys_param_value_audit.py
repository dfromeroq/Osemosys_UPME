"""Auditoría de mutaciones sobre filas OSeMOSYS (`osemosys_param_value`)."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OsemosysParamValueAudit(Base):
    """Trazabilidad de altas, bajas y modificaciones de valores OSeMOSYS por escenario."""

    __tablename__ = "osemosys_param_value_audit"
    __table_args__ = (
        CheckConstraint(
            "action IN ('INSERT','UPDATE','DELETE')",
            name="ck_osemosys_param_value_audit_action",
        ),
        CheckConstraint(
            "source IN ('API','EXCEL_APPLY','IMPORT_UPSERT')",
            name="ck_osemosys_param_value_audit_source",
        ),
        Index(
            "ix_osemosys_param_audit_scenario_param_created",
            "id_scenario",
            "param_name",
            "created_at",
        ),
        Index("ix_osemosys_param_audit_value_id", "id_osemosys_param_value"),
        Index("ix_osemosys_param_audit_scenario_batch", "id_scenario", "batch_id"),
        Index("ix_osemosys_param_audit_scenario_created", "id_scenario", "created_at"),
        Index("ix_osemosys_param_audit_reverted_by_audit_id", "reverted_by_audit_id"),
        Index("ix_osemosys_param_audit_reverts_entry_id", "reverts_entry_id"),
        {"schema": "osemosys"},
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    id_scenario: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("osemosys.scenario.id", ondelete="CASCADE"),
        nullable=False,
    )
    param_name: Mapped[str] = mapped_column(String(128), nullable=False)
    id_osemosys_param_value: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("osemosys.osemosys_param_value.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    old_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimensions_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    batch_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Marca puesta cuando este cambio fue posteriormente revertido por otra
    # operación. `reverted_by_audit_id` apunta a la entrada de auditoría que
    # ejecutó el revert (que tiene `is_revert=True`).
    reverted_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reverted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reverted_by_audit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # `True` cuando esta entrada es producto de una acción de revert.
    # `reverts_entry_id` apunta a la entrada que se está deshaciendo.
    is_revert: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    reverts_entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
