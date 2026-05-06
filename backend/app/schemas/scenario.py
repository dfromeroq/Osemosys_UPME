"""Schemas Pydantic para escenarios y permisos (schema `osemosys`)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.official_import import OfficialImportResult


EditPolicy = Literal["OWNER_ONLY", "OPEN", "RESTRICTED"]
SimulationType = Literal["NATIONAL", "REGIONAL"]
ScenarioPermissionScope = Literal["mine", "readable", "editable", "readonly"]

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ScenarioTagCategoryPublic(BaseModel):
    """Categoría jerárquica de etiquetas."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    hierarchy_level: int
    sort_order: int
    max_tags_per_scenario: int | None
    is_exclusive_combination: bool
    default_color: str


class ScenarioTagCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    hierarchy_level: int = Field(default=1, ge=1, le=10)
    sort_order: int = 0
    max_tags_per_scenario: int | None = Field(default=1, ge=1)
    is_exclusive_combination: bool = False
    default_color: str = Field(default="#64748B", min_length=7, max_length=7)

    @field_validator("default_color")
    @classmethod
    def _color_hex(cls, v: str) -> str:
        if not _HEX_COLOR.match(v):
            raise ValueError("default_color debe ser hexadecimal #RRGGBB.")
        return v


class ScenarioTagCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    hierarchy_level: int | None = Field(default=None, ge=1, le=10)
    sort_order: int | None = None
    max_tags_per_scenario: int | None = Field(default=None, ge=1)
    is_exclusive_combination: bool | None = None
    default_color: str | None = Field(default=None, min_length=7, max_length=7)

    @field_validator("default_color")
    @classmethod
    def _color_hex(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _HEX_COLOR.match(v):
            raise ValueError("default_color debe ser hexadecimal #RRGGBB.")
        return v

    @model_validator(mode="after")
    def _any_field(self):
        if all(
            getattr(self, f) is None
            for f in (
                "name",
                "hierarchy_level",
                "sort_order",
                "max_tags_per_scenario",
                "is_exclusive_combination",
                "default_color",
            )
        ):
            raise ValueError("Debes enviar al menos un campo para actualizar.")
        return self


class ScenarioTagPublic(BaseModel):
    """Etiqueta asignable a un escenario; pertenece a una categoría."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    sort_order: int
    category_id: int
    is_exclusive_combination: bool = False
    category: ScenarioTagCategoryPublic | None = None


class ScenarioTagCreate(BaseModel):
    category_id: int
    name: str = Field(min_length=1, max_length=128)
    color: str = Field(min_length=7, max_length=7)
    sort_order: int = 0
    is_exclusive_combination: bool | None = None

    @field_validator("color")
    @classmethod
    def _color_hex(cls, v: str) -> str:
        if not _HEX_COLOR.match(v):
            raise ValueError("color debe ser hexadecimal #RRGGBB.")
        return v


class ScenarioTagUpdate(BaseModel):
    category_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, min_length=7, max_length=7)
    sort_order: int | None = None
    is_exclusive_combination: bool | None = None

    @field_validator("color")
    @classmethod
    def _color_hex(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _HEX_COLOR.match(v):
            raise ValueError("color debe ser hexadecimal #RRGGBB.")
        return v

    @model_validator(mode="after")
    def _any_field(self):
        if (
            self.name is None
            and self.color is None
            and self.sort_order is None
            and self.category_id is None
            and self.is_exclusive_combination is None
        ):
            raise ValueError("Debes enviar al menos un campo para actualizar.")
        return self


class ScenarioTagAssignRequest(BaseModel):
    """Asigna una etiqueta a un escenario. `force=True` evita el 409 por conflicto."""

    tag_id: int
    force: bool = False


class ScenarioTagConflictDetail(BaseModel):
    """Conflicto detectado al intentar asignar una etiqueta."""

    scenario_id: int
    scenario_name: str
    # Tag en conflicto (el que se quitaría al forzar). Puede ser el mismo que se
    # intenta asignar (para exclusividad combinatoria) o uno distinto (para max=1).
    conflicting_tag_id: int
    conflicting_tag_name: str
    reason: str  # "exclusive_combination" | "max_one_per_scenario"


class ScenarioCreate(BaseModel):
    """Payload de creación de escenario."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    edit_policy: EditPolicy = "OWNER_ONLY"
    is_template: bool = False
    tag_ids: list[int] = Field(default_factory=list)
    simulation_type: SimulationType = "NATIONAL"


class ScenarioClone(BaseModel):
    """Payload para clonar un escenario existente."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    edit_policy: EditPolicy = "OWNER_ONLY"


class ScenarioUpdate(BaseModel):
    """Payload de actualización de metadatos de escenario.

    `tag_ids` (si se envía) reemplaza el conjunto completo de etiquetas del
    escenario. Para asignar/quitar una sola etiqueta sin riesgo de conflicto,
    usar los endpoints `/scenarios/{id}/tags` y `/scenarios/{id}/tags/{tag_id}`.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    edit_policy: EditPolicy | None = None
    tag_ids: list[int] | None = None
    simulation_type: SimulationType | None = None


class ScenarioAccessPublic(BaseModel):
    """Permisos efectivos del usuario autenticado sobre el escenario."""

    can_view: bool
    is_owner: bool
    can_edit_direct: bool
    can_propose: bool
    can_manage_values: bool


class ScenarioPublic(BaseModel):
    """Representación pública de escenario."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    owner: str
    base_scenario_id: int | None = None
    base_scenario_name: str | None = None
    changed_param_names: list[str] = Field(default_factory=list)
    edit_policy: str
    simulation_type: SimulationType = "NATIONAL"
    is_template: bool
    created_at: datetime
    # `tag` queda como etiqueta "primaria" (la de menor hierarchy_level, luego por sort_order)
    # para compatibilidad con listados/resultados legacy.
    tag: ScenarioTagPublic | None = None
    tags: list[ScenarioTagPublic] = Field(default_factory=list)
    effective_access: ScenarioAccessPublic | None = None
    # Resumen del reporte de calidad de datos. Solo el dict `summary`
    # (n_bound_conflicts, n_bound_real_conflict, n_bound_numeric_precision,
    # n_year_exclusions). El detalle completo se obtiene vía
    # GET /scenarios/{id}/data-quality.
    data_quality_summary: dict | None = None


class ScenarioDeleteChildPublic(BaseModel):
    """Escenario hijo que bloquea la eliminación de su padre."""

    id: int
    name: str
    owner: str
    edit_policy: str
    simulation_type: SimulationType
    child_count: int = 0
    simulation_job_count: int = 0
    created_at: datetime


class ScenarioDeleteImpact(BaseModel):
    """Impacto previo de eliminar un escenario."""

    scenario_id: int
    scenario_name: str
    direct_children: list[ScenarioDeleteChildPublic] = Field(default_factory=list)


class ScenarioDetachChildrenRequest(BaseModel):
    """Hijos directos que se independizan del escenario padre."""

    child_ids: list[int] = Field(min_length=1)


class ScenarioDetachChildrenResponse(BaseModel):
    detached_child_ids: list[int] = Field(default_factory=list)


class ScenarioPermissionCreate(BaseModel):
    """Crea/actualiza permisos de un usuario sobre un escenario."""

    user_id: uuid.UUID | None = None
    user_identifier: str | None = Field(
        default=None,
        description="Opcional. Si no se envía y viene `user_id`, se usa `user:<uuid>`.",
    )
    can_edit_direct: bool = False
    can_propose: bool = False
    can_manage_values: bool = False

    @model_validator(mode="after")
    def _validate_user_ref(self):
        if self.user_id is None and not (self.user_identifier and self.user_identifier.strip()):
            raise ValueError("Debes enviar `user_identifier` o `user_id`.")
        return self


class ScenarioPermissionPublic(BaseModel):
    """Representación pública de permiso por escenario."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    id_scenario: int
    user_identifier: str
    user_id: uuid.UUID | None
    can_edit_direct: bool
    can_propose: bool
    can_manage_values: bool


class ScenarioExcelImportResponse(BaseModel):
    """Resultado de crear un escenario e importar un Excel a ese escenario."""

    scenario: ScenarioPublic
    import_result: OfficialImportResult


class ScenarioExcelUpdateResponse(BaseModel):
    """Resultado de actualizar un escenario existente desde un Excel SAND."""

    updated: int
    inserted: int = 0
    skipped: int = 0
    not_found: int = 0
    total_rows_read: int
    warnings: list[str]


class SandContribution(BaseModel):
    """Resumen de aportes de un archivo SAND en la integración."""

    archivo: str
    total_cambios: int
    n_nuevas: int
    n_eliminadas: int
    n_modificadas: int
    parametros: list[str]
    tecnologias: list[str]
    fuels: list[str]


class SandExportVerificationPerFile(BaseModel):
    """Conteos de doble verificación del Excel exportado por archivo nuevo."""

    archivo: str
    ok: bool
    n_verificadas_nuevas: int
    n_verificadas_modif: int
    n_omitidas_drop: int
    n_faltantes: int


class SandExportVerification(BaseModel):
    """Doble verificación: releer el integrado exportado vs cambios esperados por archivo."""

    ok: bool
    applies_to_download: bool
    verification_error: str | None = None
    total_nuevas_verificadas: int = 0
    total_modificadas_verificadas: int = 0
    total_omitidas_drop: int = 0
    total_faltantes: int = 0
    per_file: list[SandExportVerificationPerFile] = []
    faltantes_muestra: list[dict[str, Any]] = []


class VerifySandIntegrationResponse(BaseModel):
    """Resultado de verificación manual: base + nuevos + integrado (sin ejecutar integración)."""

    standalone: bool = True
    export_verification: SandExportVerification


class SandIntegrationResponse(BaseModel):
    """Resumen de resultado de la integración de múltiples archivos SAND."""

    total_filas: int
    contribuciones: list[SandContribution]
    conflictos_count: int
    conflictos: list[dict[str, Any]] = []
    resumen: str
    warnings: list[str]
    errors: list[str] = []
    has_log: bool = False
    log_line_count: int = 0
    has_cambios_xlsx: bool = False
    has_conflictos_xlsx: bool = False
    integration_failed: bool = False
    export_verification: SandExportVerification | None = None


class ExcelUpdatePreviewRow(BaseModel):
    """Una fila del preview: puede ser actualización o inserción."""

    preview_id: str
    action: Literal["update", "insert"] = "update"
    row_id: int | None = None
    param_name: str
    region_name: str | None = None
    technology_name: str | None = None
    fuel_name: str | None = None
    emission_name: str | None = None
    timeslice_code: str | None = None
    mode_of_operation_code: str | None = None
    season_code: str | None = None
    daytype_code: str | None = None
    dailytimebracket_code: str | None = None
    storage_set_code: str | None = None
    udc_set_code: str | None = None
    year: int | None = None
    old_value: float | None = None
    new_value: float


class ScenarioExcelPreviewResponse(BaseModel):
    """Resultado del preview de actualización desde Excel."""

    changes: list[ExcelUpdatePreviewRow]
    not_found: int
    total_rows_read: int
    warnings: list[str]


class ExcelChangeToApply(BaseModel):
    """Un cambio confirmado por el usuario para aplicar."""

    preview_id: str
    action: Literal["update", "insert"] = "update"
    row_id: int | None = None
    param_name: str | None = None
    region_name: str | None = None
    technology_name: str | None = None
    fuel_name: str | None = None
    emission_name: str | None = None
    timeslice_code: str | None = None
    mode_of_operation_code: str | None = None
    season_code: str | None = None
    daytype_code: str | None = None
    dailytimebracket_code: str | None = None
    storage_set_code: str | None = None
    udc_set_code: str | None = None
    year: int | None = None
    new_value: float


class ApplyExcelChangesRequest(BaseModel):
    """Payload para aplicar cambios confirmados tras preview."""

    changes: list[ExcelChangeToApply]


class ScenarioOsemosysValueCreate(BaseModel):
    """Crea un valor específico en `osemosys_param_value` para un escenario."""

    param_name: str = Field(min_length=1, max_length=128)
    region_name: str | None = None
    technology_name: str | None = None
    fuel_name: str | None = None
    emission_name: str | None = None
    solver_name: str | None = None
    udc_name: str | None = Field(
        default=None,
        description="Nombre del UDC (code en catálogo `udc_set`) para dimensionar id_udc_set.",
    )
    year: int | None = Field(default=None, ge=0, le=3000)
    value: float


class ScenarioOsemosysValueUpdate(BaseModel):
    """Actualiza dimensiones/valor de una fila en `osemosys_param_value`."""

    param_name: str = Field(min_length=1, max_length=128)
    region_name: str | None = None
    technology_name: str | None = None
    fuel_name: str | None = None
    emission_name: str | None = None
    solver_name: str | None = None
    udc_name: str | None = Field(
        default=None,
        description="Nombre del UDC (code en catálogo `udc_set`) para dimensionar id_udc_set.",
    )
    year: int | None = Field(default=None, ge=0, le=3000)
    value: float


class ScenarioOsemosysValuePublic(BaseModel):
    """Representación pública detallada de `osemosys_param_value`."""

    id: int
    id_scenario: int
    param_name: str
    region_name: str | None = None
    technology_name: str | None = None
    fuel_name: str | None = None
    emission_name: str | None = None
    udc_name: str | None = None
    year: int | None = None
    value: float


class OsemosysValuesPage(BaseModel):
    """Respuesta paginada de valores OSeMOSYS."""

    items: list[ScenarioOsemosysValuePublic]
    total: int
    offset: int
    limit: int


class OsemosysWideCell(BaseModel):
    """Celda pivotada: id de la fila en `osemosys_param_value` y su valor."""

    id: int
    value: float


class OsemosysWideRow(BaseModel):
    """Fila pivotada: combinación de dimensiones + mapa año->celda.

    La clave `cells` usa `"scalar"` para filas con `year IS NULL` y la
    representación string del año en otro caso (ej. `"2025"`).
    """

    group_key: str
    param_name: str
    region_name: str | None = None
    technology_name: str | None = None
    fuel_name: str | None = None
    emission_name: str | None = None
    udc_name: str | None = None
    cells: dict[str, OsemosysWideCell]


class OsemosysValuesWidePage(BaseModel):
    """Respuesta paginada (sobre grupos) en formato wide."""

    items: list[OsemosysWideRow]
    total: int
    offset: int
    limit: int
    years: list[int]
    has_scalar: bool


class OsemosysWideFacets(BaseModel):
    """Valores únicos por columna para el popover de filtros (narrowed)."""

    param_names: list[str]
    region_names: list[str]
    technology_names: list[str]
    fuel_names: list[str]
    emission_names: list[str]
    udc_names: list[str]


class OsemosysParamAuditEntryPublic(BaseModel):
    """Evento de auditoría sobre `osemosys_param_value`."""

    id: int
    param_name: str
    id_osemosys_param_value: int | None = None
    action: str
    old_value: float | None = None
    new_value: float | None = None
    dimensions_json: dict | list | None = None
    source: str
    changed_by: str
    created_at: datetime


class OsemosysParamAuditPage(BaseModel):
    """Respuesta paginada de historial de cambios por parámetro."""

    items: list[OsemosysParamAuditEntryPublic]
    total: int
    offset: int
    limit: int


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Definir contratos de escenarios y permisos granulares.
#
# Posibles mejoras:
# - Introducir enums dedicados para políticas/estados de permisos.
#
# Riesgos en producción:
# - Cambios en `EditPolicy` impactan reglas de negocio y frontend.
#
# Escalabilidad:
# - Validación ligera.
