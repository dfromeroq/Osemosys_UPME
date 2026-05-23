"""Dependencias de inyección para la capa API.

Concentra componentes reutilizables de autenticación y autorización:
  - get_current_user: valida JWT y retorna usuario activo (401 si inválido).
  - get_catalog_manager: requiere can_manage_catalogs (403 si no).
  - get_official_data_import_manager: requiere can_import_official_data.
  - get_user_manager: requiere can_manage_users.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.security import ALGORITHM
from app.core.config import get_settings
from app.db.session import get_db
from app.models import User
from app.core.exceptions import NotFoundError
from app.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    """Obtiene el usuario autenticado desde un JWT Bearer.

    `sub` del token representa el `user_id` (UUID). Si el token no es válido,
    el usuario no existe o está inactivo, responde 401 con `WWW-Authenticate`.

    Seguridad:
        - No diferencia entre token inválido y usuario inexistente para reducir
          filtración de información sobre cuentas.
        - El uso de `OAuth2PasswordBearer` estandariza extracción del bearer token.
    """
    settings = get_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        subject: str | None = payload.get("sub")
        if subject is None:
            raise credentials_exception
        user_id = uuid.UUID(subject)
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    try:
        return UserService.get_active_by_id(db, user_id=user_id)
    except NotFoundError:
        raise credentials_exception


def get_catalog_manager(current_user: User = Depends(get_current_user)) -> User:
    """Autoriza operaciones sensibles de gestión de catálogos.

    Esta dependencia aplica control RBAC simple basado en `can_manage_catalogs`.
    Debe usarse en endpoints mutables de catálogos para evitar modificaciones no
    autorizadas de insumos de modelado.
    """
    if not current_user.can_manage_catalogs:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para gestionar catálogos.",
        )
    return current_user


def get_official_data_import_manager(current_user: User = Depends(get_current_user)) -> User:
    """Autoriza la carga de datos oficiales desde archivo XLSM."""
    if not current_user.can_import_official_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para importar datos oficiales.",
        )
    return current_user


def get_user_manager(current_user: User = Depends(get_current_user)) -> User:
    """Autoriza administración centralizada de usuarios y permisos."""
    if not current_user.can_manage_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para administrar usuarios.",
        )
    return current_user


def get_system_settings_manager(current_user: User = Depends(get_current_user)) -> User:
    """Autoriza la administración de configuración runtime del sistema."""
    if not current_user.can_manage_system_settings:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para administrar la configuración del sistema.",
        )
    return current_user


def get_scenario_manager(current_user: User = Depends(get_current_user)) -> User:
    """Autoriza administración integral de escenarios ajenos.

    Concede ver escenarios privados (OWNER_ONLY ajenos), editar metadatos,
    política, etiquetas y valores; administrar permisos granulares; clonar,
    exportar, revisar change requests y eliminar escenarios/simulaciones.
    """
    if not current_user.can_manage_scenarios:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para administrar escenarios ajenos.",
        )
    return current_user


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Centralizar autenticación por JWT y autorizaciones comunes para endpoints.
#
# Posibles mejoras:
# - Añadir scopes/roles más granulares para separar permisos por dominio.
# - Implementar caché de usuario activo para reducir round-trips a BD.
#
# Riesgos en producción:
# - Dependencia estricta del claim `sub`; cambios de contrato JWT romperían auth.
# - Si `secret_key` rota sin estrategia de transición, se invalidan sesiones activas.
#
# Escalabilidad:
# - Escala horizontalmente con API; el costo principal es lookup de usuario en BD.

