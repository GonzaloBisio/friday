"""Collector NEXCOURT — poll a Spring Boot Actuator de cada microservicio."""

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


class NexcourtCollector(Collector):
    """Consulta /actuator/health y /actuator/prometheus de cada servicio NEXCOURT."""

    def __init__(
        self,
        base_url: str | None = None,
        services: list[str] | None = None,
        api_key: str | None = None,
    ) -> None:
        self._base_url = (base_url or settings.nexcourt_base_url).rstrip("/")
        self._services = services if services is not None else settings.nexcourt_services
        self._api_key = api_key or settings.nexcourt_api_key

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

    def _collect_service(self, service: str) -> list[MetricPoint]:
        now = MetricPoint.utcnow()
        points: list[MetricPoint] = []
        headers = self._build_headers()

        health = self._fetch_health(service, headers)
        status_val = 1.0 if health == "UP" else 0.0
        points.append(MetricPoint(
            timestamp=now, source=self.source, name="status",
            value=status_val, service=service, tags={"health": health},
        ))

        if status_val == 0.0:
            return points

        prom_metrics = self._fetch_prometheus(service, headers)
        for name, value in prom_metrics.items():
            points.append(MetricPoint(
                timestamp=now, source=self.source, name=name,
                value=value, service=service,
            ))

        return points

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _fetch_health(self, service: str, headers: dict[str, str]) -> str:
        url = f"{self._base_url}/{service}/actuator/health"
        try:
            resp = httpx.get(url, headers=headers, timeout=HEALTH_TIMEOUT, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status", "UNKNOWN")
            return "DOWN"
        except Exception as exc:
            logger.warning("Health check failed for %s: %s", service, exc)
            return "DOWN"

    def _fetch_prometheus(self, service: str, headers: dict[str, str]) -> dict[str, float]:
        url = f"{self._base_url}/{service}/actuator/prometheus"
        try:
            resp = httpx.get(url, headers=headers, timeout=METRICS_TIMEOUT, verify=False)
            if resp.status_code != 200:
                return {}
            return _parse_prometheus(resp.text)
        except Exception as exc:
            logger.warning("Prometheus fetch failed for %s: %s", service, exc)
            return {}


_METRICS_OF_INTEREST = {
    "http_server_requests_seconds_count",
    "http_server_requests_seconds_sum",
    "jvm_memory_used_bytes",
    "jvm_threads_live_threads",
    "process_cpu_usage",
    "system_cpu_usage",
}

_PROM_LINE_RE = re.compile(r"^(\w+?)(?:\{[^}]*\})?\s+([\d.eE+\-]+)$")


def _parse_prometheus(text: str) -> dict[str, float]:
    """Extrae métricas seleccionadas del formato Prometheus exposition."""
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
        if name in result:
            result[name] += value
        else:
            result[name] = value
    return result
