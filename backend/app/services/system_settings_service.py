"""Servicio para configuración runtime clave-valor.

La tabla `core.system_setting` permite que un administrador modifique parámetros
del despliegue desde la UI sin reiniciar el contenedor. El valor se guarda como
texto y se interpreta por el lector según la clave (`get_int`, `get_str`, …).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SystemSetting

# --- Claves conocidas ----------------------------------------------------
#: Hilos que se entregan al solver multihilo (HiGHS, Gurobi). 0 = no aplicar
#: (cada solver usa su default). Se persiste como texto.
SOLVER_THREADS_KEY = "solver.threads"


class SystemSettingsService:
    """Lectura/escritura de la tabla `core.system_setting`."""

    @staticmethod
    def get_raw(db: Session, key: str) -> SystemSetting | None:
        return db.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        ).scalar_one_or_none()

    @staticmethod
    def get_int(db: Session, key: str, default: int = 0) -> int:
        row = SystemSettingsService.get_raw(db, key)
        if row is None or row.value is None:
            return default
        try:
            return int(str(row.value).strip())
        except (TypeError, ValueError):
            return default

    @staticmethod
    def set_value(
        db: Session,
        *,
        key: str,
        value: Any,
        updated_by: uuid.UUID | None,
    ) -> SystemSetting:
        row = SystemSettingsService.get_raw(db, key)
        text_value = None if value is None else str(value)
        if row is None:
            row = SystemSetting(key=key, value=text_value, updated_by=updated_by)
            db.add(row)
        else:
            row.value = text_value
            row.updated_by = updated_by
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def get_solver_threads(db: Session, *, fallback: int = 0) -> int:
        """Hilos a aplicar al solver. Si no hay registro, usa `fallback`.

        El fallback típico es ``settings.sim_solver_threads`` (env var del
        despliegue) — así el flujo legado sigue funcionando si no se ha tocado
        la BD aún.
        """
        return SystemSettingsService.get_int(
            db, SOLVER_THREADS_KEY, default=fallback
        )
