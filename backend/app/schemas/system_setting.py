"""Schemas Pydantic para configuración runtime clave-valor."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SolverSettingsPublic(BaseModel):
    """Vista pública de la configuración del solver expuesta al admin."""

    #: Hilos a configurar en el solver. 0 = no aplicar (cada solver usa su default).
    solver_threads: int = Field(default=0, ge=0, le=512)
    updated_at: datetime | None = None
    updated_by_username: str | None = None


class SolverSettingsUpdate(BaseModel):
    """Payload para actualizar la configuración del solver desde el admin."""

    solver_threads: int = Field(ge=0, le=512)
