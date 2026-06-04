"""Catálogo de metadatos de parámetros OSeMOSYS con default en el modelo Pyomo."""

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelParameterCatalog(Base):
    __tablename__ = "model_parameter_catalog"
    __table_args__ = ({"schema": "osemosys"},)

    param_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    pyomo_name: Mapped[str] = mapped_column(String(120), nullable=False)
    index_dims: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="float")
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    requires_storage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_udc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
