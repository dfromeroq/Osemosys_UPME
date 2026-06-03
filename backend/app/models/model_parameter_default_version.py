"""Versión inmutable de valores default del modelo OSeMOSYS."""

import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ModelParameterDefaultVersion(Base):
    __tablename__ = "model_parameter_default_version"
    __table_args__ = ({"schema": "osemosys"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["ModelParameterDefaultItem"]] = relationship(
        "ModelParameterDefaultItem",
        back_populates="version",
        cascade="all, delete-orphan",
    )


class ModelParameterDefaultItem(Base):
    __tablename__ = "model_parameter_default_item"
    __table_args__ = (
        {"schema": "osemosys"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("osemosys.model_parameter_default_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    param_key: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("osemosys.model_parameter_catalog.param_key", ondelete="RESTRICT"),
        nullable=False,
    )
    value: Mapped[float] = mapped_column(nullable=False)

    version: Mapped[ModelParameterDefaultVersion] = relationship(
        "ModelParameterDefaultVersion",
        back_populates="items",
    )
