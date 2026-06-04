"""Schemas Pydantic para configuración runtime clave-valor."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SolverSettingsPublic(BaseModel):
    """Vista pública de la configuración del solver expuesta al admin."""

    #: Hilos pedidos en admin/env. 0 = usar todos los CPUs disponibles del worker.
    solver_threads: int = Field(default=0, ge=0, le=512)
    #: CPUs visibles para el proceso del worker (affinity o cpu_count).
    hardware_thread_limit: int = Field(default=1, ge=1)
    #: Hilos que HiGHS aplicaría con la config actual (cap por hardware).
    effective_threads_preview: int = Field(default=1, ge=1)
    updated_at: datetime | None = None
    updated_by_username: str | None = None


class SolverSettingsUpdate(BaseModel):
    """Payload para actualizar la configuración del solver desde el admin."""

    solver_threads: int = Field(ge=0, le=512)
