"""Modelos ORM para el catálogo editable de visualización (schema ``osemosys.catalog_meta_*``)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

SCHEMA = "osemosys"


class CatalogMetaColorPalette(Base):
    __tablename__ = "catalog_meta_color_palette"
    __table_args__ = (
        UniqueConstraint("group", "key", name="uq_color_palette_group_key"),
        Index("ix_color_palette_group", "group"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(9), nullable=False)
    group: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )


class CatalogMetaLabel(Base):
    __tablename__ = "catalog_meta_label"
    __table_args__ = (
        UniqueConstraint("code", name="uq_label_code"),
        Index("ix_label_category", "category"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    label_es: Mapped[str] = mapped_column(String(255), nullable=False)
    label_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )


class CatalogMetaSectorMapping(Base):
    __tablename__ = "catalog_meta_sector_mapping"
    __table_args__ = (
        UniqueConstraint("tech_prefix", name="uq_sector_mapping_prefix"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tech_prefix: Mapped[str] = mapped_column(String(64), nullable=False)
    sector_name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )


class CatalogMetaTechFamily(Base):
    __tablename__ = "catalog_meta_tech_family"
    __table_args__ = (
        UniqueConstraint("family_code", "tech_prefix", name="uq_tech_family_row"),
        Index("ix_tech_family_family", "family_code"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_code: Mapped[str] = mapped_column(String(64), nullable=False)
    tech_prefix: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )


class CatalogMetaFilterGroup(Base):
    __tablename__ = "catalog_meta_filter_group"
    __table_args__ = (
        UniqueConstraint("code", name="uq_filter_group_code"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    filter_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="TECH_ONLY")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )

    members: Mapped[list["CatalogMetaFilterMember"]] = relationship(
        "CatalogMetaFilterMember",
        back_populates="group",
        foreign_keys="CatalogMetaFilterMember.group_id",
        cascade="all, delete-orphan",
    )


class CatalogMetaFilterMember(Base):
    __tablename__ = "catalog_meta_filter_member"
    __table_args__ = (
        Index("ix_filter_member_group", "group_id", "sort_order"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA}.catalog_meta_filter_group.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="CODE")
    operation: Mapped[str] = mapped_column(String(16), nullable=False, default="INCLUDE")
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False, default="TECHNOLOGY")
    match_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="EXACT")
    value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ref_group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA}.catalog_meta_filter_group.id", ondelete="SET NULL"),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )

    group: Mapped["CatalogMetaFilterGroup"] = relationship(
        "CatalogMetaFilterGroup",
        back_populates="members",
        foreign_keys=[group_id],
    )
    ref_group: Mapped["CatalogMetaFilterGroup | None"] = relationship(
        "CatalogMetaFilterGroup",
        foreign_keys=[ref_group_id],
    )


class CatalogMetaChartModule(Base):
    __tablename__ = "catalog_meta_chart_module"
    __table_args__ = (
        UniqueConstraint("code", name="uq_chart_module_code"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )

    submodules: Mapped[list["CatalogMetaChartSubmodule"]] = relationship(
        back_populates="module", cascade="all, delete-orphan"
    )
    charts: Mapped[list["CatalogMetaChartConfig"]] = relationship(
        back_populates="module", foreign_keys="CatalogMetaChartConfig.module_id"
    )


class CatalogMetaChartSubmodule(Base):
    __tablename__ = "catalog_meta_chart_submodule"
    __table_args__ = (
        UniqueConstraint("module_id", "code", name="uq_chart_submodule_code"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA}.catalog_meta_chart_module.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )

    module: Mapped["CatalogMetaChartModule"] = relationship(back_populates="submodules")
    charts: Mapped[list["CatalogMetaChartConfig"]] = relationship(back_populates="submodule")


class CatalogMetaChartConfig(Base):
    __tablename__ = "catalog_meta_chart_config"
    __table_args__ = (
        UniqueConstraint("tipo", name="uq_chart_config_tipo"),
        Index("ix_chart_config_module", "module_id"),
        Index("ix_chart_config_submodule", "submodule_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String(64), nullable=False)
    module_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA}.catalog_meta_chart_module.id", ondelete="RESTRICT"),
        nullable=False,
    )
    submodule_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA}.catalog_meta_chart_submodule.id", ondelete="SET NULL"),
        nullable=True,
    )
    label_titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    label_figura: Mapped[str | None] = mapped_column(String(64), nullable=True)
    variable_default: Mapped[str] = mapped_column(String(128), nullable=False)
    filtro_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="group")
    filtro_group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA}.catalog_meta_filter_group.id", ondelete="SET NULL"),
        nullable=True,
    )
    filtro_params_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    agrupar_por_default: Mapped[str] = mapped_column(String(32), nullable=False, default="TECNOLOGIA")
    agrupaciones_permitidas_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    color_fn_key: Mapped[str] = mapped_column(String(32), nullable=False, default="tecnologias")
    flags_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    msg_sin_datos: Mapped[str | None] = mapped_column(String(512), nullable=True)
    data_explorer_filters_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )

    module: Mapped["CatalogMetaChartModule"] = relationship(
        back_populates="charts", foreign_keys=[module_id]
    )
    submodule: Mapped["CatalogMetaChartSubmodule | None"] = relationship(back_populates="charts")
    filtro_group: Mapped["CatalogMetaFilterGroup | None"] = relationship(
        foreign_keys=[filtro_group_id]
    )
    subfilters: Mapped[list["CatalogMetaChartSubfilter"]] = relationship(
        back_populates="chart", cascade="all, delete-orphan"
    )


class CatalogMetaChartSubfilter(Base):
    __tablename__ = "catalog_meta_chart_subfilter"
    __table_args__ = (
        UniqueConstraint("chart_id", "code", name="uq_chart_subfilter_code"),
        Index("ix_chart_subfilter_chart", "chart_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chart_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA}.catalog_meta_chart_config.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    filter_group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA}.catalog_meta_filter_group.id", ondelete="SET NULL"),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    default_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )

    chart: Mapped["CatalogMetaChartConfig"] = relationship(back_populates="subfilters")
    filter_group: Mapped["CatalogMetaFilterGroup | None"] = relationship(
        foreign_keys=[filter_group_id]
    )


class CatalogMetaChartSubfilterGroup(Base):
    __tablename__ = "catalog_meta_chart_subfilter_group"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chart_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA}.catalog_meta_chart_config.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_label: Mapped[str] = mapped_column(String(128), nullable=False)
    subfilter_codes_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )


class CatalogMetaVariableUnit(Base):
    __tablename__ = "catalog_meta_variable_unit"
    __table_args__ = (
        UniqueConstraint("variable_name", name="uq_variable_unit_name"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variable_name: Mapped[str] = mapped_column(String(128), nullable=False)
    unit_base: Mapped[str] = mapped_column(String(32), nullable=False)
    display_units_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )


class CatalogMetaAudit(Base):
    __tablename__ = "catalog_meta_audit"
    __table_args__ = (
        Index("ix_catalog_meta_audit_table", "table_name", "row_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(64), nullable=False)
    row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    diff_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.user.id", ondelete="SET NULL"),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
