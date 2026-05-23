from __future__ import annotations

"""Inicialización de Celery para ejecución asíncrona de simulaciones.

Este módulo centraliza la configuración de broker/backend y serialización para
todos los workers de simulación. Debe mantenerse libre de lógica de negocio;
su responsabilidad es infraestructura de ejecución distribuida.
"""

import logging

from celery import Celery

from app.core.config import get_settings
from app.simulation.core.solver import get_solver_availability

settings = get_settings()
logger = logging.getLogger(__name__)

broker_url = settings.redis_url
backend_url = settings.redis_url
if settings.is_sync_simulation_mode():
    # En modo local síncrono no dependemos de Redis.
    broker_url = "memory://"
    backend_url = "cache+memory://"

celery_app = Celery(
    "osemosys_simulation",
    broker=broker_url,
    backend=backend_url,
)

celery_app.conf.update(
    # `task_track_started` permite observabilidad de transición PENDING -> STARTED.
    task_track_started=True,
    # Ack tardío + rechazo ante WorkerLost evita consumir definitivamente una
    # task cuando el proceso hijo muere por SIGKILL/OOM.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # JSON reduce superficie de ataque frente a serializadores ejecutables.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # UTC evita deriva temporal entre nodos/hosts.
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.simulation", "app.scenario"])

availability = get_solver_availability()
missing = [name for name, enabled in availability.items() if not enabled]
if missing:
    logger.warning(
        "Worker con solvers faltantes: %s. Disponibilidad: %s",
        ", ".join(missing),
        availability,
    )
else:
    logger.info("Worker con todos los solvers disponibles: %s", availability)


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Proveer una instancia única de Celery con configuración homogénea.
#
# Posibles mejoras:
# - Externalizar configuración avanzada (retries, acks_late, prefetch) por entorno.
# - Configurar colas dedicadas por prioridad/tipo de simulación.
#
# Riesgos en producción:
# - Uso de un único broker/backend puede ser punto único de falla.
# - Si `redis_url` apunta a una instancia no aislada, puede haber interferencia
#   de namespaces de tareas con otros servicios.
#
# Escalabilidad:
# - Escala horizontalmente agregando workers; requiere tuning de concurrency y
#   tamaño de cola para no saturar CPU en cargas de solve.
