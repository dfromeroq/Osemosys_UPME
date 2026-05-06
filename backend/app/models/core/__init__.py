"""Modelos ORM del esquema `core`."""

from .document_type import DocumentType
from .system_setting import SystemSetting
from .user import User

__all__ = ["DocumentType", "SystemSetting", "User"]


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Namespace de modelos transversales de identidad y autenticación.
#
# Posibles mejoras:
# - Incorporar modelos de roles/claims si crece control de acceso.
#
# Riesgos en producción:
# - Ninguno directo.
#
# Escalabilidad:
# - No aplica.
