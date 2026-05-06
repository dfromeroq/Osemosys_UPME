"""Modelo ORM para jobs de simulacion en cola/ejecucion."""

from sqlalchemy import (
    Boolean,
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


class SimulationJob(Base):
    """Estado principal de cada corrida OSEMOSYS solicitada por usuario."""

    __tablename__ = "simulation_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="simulation_job_status",
        ),
        CheckConstraint(
            "input_mode IN ('SCENARIO','CSV_UPLOAD')",
            name="simulation_job_input_mode",
        ),
        CheckConstraint(
            "simulation_type IN ('NATIONAL','REGIONAL')",
            name="simulation_job_simulation_type",
        ),
        Index("ix_simulation_job_user_status", "user_id", "status"),
        Index("ix_simulation_job_scenario", "scenario_id"),
        Index("ix_simulation_job_status_queue", "status", "queued_at"),
        {"schema": "osemosys"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[object] = mapped_column(
        Uuid, ForeignKey("core.user.id", ondelete="RESTRICT"), nullable=False
    )
    scenario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("osemosys.scenario.id", ondelete="RESTRICT"), nullable=True
    )
    solver_name: Mapped[str] = mapped_column(String(20), nullable=False, default="highs")
    input_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="SCENARIO")
    simulation_type: Mapped[str] = mapped_column(String(20), nullable=False, default="NATIONAL")
    parallel_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Nombre opcional definido por el usuario para identificar la corrida en resultados/exportación.
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Si ``True``, cuando el solver termine infactible el pipeline corre
    #: automáticamente el análisis enriquecido (IIS + mapeo a parámetros).
    #: Si ``False`` (default), el diagnóstico queda disponible on-demand desde
    #: la UI vía POST /simulations/{id}/diagnose-infeasibility.
    run_iis_analysis: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Si ``True``, el pipeline escribe el modelo como archivo `.lp` en
    #: ``tmp/lp-files/`` con nombre ``sim_<id>_<nombre>_<timestamp>.lp`` para
    #: poder inspeccionarlo o resolverlo en otra herramienta. ``False`` (default)
    #: omite la escritura para ahorrar I/O.
    generate_lp: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Ruta absoluta dentro del worker al archivo `.lp` escrito (cuando
    #: ``generate_lp=True``). Sirve como puntero estable para el endpoint de
    #: descarga, independiente de que el ``display_name`` cambie luego.
    lp_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Visibilidad del resultado.
    #: ``True`` (default) → cualquier usuario autenticado lo ve en global scope.
    #: ``False`` → solo lo ve el dueño (aunque se liste con scope=global).
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Result summary (populated when job succeeds) ---
    #: Hilos efectivamente entregados al solver (leídos del propio optimizador
    #: post-configuración). NULL si el solver no soporta multihilo (e.g. GLPK)
    #: o si la lectura del valor efectivo falló.
    solver_threads_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    objective_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_demand: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_dispatch: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_unmet: Mapped[float | None] = mapped_column(Float, nullable=True)
    records_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    osemosys_param_records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage_times_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    model_timings_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    inputs_summary_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    infeasibility_diagnostics_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
