"""Modelo ORM para operaciones asíncronas de escenarios."""

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScenarioOperationJob(Base):
    """Estado principal de operaciones largas de escenarios."""

    __tablename__ = "scenario_operation_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="scenario_operation_job_status",
        ),
        CheckConstraint(
            "operation_type IN ('CLONE_SCENARIO','APPLY_EXCEL_CHANGES','DELETE_SCENARIO')",
            name="scenario_operation_job_type",
        ),
        Index("ix_scenario_operation_job_user_status", "user_id", "status"),
        Index("ix_scenario_operation_job_scenario", "scenario_id"),
        {"schema": "osemosys"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    user_id: Mapped[object] = mapped_column(
        Uuid, ForeignKey("core.user.id", ondelete="RESTRICT"), nullable=False
    )
    scenario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("osemosys.scenario.id", ondelete="SET NULL"), nullable=True
    )
    target_scenario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("osemosys.scenario.id", ondelete="SET NULL"), nullable=True
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
