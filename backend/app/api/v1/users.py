"""Endpoints de usuario y permisos administrativos.

Incluye consulta de perfil autenticado y operación privilegiada para delegar
capacidad de gestión de catálogos.
"""

import uuid

from fastapi import APIRouter, Depends
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_catalog_manager, get_current_user, get_user_manager
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.models import User
from app.schemas.user import (
    UserCreate,
    UserCatalogPermissionUpdate,
    UserOfficialDataImportPermissionUpdate,
    UserPasswordResetPayload,
    UserPermissionsUpdate,
    UserPublic,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users")


@router.get("/me", response_model=UserPublic)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    """Retorna el usuario autenticado actual.

    Método HTTP:
        - `GET` por ser lectura de identidad.

    Respuestas:
        - 200: perfil del usuario autenticado.
        - 401: token inválido/no autenticado.
    """
    return current_user


@router.get("", response_model=list[UserPublic])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_user_manager),
) -> list[User]:
    """Lista usuarios para panel de administración."""
    return UserService.list_users(db)


@router.post("", response_model=UserPublic, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_user_manager),
) -> User:
    """Crea usuario y permisos iniciales desde panel administrativo."""
    try:
        return UserService.create_user(
            db,
            email=payload.email,
            username=payload.username,
            password=payload.password,
            is_active=payload.is_active,
            can_manage_catalogs=payload.can_manage_catalogs,
            can_import_official_data=payload.can_import_official_data,
            can_manage_users=payload.can_manage_users,
            can_manage_scenarios=payload.can_manage_scenarios,
            is_admin_reports=payload.is_admin_reports,
            can_manage_system_settings=payload.can_manage_system_settings,
        )
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.patch("/{user_id}/catalog-manager", response_model=UserPublic)
def set_catalog_manager(
    user_id: uuid.UUID,
    payload: UserCatalogPermissionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_catalog_manager),
) -> User:
    """Asigna o revoca permiso de gestión de catálogos a un usuario.

    Método HTTP:
        - `PATCH` porque actualiza parcialmente un atributo de autorización.

    Validaciones:
        - usuario objetivo debe existir;
        - caller debe cumplir `get_catalog_manager`.

    Respuestas:
        - 200: actualización aplicada.
        - 404: usuario no encontrado.
        - 403: caller sin privilegio administrativo.
    """
    try:
        return UserService.set_catalog_manager(
            db=db,
            user_id=user_id,
            can_manage_catalogs=payload.can_manage_catalogs,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.patch("/{user_id}/official-data-importer", response_model=UserPublic)
def set_official_data_importer(
    user_id: uuid.UUID,
    payload: UserOfficialDataImportPermissionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_catalog_manager),
) -> User:
    """Asigna o revoca permiso de importación de datos oficiales a un usuario."""
    try:
        return UserService.set_official_data_importer(
            db=db,
            user_id=user_id,
            can_import_official_data=payload.can_import_official_data,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.patch("/{user_id}/permissions", response_model=UserPublic)
def set_permissions(
    user_id: uuid.UUID,
    payload: UserPermissionsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_user_manager),
) -> User:
    """Actualiza todos los permisos funcionales en una sola operación."""
    try:
        return UserService.set_permissions(
            db=db,
            user_id=user_id,
            is_active=payload.is_active,
            can_manage_catalogs=payload.can_manage_catalogs,
            can_import_official_data=payload.can_import_official_data,
            can_manage_users=payload.can_manage_users,
            can_manage_scenarios=payload.can_manage_scenarios,
            is_admin_reports=payload.is_admin_reports,
            can_manage_system_settings=payload.can_manage_system_settings,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/{user_id}/reset-password", response_model=UserPublic)
def reset_user_password(
    user_id: uuid.UUID,
    payload: UserPasswordResetPayload,
    db: Session = Depends(get_db),
    _: User = Depends(get_user_manager),
) -> User:
    """Restablece la contraseña de un usuario (uso administrativo)."""
    try:
        return UserService.reset_password(
            db=db, user_id=user_id, new_password=payload.new_password
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Exponer identidad autenticada y delegación de permisos de catálogo.
#
# Posibles mejoras:
# - Reemplazar control binario por rol granular (RBAC completo).
# - Registrar auditoría explícita de cambios de permisos.
#
# Riesgos en producción:
# - Escalada de privilegios si dependencia de autorización es omitida accidentalmente.
#
# Escalabilidad:
# - Carga baja; operaciones mayormente I/O-bound en BD.

