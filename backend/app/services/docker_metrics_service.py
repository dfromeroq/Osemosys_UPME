"""Consulta métricas de memoria de servicios Docker vía socket Unix."""

from __future__ import annotations

import http.client
import json
import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from urllib.parse import quote

from app.core.config import get_settings


def _number_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class _UnixSocketHTTPConnection(http.client.HTTPConnection):
    """Conexión HTTP mínima contra el socket Unix del daemon Docker."""

    def __init__(self, socket_path: str, *, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:  # pragma: no cover
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


class DockerMetricsService:
    """Obtiene memoria por servicio del stack Docker actual.

    - Filtra por proyecto Compose del propio contenedor (evita contar RAM de
      otros stacks corriendo en el mismo host) + por lista de servicios.
    - Usa `?one-shot=true` en el endpoint de stats, que retorna al instante en
      lugar de bloquear ~1 s muestreando CPU.
    - Paraleliza las llamadas por contenedor con un ThreadPool.
    """

    _cache_lock = threading.Lock()
    _cached_service_memory: list[dict] = []
    _cache_expires_at: float = 0.0
    _cached_service_metrics: list[dict] = []
    _metrics_cache_expires_at: float = 0.0
    _detected_project: str | None = None

    @staticmethod
    def _request_json(path: str, *, timeout: float | None = None) -> object:
        settings = get_settings()
        t = timeout if timeout is not None else float(settings.docker_metrics_timeout_seconds)
        conn = _UnixSocketHTTPConnection(settings.docker_socket_path, timeout=max(0.05, t))
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            raw = response.read()
            if response.status >= 400:
                raise RuntimeError(
                    f"Docker API error {response.status}: {raw.decode('utf-8', errors='ignore')}"
                )
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
        finally:
            conn.close()

    @classmethod
    def _get_cached_service_memory(cls) -> list[dict]:
        now = monotonic()
        with cls._cache_lock:
            if now < cls._cache_expires_at:
                return [dict(item) for item in cls._cached_service_memory]
        return []

    @classmethod
    def _get_last_cached_service_memory(cls) -> list[dict]:
        with cls._cache_lock:
            return [dict(item) for item in cls._cached_service_memory]

    @classmethod
    def _set_cached_service_memory(cls, items: list[dict]) -> None:
        settings = get_settings()
        ttl = max(0.0, float(settings.docker_metrics_cache_ttl_seconds))
        with cls._cache_lock:
            cls._cached_service_memory = [dict(item) for item in items]
            cls._cache_expires_at = monotonic() + ttl

    @classmethod
    def _get_cached_service_metrics(cls) -> list[dict]:
        now = monotonic()
        with cls._cache_lock:
            if now < cls._metrics_cache_expires_at:
                return [dict(item) for item in cls._cached_service_metrics]
        return []

    @classmethod
    def _get_last_cached_service_metrics(cls) -> list[dict]:
        with cls._cache_lock:
            return [dict(item) for item in cls._cached_service_metrics]

    @classmethod
    def _set_cached_service_metrics(cls, items: list[dict]) -> None:
        ttl = max(0.0, float(get_settings().docker_metrics_cache_ttl_seconds))
        with cls._cache_lock:
            cls._cached_service_metrics = [dict(item) for item in items]
            cls._metrics_cache_expires_at = monotonic() + ttl

    @classmethod
    def _resolve_project(cls) -> str:
        """Retorna el proyecto Compose a filtrar.

        Prioridad: setting `docker_metrics_project` > auto-detección via
        etiqueta del propio contenedor > env `COMPOSE_PROJECT_NAME` > "" (sin
        filtro por proyecto).
        """
        settings = get_settings()
        explicit = (settings.docker_metrics_project or "").strip()
        if explicit:
            return explicit

        if cls._detected_project is not None:
            return cls._detected_project

        project = ""
        hostname = os.environ.get("HOSTNAME", "").strip()
        if hostname:
            try:
                info = cls._request_json(f"/containers/{quote(hostname, safe='')}/json")
                if isinstance(info, dict):
                    labels = ((info.get("Config") or {}).get("Labels")) or {}
                    project = str(labels.get("com.docker.compose.project") or "").strip()
            except (FileNotFoundError, OSError, RuntimeError, json.JSONDecodeError):
                project = ""

        if not project:
            project = os.environ.get("COMPOSE_PROJECT_NAME", "").strip()

        cls._detected_project = project
        return project

    @classmethod
    def _fetch_memory_usage(cls, container_id: str) -> int | None:
        """Obtiene `memory_stats.usage` con `one-shot=true` (no bloquea)."""
        try:
            stats = cls._request_json(
                f"/containers/{quote(container_id, safe='')}/stats?stream=false&one-shot=true"
            )
        except (OSError, RuntimeError, json.JSONDecodeError):
            return None
        if not isinstance(stats, dict):
            return None
        memory_stats = stats.get("memory_stats")
        if not isinstance(memory_stats, dict):
            return None
        usage = memory_stats.get("usage")
        if not isinstance(usage, (int, float)):
            return None
        return int(usage)

    @classmethod
    def _fetch_container_metrics(cls, service_name: str, container_id: str) -> dict | None:
        try:
            stats = cls._request_json(
                f"/containers/{quote(container_id, safe='')}/stats?stream=false&one-shot=true"
            )
            inspect = cls._request_json(f"/containers/{quote(container_id, safe='')}/json")
        except (OSError, RuntimeError, json.JSONDecodeError):
            return None
        if not isinstance(stats, dict):
            return None
        if not isinstance(inspect, dict):
            inspect = {}

        memory = stats.get("memory_stats") if isinstance(stats.get("memory_stats"), dict) else {}
        memory_stats = memory.get("stats") if isinstance(memory.get("stats"), dict) else {}
        usage = memory.get("usage")
        limit = memory.get("limit")
        inactive = memory_stats.get("inactive_file", memory_stats.get("total_inactive_file", 0))
        working_set = None
        if isinstance(usage, (int, float)):
            working_set = max(0, int(usage) - int(inactive or 0))
        peak = memory.get("max_usage")
        if not isinstance(peak, (int, float)):
            peak = memory_stats.get("peak")

        cpu = stats.get("cpu_stats") if isinstance(stats.get("cpu_stats"), dict) else {}
        precpu = stats.get("precpu_stats") if isinstance(stats.get("precpu_stats"), dict) else {}
        cpu_usage = cpu.get("cpu_usage") if isinstance(cpu.get("cpu_usage"), dict) else {}
        precpu_usage = precpu.get("cpu_usage") if isinstance(precpu.get("cpu_usage"), dict) else {}
        cpu_total = int(cpu_usage.get("total_usage") or 0)
        precpu_total = int(precpu_usage.get("total_usage") or 0)
        system_total = int(cpu.get("system_cpu_usage") or 0)
        presystem_total = int(precpu.get("system_cpu_usage") or 0)
        online_cpus = int(cpu.get("online_cpus") or len(cpu_usage.get("percpu_usage") or []) or 1)
        cpu_delta = cpu_total - precpu_total
        system_delta = system_total - presystem_total
        cpu_percent = None
        if cpu_delta >= 0 and system_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0

        state = inspect.get("State") if isinstance(inspect.get("State"), dict) else {}
        config = inspect.get("Config") if isinstance(inspect.get("Config"), dict) else {}
        processes: list[dict] = []
        try:
            top = cls._request_json(
                f"/containers/{quote(container_id, safe='')}/top?ps_args=-eo%20pid,ppid,pcpu,pmem,rss,comm,args",
                timeout=0.5,
            )
            if isinstance(top, dict):
                for row in (top.get("Processes") or [])[:20]:
                    if not isinstance(row, list) or len(row) < 6:
                        continue
                    processes.append({
                        "pid": row[0],
                        "ppid": row[1] if len(row) > 1 else None,
                        "cpu_percent": _number_or_none(row[2] if len(row) > 2 else None),
                        "memory_percent": _number_or_none(row[3] if len(row) > 3 else None),
                        "rss_kb": _int_or_none(row[4] if len(row) > 4 else None),
                        "command": row[5] if len(row) > 5 else None,
                        "args": row[6] if len(row) > 6 else None,
                    })
        except (OSError, RuntimeError, json.JSONDecodeError):
            pass

        pids = stats.get("pids_stats") if isinstance(stats.get("pids_stats"), dict) else {}
        return {
            "service_name": service_name,
            "container_id": container_id[:12],
            "container_name": str(inspect.get("Name") or "").lstrip("/"),
            "image": config.get("Image"),
            "status": state.get("Status"),
            "running": bool(state.get("Running")),
            "oom_killed": bool(state.get("OOMKilled")),
            "restart_count": int(inspect.get("RestartCount") or 0),
            "host_pid": _int_or_none(state.get("Pid")),
            "started_at": state.get("StartedAt"),
            "memory_usage_bytes": int(usage) if isinstance(usage, (int, float)) else None,
            "memory_working_set_bytes": working_set,
            "memory_limit_bytes": int(limit) if isinstance(limit, (int, float)) else None,
            "memory_peak_bytes": int(peak) if isinstance(peak, (int, float)) else None,
            "memory_used_percent": round((working_set / int(limit)) * 100, 2)
            if working_set is not None and isinstance(limit, (int, float)) and limit > 0
            else None,
            "cpu_percent": round(cpu_percent, 2) if cpu_percent is not None else None,
            "cpu_used_cores": round(cpu_percent / 100.0, 3) if cpu_percent is not None else None,
            "online_cpus": online_cpus,
            "pids_current": _int_or_none(pids.get("current")),
            "processes": processes,
        }

    @classmethod
    def list_service_metrics(cls) -> list[dict]:
        """Métricas detalladas por servicio, incluyendo CPU, OOM y procesos."""
        settings = get_settings()
        tracked = set(settings.docker_metrics_services_list())
        if not tracked:
            return []
        cached = cls._get_cached_service_metrics()
        if cached:
            return cached
        project_filter = cls._resolve_project()
        try:
            containers = cls._request_json("/containers/json?all=0")
        except (FileNotFoundError, OSError, RuntimeError, json.JSONDecodeError):
            return cls._get_last_cached_service_metrics()
        if not isinstance(containers, list):
            return cls._get_last_cached_service_metrics()
        targets: list[tuple[str, str]] = []
        for container in containers:
            labels = container.get("Labels") or {}
            service_name = labels.get("com.docker.compose.service")
            if service_name not in tracked:
                continue
            if project_filter and labels.get("com.docker.compose.project") != project_filter:
                continue
            if container.get("Id"):
                targets.append((str(service_name), str(container["Id"])))
        if not targets:
            cls._set_cached_service_metrics([])
            return []
        max_workers = max(1, min(8, len(targets)))
        items: list[dict] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for result in pool.map(lambda item: cls._fetch_container_metrics(*item), targets):
                if result is not None:
                    items.append(result)
        items.sort(key=lambda item: item["service_name"])
        cls._set_cached_service_metrics(items)
        return items

    @staticmethod
    def list_service_memory() -> list[dict]:
        """Retorna uso de memoria por servicio compose rastreado."""
        settings = get_settings()
        tracked = set(settings.docker_metrics_services_list())
        if not tracked:
            return []

        cached = DockerMetricsService._get_cached_service_memory()
        if cached:
            return cached

        project_filter = DockerMetricsService._resolve_project()

        try:
            containers = DockerMetricsService._request_json("/containers/json?all=0")
        except (FileNotFoundError, OSError, RuntimeError, json.JSONDecodeError):
            return DockerMetricsService._get_last_cached_service_memory()

        if not isinstance(containers, list):
            return DockerMetricsService._get_last_cached_service_memory()

        # Seleccionamos los contenedores a consultar respetando proyecto + servicio.
        targets: list[tuple[str, str]] = []
        for container in containers:
            labels = container.get("Labels") or {}
            service_name = labels.get("com.docker.compose.service")
            if service_name not in tracked:
                continue
            if project_filter:
                container_project = labels.get("com.docker.compose.project")
                if container_project != project_filter:
                    continue
            container_id = container.get("Id")
            if not container_id:
                continue
            targets.append((str(service_name), str(container_id)))

        if not targets:
            DockerMetricsService._set_cached_service_memory([])
            return []

        # `?one-shot=true` devuelve al instante: paralelizamos igual porque el
        # handshake + read del socket se beneficia y así acotamos latencia total.
        def _task(item: tuple[str, str]) -> dict | None:
            service_name, container_id = item
            usage = DockerMetricsService._fetch_memory_usage(container_id)
            if usage is None:
                return None
            return {"service_name": service_name, "memory_usage_bytes": usage}

        max_workers = max(1, min(8, len(targets)))
        stats_by_service: list[dict] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for result in pool.map(_task, targets):
                if result is not None:
                    stats_by_service.append(result)

        sorted_items = sorted(stats_by_service, key=lambda item: item["service_name"])
        DockerMetricsService._set_cached_service_memory(sorted_items)
        return sorted_items
