"""Esquemas Pydantic para plantillas globales de tablas de resultados."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResultTableColumnRulePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_key: str
    hidden: bool = False
    sort_order: int | None = None


class ResultTableColumnRuleCreate(BaseModel):
    category_key: str = Field(..., min_length=1, max_length=64)
    hidden: bool = False
    sort_order: int | None = None


class ResultTableTemplatePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    seed_key: str | None = None
    display_title: str | None
    sort_order: int
    is_enabled: bool

    tipo: str
    un: str
    sub_filtro: str | None
    loc: str | None
    variable: str | None
    agrupar_por: str | None
    region: str | None
    timeslice: str | None

    table_period_years: int | None
    table_cumulative: bool | None
    custom_series_order: list[str] | None
    y_axis_min: float | None
    y_axis_max: float | None

    column_rules: list[ResultTableColumnRulePublic] = Field(default_factory=list)

    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ResultTableTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    display_title: str | None = Field(None, max_length=255)
    sort_order: int = 0
    is_enabled: bool = True

    tipo: str = Field(..., min_length=1, max_length=64)
    un: str = Field(..., min_length=1, max_length=16)
    sub_filtro: str | None = Field(None, max_length=64)
    loc: str | None = Field(None, max_length=32)
    variable: str | None = Field(None, max_length=64)
    agrupar_por: str | None = Field(None, max_length=32)
    region: str | None = Field(None, max_length=16)
    timeslice: str | None = Field(None, max_length=32)

    table_period_years: int | None = None
    table_cumulative: bool | None = None
    custom_series_order: list[str] | None = None
    y_axis_min: float | None = None
    y_axis_max: float | None = None

    column_rules: list[ResultTableColumnRuleCreate] = Field(default_factory=list)


class ResultTableTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    display_title: str | None = Field(None, max_length=255)
    sort_order: int | None = None
    is_enabled: bool | None = None

    tipo: str | None = Field(None, min_length=1, max_length=64)
    un: str | None = Field(None, min_length=1, max_length=16)
    sub_filtro: str | None = None
    loc: str | None = None
    variable: str | None = None
    agrupar_por: str | None = None
    region: str | None = None
    timeslice: str | None = None

    table_period_years: int | None = None
    table_cumulative: bool | None = None
    custom_series_order: list[str] | None = None
    y_axis_min: float | None = None
    y_axis_max: float | None = None

    column_rules: list[ResultTableColumnRuleCreate] | None = None


class ResultTablePresentationSeriesOptionPublic(BaseModel):
    value: str = Field(..., description="Texto que debe coincidir con ChartSeries.name")
    code: str | None = Field(None, description="Código catálogo si aplica")


class ResultTablePresentationOptionsPublic(BaseModel):
    series_options: list[ResultTablePresentationSeriesOptionPublic]
    category_keys: list[str]
    agrupar_por_resolved: str


class ResultTableReorderBody(BaseModel):
    ids: list[int] = Field(..., min_length=1)
