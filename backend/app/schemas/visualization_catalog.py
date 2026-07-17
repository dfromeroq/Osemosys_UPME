"""Schemas para administración del catálogo de visualización."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Filter groups ────────────────────────────────────────────────────────────


class FilterMemberPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_kind: str
    operation: str
    entity_type: str
    match_mode: str
    value: str | None
    ref_group_id: int | None
    sort_order: int


class FilterGroupPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None
    filter_mode: str
    is_system: bool
    members: list[FilterMemberPublic] = Field(default_factory=list)


class FilterMemberCreate(BaseModel):
    member_kind: str = "CODE"
    operation: str = "INCLUDE"
    entity_type: str = "TECHNOLOGY"
    match_mode: str = "EXACT"
    value: str | None = None
    ref_group_id: int | None = None
    sort_order: int = 0


class FilterGroupCreate(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    filter_mode: str = "TECH_ONLY"
    members: list[FilterMemberCreate] = Field(default_factory=list)


class FilterGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    filter_mode: str | None = None


class FilterMembersReplace(BaseModel):
    members: list[FilterMemberCreate] = Field(default_factory=list)


class FilterMembersImport(BaseModel):
    text: str = Field(min_length=1)
    mode: Literal["merge", "replace"] = "merge"


# ── Labels ───────────────────────────────────────────────────────────────────


class LabelPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    label_es: str
    label_en: str | None
    category: str | None


class LabelPagePublic(BaseModel):
    items: list[LabelPublic]
    total: int
    page: int
    page_size: int


class LabelCreate(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    label_es: str = Field(min_length=1, max_length=255)
    label_en: str | None = None
    category: str | None = None


class LabelUpdate(BaseModel):
    label_es: str | None = None
    label_en: str | None = None
    category: str | None = None


# ── Colors ───────────────────────────────────────────────────────────────────


class ColorPalettePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group: str
    key: str
    color_hex: str
    sort_order: int = 0


class ColorPaletteCreate(BaseModel):
    group: str = Field(min_length=1, max_length=32)
    key: str = Field(min_length=1, max_length=128)
    color_hex: str = Field(min_length=4, max_length=9)
    sort_order: int = 0


class ColorPaletteUpdate(BaseModel):
    group: str | None = None
    key: str | None = None
    color_hex: str | None = None
    sort_order: int | None = None


# ── Chart configs ────────────────────────────────────────────────────────────


class ChartSubfilterPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    display_label: str | None
    group_label: str | None
    filter_group_id: int | None
    sort_order: int
    default_selected: bool


class ChartSubfilterCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    display_label: str | None = None
    group_label: str | None = None
    filter_group_id: int | None = None
    sort_order: int = 0
    default_selected: bool = False


class ChartConfigPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    label_titulo: str
    variable_default: str
    agrupar_por_default: str
    color_fn_key: str
    filtro_kind: str
    is_visible: bool


class ChartConfigDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    module_id: int
    submodule_id: int | None
    label_titulo: str
    label_figura: str | None
    variable_default: str
    filtro_kind: str
    filtro_group_id: int | None
    filtro_params_json: dict[str, Any] | None
    agrupar_por_default: str
    agrupaciones_permitidas_json: list[str] | None
    color_fn_key: str
    flags_json: dict[str, Any] | None
    msg_sin_datos: str | None
    data_explorer_filters_json: dict[str, Any] | None
    is_visible: bool
    sort_order: int
    subfilters: list[ChartSubfilterPublic] = Field(default_factory=list)


class ChartConfigCreate(BaseModel):
    tipo: str = Field(min_length=1, max_length=64)
    module_id: int
    submodule_id: int | None = None
    label_titulo: str = Field(min_length=1, max_length=255)
    label_figura: str | None = None
    variable_default: str = Field(min_length=1, max_length=128)
    filtro_kind: str = "group"
    filtro_group_id: int | None = None
    filtro_params_json: dict[str, Any] | None = None
    agrupar_por_default: str = "TECNOLOGIA"
    agrupaciones_permitidas_json: list[str] | None = None
    color_fn_key: str = "tecnologias"
    flags_json: dict[str, Any] | None = None
    msg_sin_datos: str | None = None
    data_explorer_filters_json: dict[str, Any] | None = None
    is_visible: bool = True
    sort_order: int = 0
    subfilters: list[ChartSubfilterCreate] = Field(default_factory=list)


class ChartConfigUpdate(BaseModel):
    module_id: int | None = None
    submodule_id: int | None = None
    label_titulo: str | None = None
    label_figura: str | None = None
    variable_default: str | None = None
    filtro_kind: str | None = None
    filtro_group_id: int | None = None
    filtro_params_json: dict[str, Any] | None = None
    agrupar_por_default: str | None = None
    agrupaciones_permitidas_json: list[str] | None = None
    color_fn_key: str | None = None
    flags_json: dict[str, Any] | None = None
    msg_sin_datos: str | None = None
    data_explorer_filters_json: dict[str, Any] | None = None
    is_visible: bool | None = None
    sort_order: int | None = None
    subfilters: list[ChartSubfilterCreate] | None = None


# ── Menu (read-only) ─────────────────────────────────────────────────────────


class MenuChartPublic(BaseModel):
    tipo: str
    label: str
    allowed: list[str] | None = None
    default_grouping: str | None = None
    is_capacity: bool = False
    soporta_pareto: bool = False
    has_loc: bool = False
    sub_filtros: list[str] | None = None
    sub_label: str | None = None


class MenuSubmodulePublic(BaseModel):
    code: str
    label: str
    charts: list[MenuChartPublic] = Field(default_factory=list)


class MenuModulePublic(BaseModel):
    code: str
    label: str
    icon: str | None = None
    charts: list[MenuChartPublic] | None = None
    subs: list[MenuSubmodulePublic] | None = None


class ResolvedFilterGroupPublic(BaseModel):
    code: str
    technology_codes: list[str]
    fuel_codes: list[str]


# ── Form options ─────────────────────────────────────────────────────────────


class FormOptionItem(BaseModel):
    value: str
    label: str


class ModuleOptionPublic(BaseModel):
    id: int
    code: str
    label: str


class SubmoduleOptionPublic(BaseModel):
    id: int
    module_id: int
    code: str
    label: str


class CatalogFormOptionsPublic(BaseModel):
    grouping_axes: list[FormOptionItem]
    color_fn_keys: list[str]
    filtro_kinds: list[str]
    filter_modes: list[str]
    member_operations: list[str]
    entity_types: list[str]
    color_groups: list[str]
    label_categories: list[str]
    modules: list[ModuleOptionPublic]
    submodules: list[SubmoduleOptionPublic]
