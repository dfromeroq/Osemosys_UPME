"""Schemas Pydantic para usuarios y permisos de catálogo."""

import uuid

from pydantic import BaseModel


class UserPublic(BaseModel):
    """Representación pública de usuario autenticado."""

    id: uuid.UUID
    email: str
    username: str
    is_active: bool
    can_manage_catalogs: bool
    can_import_official_data: bool
    can_manage_users: bool
    can_manage_scenarios: bool = False
    is_admin_reports: bool = False
    can_manage_system_settings: bool = False


class UserCreate(BaseModel):
    """Payload para crear usuario desde panel administrativo."""

    email: str
    username: str
    password: str
    is_active: bool = True
    can_manage_catalogs: bool = False
    can_import_official_data: bool = False
    can_manage_users: bool = False
    can_manage_scenarios: bool = False
    is_admin_reports: bool = False
    can_manage_system_settings: bool = False


class UserCatalogPermissionUpdate(BaseModel):
    """Payload para asignar/revocar `can_manage_catalogs`."""

    can_manage_catalogs: bool


class UserOfficialDataImportPermissionUpdate(BaseModel):
    """Payload para asignar/revocar `can_import_official_data`."""

    can_import_official_data: bool


class UserPermissionsUpdate(BaseModel):
    """Payload unificado para asignar/revocar permisos funcionales."""

    is_active: bool
    can_manage_catalogs: bool
    can_import_official_data: bool
    can_manage_users: bool
    can_manage_scenarios: bool = False
    is_admin_reports: bool = False
    can_manage_system_settings: bool = False


class UserPasswordResetPayload(BaseModel):
    """Payload para resetear la contraseña de un usuario (uso admin)."""

    new_password: str


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Exponer DTOs de usuario para perfil y gestión de privilegios globales.
#
# Posibles mejoras:
# - Incluir metadatos de documento y timestamps según necesidad de UI.
#
# Riesgos en producción:
# - Cambios en shape de `UserPublic` pueden romper clientes de autenticación.
#
# Escalabilidad:
# - No aplica.

