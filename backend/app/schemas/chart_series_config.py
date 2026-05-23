"""Esquemas Pydantic para configuración global de series de gráficas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChartSeriesConfigPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    agrupar_por: str
    series_code: str
    display_name: str
    color: str | None = None
    hidden: bool = False
    is_global: bool = False
    sort_index: int = 0
    group_key: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ChartSeriesConfigCreate(BaseModel):
    tipo: str = Field(..., min_length=1, max_length=64)
    agrupar_por: str | None = Field(None, max_length=32)
    series_code: str = Field(..., min_length=1, max_length=512)
    display_name: str | None = Field(None, max_length=512)
    color: str | None = Field(None, max_length=32)
    hidden: bool = False
    is_global: bool = False
    sort_index: int | None = None
    group_key: str | None = Field(None, max_length=255)
    notes: str | None = None


class ChartSeriesConfigUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=512)
    color: str | None = Field(None, max_length=32)
    hidden: bool | None = None
    is_global: bool | None = None
    sort_index: int | None = None
    group_key: str | None = Field(None, max_length=255)


class ChartSeriesPopulateBody(BaseModel):
    tipo: str = Field(..., min_length=1, max_length=64)
    agrupar_por: str | None = None
    variable: str | None = Field(None, max_length=64)


class ChartSeriesReorderBody(BaseModel):
    ids: list[int] = Field(..., min_length=1)


class ChartTypeInfoPublic(BaseModel):
    tipo: str
    agrupar_por_default: str
    source: str
