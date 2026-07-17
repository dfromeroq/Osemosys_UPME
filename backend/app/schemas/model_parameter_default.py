"""Schemas para defaults versionados del modelo OSeMOSYS."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ModelDefaultItemInput(BaseModel):
    param_key: str
    value: float


class ModelDefaultVersionCreate(BaseModel):
    items: list[ModelDefaultItemInput]
    comment: str | None = Field(default=None, max_length=2000)


class ModelDefaultCatalogRowPublic(BaseModel):
    param_key: str
    pyomo_name: str
    index_dims: str
    category: str
    description: str | None
    value_type: str
    min_value: float | None
    max_value: float | None
    requires_storage: bool
    requires_udc: bool
    value: float


class ModelDefaultCatalogResponse(BaseModel):
    version_id: int
    is_active: bool
    rows: list[ModelDefaultCatalogRowPublic]


class ModelDefaultVersionSummaryPublic(BaseModel):
    id: int
    created_at: datetime
    created_by_username: str | None
    comment: str | None
    is_active: bool


class ModelDefaultVersionListResponse(BaseModel):
    active_version_id: int
    versions: list[ModelDefaultVersionSummaryPublic]


class ModelDefaultVersionDetailPublic(BaseModel):
    id: int
    created_at: datetime
    created_by_username: str | None
    comment: str | None
    is_active: bool
    items: list[ModelDefaultCatalogRowPublic]


class ModelDefaultVersionCreateResponse(BaseModel):
    version_id: int
    active_version_id: int
