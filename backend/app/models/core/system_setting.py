"""Modelo ORM para configuración runtime clave-valor (schema `core`)."""

import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemSetting(Base):
    """Pareja clave-valor de configuración global mutable en runtime.

    Permite que un administrador modifique parámetros del despliegue (e.g.
    `solver.threads`) desde la UI sin reiniciar el contenedor. El valor se
    almacena como texto y se interpreta por el lector según la clave.
    """

    __tablename__ = "system_setting"
    __table_args__ = ({"schema": "core"},)

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )
