"""Schemas para operaciones asíncronas de escenarios."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ScenarioOperationType = Literal["CLONE_SCENARIO", "APPLY_EXCEL_CHANGES", "DELETE_SCENARIO"]
ScenarioOperationStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]


class ScenarioCloneAsyncCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    edit_policy: Literal["OWNER_ONLY", "OPEN", "RESTRICTED"] = "OWNER_ONLY"


class ScenarioApplyExcelChangesAsyncCreate(BaseModel):
    changes: list[dict[str, float | int]]


class ScenarioOperationJobPublic(BaseModel):
    id: int
    operation_type: ScenarioOperationType
    status: ScenarioOperationStatus
    user_id: str
    username: str | None = None
    scenario_id: int | None = None
    scenario_name: str | None = None
    target_scenario_id: int | None = None
    target_scenario_name: str | None = None
    progress: float
    stage: str | None = None
    message: str | None = None
    result_json: dict | None = None
    error_message: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ScenarioOperationLogPublic(BaseModel):
    id: int
    event_type: str
    stage: str | None
    message: str | None
    progress: float | None
    created_at: datetime
