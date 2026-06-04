"""Schemas Pydantic para configuración runtime clave-valor."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


HighsMethod = Literal["choose", "simplex", "ipm", "ipx", "hipo"]
OnOffChoose = Literal["off", "on", "choose"]


class SolverSettingsPublic(BaseModel):
    """Vista pública de la configuración del solver expuesta al admin."""

    solver_threads: int = Field(default=0, ge=0, le=512)
    highs_method: HighsMethod = "ipm"
    highs_presolve: OnOffChoose = "on"
    highs_parallel: OnOffChoose = "on"
    highs_hipo_parallel_type: str = ""
    highs_run_crossover: OnOffChoose = "choose"
    highs_use_direct: bool = True
    highs_time_limit: float = Field(default=0.0, ge=0.0)
    highs_ipm_optimality_tolerance: float = Field(default=1e-7, gt=0.0)
    highs_primal_feasibility_tolerance: float = Field(default=1e-7, gt=0.0)
    updated_at: datetime | None = None
    updated_by_username: str | None = None


class SolverSettingsUpdate(BaseModel):
    """Payload para actualizar la configuración del solver desde el admin."""

    solver_threads: int = Field(ge=0, le=512)
    highs_method: HighsMethod = "ipm"
    highs_presolve: OnOffChoose = "on"
    highs_parallel: OnOffChoose = "on"
    highs_hipo_parallel_type: str = ""
    highs_run_crossover: OnOffChoose = "choose"
    highs_use_direct: bool = True
    highs_time_limit: float = Field(default=0.0, ge=0.0)
    highs_ipm_optimality_tolerance: float = Field(default=1e-7, gt=0.0)
    highs_primal_feasibility_tolerance: float = Field(default=1e-7, gt=0.0)
