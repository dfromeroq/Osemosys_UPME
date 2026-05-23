"""Schemas de API para ejecución y monitoreo de simulaciones."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.scenario import ScenarioTagPublic, SimulationType

SimulationStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
SimulationSolver = Literal["highs", "glpk", "gurobi"]
SimulationInputMode = Literal["SCENARIO", "CSV_UPLOAD"]
#: Estado del análisis de infactibilidad on-demand para un job infactible.
#: ``NONE`` = aún no se ha corrido; se dispara vía POST /simulations/{id}/diagnose-infeasibility.
DiagnosticStatus = Literal["NONE", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED"]


class SimulationSubmit(BaseModel):
    """Payload para encolar una simulación."""

    scenario_id: int = Field(gt=0)
    solver_name: SimulationSolver = "highs"
    #: Si ``True``, el pipeline corre el análisis enriquecido de infactibilidad
    #: (IIS + mapeo a parámetros) automáticamente cuando el modelo es infactible.
    #: Si ``False`` (default), el diagnóstico queda para disparar manualmente
    #: desde la UI, evitando tiempo extra en cada corrida.
    run_iis_analysis: bool = False
    #: Si ``True``, el pipeline escribe el modelo en formato ``.lp`` en
    #: ``tmp/lp-files/sim_<id>_<nombre>_<timestamp>.lp`` antes de resolver.
    generate_lp: bool = False
    display_name: str | None = Field(
        default=None,
        max_length=255,
        description="Nombre opcional para esta corrida (resultados y exportación). Si se omite, se usa el nombre del escenario.",
    )


class SimulationJobDisplayNamePatch(BaseModel):
    """Actualización parcial de metadatos editables por el dueño.

    Conserva el nombre histórico (``display_name``) por compatibilidad, pero
    ahora acepta también ``is_public`` para cambiar la visibilidad del
    resultado (solo el dueño).
    """

    display_name: str | None = Field(
        default=None,
        max_length=255,
        description="Nombre corto para resultados y archivos; vacío o null borra el alias.",
    )
    is_public: bool | None = Field(
        default=None,
        description="True = visible por todos los usuarios; False = solo el dueño.",
    )


class SimulationJobFavoritePatch(BaseModel):
    """Marca/desmarca un resultado como favorito del usuario autenticado."""

    is_favorite: bool


class SimulationJobPublic(BaseModel):
    """Estado público de un job de simulación."""

    id: int
    scenario_id: int | None = None
    scenario_name: str | None = None
    scenario_tag: ScenarioTagPublic | None = None
    scenario_tags: list[ScenarioTagPublic] = Field(default_factory=list)
    display_name: str | None = None
    user_id: str
    username: str | None = None
    solver_name: SimulationSolver
    #: Hilos efectivamente entregados al solver (NULL si el solver no soporta
    #: multihilo o si la lectura del valor efectivo falló).
    solver_threads_used: int | None = None
    input_mode: SimulationInputMode = "SCENARIO"
    input_name: str | None = None
    simulation_type: SimulationType = "NATIONAL"
    status: SimulationStatus
    progress: float
    cancel_requested: bool
    queue_position: int | None = None
    result_ref: str | None = None
    error_message: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    #: True si el job terminó en SUCCEEDED pero el solver reportó infactibilidad o hay diagnóstico estructurado.
    is_public: bool = True
    is_favorite: bool = False
    is_infeasible_result: bool = False
    #: El usuario pidió diagnóstico automático al encolar la simulación.
    run_iis_analysis: bool = False
    #: El usuario pidió que se escriba el modelo a ``.lp`` durante la corrida.
    generate_lp: bool = False
    #: ``True`` cuando el ``.lp`` ya está escrito y disponible para descarga.
    has_lp_file: bool = False
    #: Estado del análisis enriquecido de infactibilidad (opcional, se dispara
    #: desde la UI con el botón "Correr diagnóstico de infactibilidad").
    diagnostic_status: DiagnosticStatus = "NONE"
    #: Motivo del último fallo del análisis (si `diagnostic_status == 'FAILED'`).
    diagnostic_error: str | None = None
    #: Timestamp ISO en que inició el diagnóstico (solo si ya arrancó).
    diagnostic_started_at: str | None = None
    #: Timestamp ISO en que finalizó (SUCCEEDED / FAILED / cancelado).
    diagnostic_finished_at: str | None = None
    #: Duración total del diagnóstico en segundos.
    diagnostic_seconds: float | None = None


class SimulationOverviewPublic(BaseModel):
    """Resumen operacional del tablero global de simulaciones."""

    queued_count: int
    running_count: int
    active_count: int
    total_count: int
    services_memory_total_bytes: int = 0


class SimulationLogPublic(BaseModel):
    """Evento/log de progreso de una simulación."""

    id: int
    event_type: str
    stage: str | None
    message: str | None
    progress: float | None
    created_at: datetime


class ConstraintViolationPublic(BaseModel):
    """Restricción violada detectada durante un diagnóstico de infactibilidad."""

    name: str
    body: float
    lower: float | None = None
    upper: float | None = None
    side: str
    violation: float


class VarBoundConflictPublic(BaseModel):
    """Variable con bounds incompatibles (LB > UB)."""

    name: str
    lb: float
    ub: float
    gap: float


class IISReportPublic(BaseModel):
    """Irreducible Inconsistent Subsystem reportado por el solver (HiGHS si está disponible)."""

    available: bool = False
    method: str | None = None
    constraint_names: list[str] = Field(default_factory=list)
    variable_names: list[str] = Field(default_factory=list)
    unavailable_reason: str | None = None


class ParamHitPublic(BaseModel):
    """Fila puntual de un parámetro OSeMOSYS relacionado con una restricción violada."""

    param: str
    indices: dict[str, str] = Field(default_factory=dict)
    value: float | None = None
    is_default: bool = False
    #: Valor por defecto canónico del modelo OSeMOSYS (si se conoce).
    default_value: float | None = None
    #: Diferencia absoluta ``value - default_value``.
    diff_abs: float | None = None
    #: Score normalizado 0-100 de desviación del default.
    deviation_score: float | None = None


class ConstraintAnalysisPublic(BaseModel):
    """Análisis enriquecido de una restricción violada (mapeo a parámetros + IIS)."""

    name: str
    constraint_type: str
    indices: dict[str, str] = Field(default_factory=dict)
    body: float | None = None
    lower: float | None = None
    upper: float | None = None
    side: str = ""
    violation: float = 0.0
    in_iis: bool = False
    has_mapping: bool = False
    description: str = ""
    related_params: list[ParamHitPublic] = Field(default_factory=list)


class InfeasibilityOverviewPublic(BaseModel):
    """Resumen de alto nivel: años, tipos y códigos únicos en el IIS/violaciones."""

    years: list[int] = Field(default_factory=list)
    constraint_types: dict[str, int] = Field(default_factory=dict)
    variable_types: dict[str, int] = Field(default_factory=dict)
    techs_or_fuels: dict[str, int] = Field(default_factory=dict)
    total_constraints: int = 0
    total_variables: int = 0


class InfeasibilityDiagnosticsPublic(BaseModel):
    """Diagnóstico estructurado de infactibilidad del solver.

    Incluye el diagnóstico básico (restricciones violadas, bounds conflictivos)
    y el análisis enriquecido producido por
    :mod:`app.simulation.core.infeasibility_analysis` cuando está disponible:
    IIS vía HiGHS, mapeo de cada restricción a los parámetros OSeMOSYS que
    la alimentan y lista de prefijos sin mapeo estático.
    """

    constraint_violations: list[ConstraintViolationPublic] = Field(default_factory=list)
    var_bound_conflicts: list[VarBoundConflictPublic] = Field(default_factory=list)
    iis: IISReportPublic | None = None
    overview: InfeasibilityOverviewPublic | None = None
    top_suspects: list[ParamHitPublic] = Field(default_factory=list)
    constraint_analyses: list[ConstraintAnalysisPublic] = Field(default_factory=list)
    unmapped_constraint_prefixes: list[str] = Field(default_factory=list)
    csv_dir: str | None = None


class SimulationResultPublic(BaseModel):
    """Contrato del artefacto final de resultados de simulación."""

    job_id: int
    scenario_id: int | None = None
    records_used: int
    osemosys_param_records: int
    objective_value: float
    solver_status: str
    solver_name: SimulationSolver
    coverage_ratio: float
    total_demand: float
    total_dispatch: float
    total_unmet: float
    dispatch: list[dict]
    unmet_demand: list[dict]
    new_capacity: list[dict]
    annual_emissions: list[dict]
    osemosys_inputs_summary: list[dict]
    stage_times: dict = Field(default_factory=dict)
    model_timings: dict = Field(default_factory=dict)
    # Diccionario de solución tipo HiGHS: por variable, lista de {index: [...], value: number}
    sol: dict[str, list[dict]] = Field(default_factory=dict)
    # Variables intermedias tipo GLPK: ProductionByTechnology, UseByTechnology, etc.
    intermediate_variables: dict[str, list[dict]] = Field(default_factory=dict)
    infeasibility_diagnostics: InfeasibilityDiagnosticsPublic | None = None


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Contratos para envío, monitoreo y consulta de resultados de corridas.
#
# Posibles mejoras:
# - Tipar estructuras `dispatch/unmet/new_capacity` con modelos dedicados.
#
# Riesgos en producción:
# - `list[dict]` flexible acelera cambios pero reduce seguridad de contrato.
#
# Escalabilidad:
# - Serialización potencialmente pesada en resultados de gran tamaño.
