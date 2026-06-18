"""Collector NEXCOURT — poll a Spring Boot Actuator de cada microservicio.

Soporta dos modos:
- "direct":  consulta los management ports (9081-9087) directamente.
- "kong":    consulta vía Kong gateway (/health/{service}).
"""

from __future__ import annotations

import logging
import re

import httpx

from friday.config import settings
from friday.models import MetricPoint

from .base import Collector

logger = logging.getLogger(__name__)

HEALTH_TIMEOUT = 5.0
METRICS_TIMEOUT = 10.0

# --- Métricas Prometheus que nos interesan trackear ---
_METRICS_OF_INTEREST = {
    "http_server_requests_seconds_count",
    "http_server_requests_seconds_sum",
    "jvm_memory_used_bytes",
    "jvm_threads_live_threads",
    "process_cpu_usage",
    "system_cpu_usage",
}

_PROM_LINE_RE = re.compile(r"^(\w+?)(?:\{[^}]*\})?\s+([\d.eE+\-]+)$")

# --- Mapeo de puertos de gestión por servicio (descubierto del repo NEXCOURT) ---
_SERVICE_MGMT_PORTS: dict[str, int] = {
    "clubs-service":          9081,
    "reservations-service":   9082,
    "stock-service":          9083,
    "reports-service":        9084,
    "sports-service":         9085,
    "media-service":          9086,
    "notifications-service":  9087,
}

# --- Mapeo de paths Kong para health ---
_SERVICE_KONG_PATHS: dict[str, str] = {
    "clubs-service":          "clubs",
    "reservations-service":   "reservations",
    "stock-service":          "stock",
    "reports-service":        "reports",
    "sports-service":         "sports",
    "media-service":          "media",
    "notifications-service":  "notifications",
}


class NexcourtCollector(Collector):
    """Consulta /actuator/health y /actuator/prometheus de cada servicio NEXCOURT.

    En modo "direct" usa los puertos de gestión 9081-9087.
    En modo "kong" usa el gateway para health (prometheus no disponible via Kong).
    """

    def __init__(
        self,
        mode: str | None = None,
        direct_host: str | None = None,
        kong_url: str | None = None,
        services: list[str] | None = None,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._mode = mode or settings.nexcourt_mode
        self._direct_host = (direct_host or settings.nexcourt_direct_host).rstrip("/")
        self._kong_url = (kong_url or settings.nexcourt_kong_url).rstrip("/")
        self._services = self._resolve_services(services)
        self._api_key = api_key or settings.nexcourt_api_key
        self._client = client or self._build_client()

    def _resolve_services(self, override: list[str] | None) -> list[str]:
        if override is not None:
            return override
        # Preferir el config estructurado; fallback al listado plano legacy
        cfg = settings.nexcourt_services_config
        if cfg:
            return list(cfg.keys())
        return list(settings.nexcourt_services)

    def _build_client(self) -> httpx.Client:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        verify = self._mode != "direct"  # solo verificar TLS en modo kong
        return httpx.Client(headers=headers, verify=verify, timeout=METRICS_TIMEOUT)

    # ── Collector interface ───────────────────────────────────────────────

    @property
    def source(self) -> str:
        return "nexcourt"

    @property
    def interval_seconds(self) -> int:
        return settings.nexcourt_poll_interval_seconds

    def collect(self) -> list[MetricPoint]:
        if not self._services:
            return []

        points: list[MetricPoint] = []
        for service in self._services:
            points.extend(self._collect_service(service))
        return points

    # ── Service-level collection ──────────────────────────────────────────

    def _collect_service(self, service: str) -> list[MetricPoint]:
        now = MetricPoint.utcnow()
        points: list[MetricPoint] = []

        health = self._fetch_health(service)
        status_val = 1.0 if health == "UP" else 0.0
        points.append(MetricPoint(
            timestamp=now, source=self.source, name="status",
            value=status_val, service=service, tags={"health": health},
        ))

        # Solo fetcheamos Prometheus si el servicio está UP y NO estamos en modo kong
        # (Kong no expone /actuator/prometheus)
        if status_val == 1.0 and self._mode != "kong":
            prom_metrics = self._fetch_prometheus(service)
            for name, value in prom_metrics.items():
                points.append(MetricPoint(
                    timestamp=now, source=self.source, name=name,
                    value=value, service=service,
                ))

        return points

    # ── URL builders ──────────────────────────────────────────────────────

    def _health_url(self, service: str) -> str:
        if self._mode == "kong":
            path = _SERVICE_KONG_PATHS.get(service, service)
            return f"{self._kong_url}/health/{path}"
        # direct mode
        port = _SERVICE_MGMT_PORTS.get(service)
        if port is None:
            logger.warning("Puerto de gestión desconocido para %s, usando URL legacy", service)
            return f"{self._direct_host}/{service}/actuator/health"
        return f"{self._direct_host}:{port}/actuator/health"

    def _metrics_url(self, service: str) -> str:
        """En modo kong no hay endpoint de métricas; solo se usa en modo direct."""
        if self._mode == "kong":
            return ""  # no disponible
        port = _SERVICE_MGMT_PORTS.get(service)
        if port is None:
            return f"{self._direct_host}/{service}/actuator/prometheus"
        return f"{self._direct_host}:{port}/actuator/prometheus"

    # ── HTTP fetchers ─────────────────────────────────────────────────────

    def _fetch_health(self, service: str) -> str:
        url = self._health_url(service)
        try:
            resp = self._client.get(url, timeout=HEALTH_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status", "UNKNOWN")
            logger.warning("Health check %s → HTTP %d", service, resp.status_code)
            return "DOWN"
        except Exception as exc:
            logger.warning("Health check failed for %s: %s", service, exc)
            return "DOWN"

    def _fetch_prometheus(self, service: str) -> dict[str, float]:
        url = self._metrics_url(service)
        if not url:
            return {}
        try:
            resp = self._client.get(url, timeout=METRICS_TIMEOUT)
            if resp.status_code != 200:
                return {}
            return _parse_prometheus(resp.text)
        except Exception as exc:
            logger.warning("Prometheus fetch failed for %s: %s", service, exc)
            return {}


# ── Parsing de Prometheus ─────────────────────────────────────────────────

def _parse_prometheus(text: str) -> dict[str, float]:
    """Extrae métricas seleccionadas del formato Prometheus exposition.

    Acumula valores cuando la misma métrica aparece con distintos tags
    (ej. http_server_requests_seconds_count por endpoint).
    """
    result: dict[str, float] = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        m = _PROM_LINE_RE.match(line)
        if m is None:
            continue
        name = m.group(1)
        if name not in _METRICS_OF_INTEREST:
            continue
        try:
            value = float(m.group(2))
        except ValueError:
            continue
        result[name] = result.get(name, 0.0) + value
    return result
