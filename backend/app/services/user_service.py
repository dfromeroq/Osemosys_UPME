"""Servicio de negocio para usuarios (`core`)."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import get_password_hash
from app.models import User
from app.repositories.user_repository import UserRepository


class UserService:
    """Operaciones de negocio asociadas a identidad y permisos de usuario."""

    @staticmethod
    def get_active_by_id(db: Session, *, user_id: uuid.UUID) -> User:
        """Obtiene usuario activo por id o lanza error de dominio."""
        user = UserRepository.get_by_id(db, user_id)
        if not user or not user.is_active:
            raise NotFoundError("Usuario no encontrado o inactivo.")
        return user

    @staticmethod
    def get_by_username(db: Session, *, username: str) -> User | None:
        """Busca usuario por username para autenticación."""
        return UserRepository.get_by_username(db, username)

    @staticmethod
    def list_users(db: Session) -> list[User]:
        """Lista usuarios para panel de administración."""
        return UserRepository.list_all(db)

    @staticmethod
    def create_user(
        db: Session,
        *,
        email: str,
        username: str,
        password: str,
        is_active: bool,
        can_manage_catalogs: bool,
        can_import_official_data: bool,
        can_manage_users: bool,
        can_manage_scenarios: bool = False,
        is_admin_reports: bool = False,
        can_manage_system_settings: bool = False,
    ) -> User:
        """Crea usuario con permisos iniciales."""
        user = User(
            email=email.strip(),
            username=username.strip(),
            hashed_password=get_password_hash(password),
            is_active=is_active,
            can_manage_catalogs=can_manage_catalogs,
            can_import_official_data=can_import_official_data,
            can_manage_users=can_manage_users,
            can_manage_scenarios=can_manage_scenarios,
            is_admin_reports=is_admin_reports,
            can_manage_system_settings=can_manage_system_settings,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            raise ConflictError("No se pudo crear usuario (email/username ya existe).") from e
        db.refresh(user)
        return user

    @staticmethod
    def set_catalog_manager(db: Session, *, user_id: uuid.UUID, can_manage_catalogs: bool) -> User:
        """Asigna o revoca permiso administrativo de catálogos."""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise NotFoundError("Usuario no encontrado.")
        user.can_manage_catalogs = can_manage_catalogs
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def set_official_data_importer(
        db: Session, *, user_id: uuid.UUID, can_import_official_data: bool
    ) -> User:
        """Asigna o revoca permiso de importación de datos oficiales."""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise NotFoundError("Usuario no encontrado.")
        user.can_import_official_data = can_import_official_data
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def set_permissions(
        db: Session,
        *,
        user_id: uuid.UUID,
        is_active: bool,
        can_manage_catalogs: bool,
        can_import_official_data: bool,
        can_manage_users: bool,
        can_manage_scenarios: bool = False,
        is_admin_reports: bool = False,
        can_manage_system_settings: bool = False,
    ) -> User:
        """Actualiza permisos funcionales en una sola operación."""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise NotFoundError("Usuario no encontrado.")
        user.is_active = is_active
        user.can_manage_catalogs = can_manage_catalogs
        user.can_import_official_data = can_import_official_data
        user.can_manage_users = can_manage_users
        user.can_manage_scenarios = can_manage_scenarios
        user.is_admin_reports = is_admin_reports
        user.can_manage_system_settings = can_manage_system_settings
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def reset_password(
        db: Session, *, user_id: uuid.UUID, new_password: str
    ) -> User:
        """Restablece la contraseña de un usuario (uso administrativo)."""
        if not new_password or len(new_password) < 6:
            raise ConflictError(
                "La contraseña debe tener al menos 6 caracteres."
            )
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise NotFoundError("Usuario no encontrado.")
        user.hashed_password = get_password_hash(new_password)
        db.commit()
        db.refresh(user)
        return user


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Encapsular reglas de negocio del usuario por encima del repositorio.
#
# Posibles mejoras:
# - Añadir historial/auditoría de cambios de permisos.
#
# Riesgos en producción:
# - Cambios de privilegios sin auditoría dificultan trazabilidad de incidentes.
#
# Escalabilidad:
# - I/O-bound, coste bajo por operación.

