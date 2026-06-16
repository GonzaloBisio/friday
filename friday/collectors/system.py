"""Collector de métricas del sistema operativo (CPU, RAM, disco, uptime)."""

from __future__ import annotations

import time

import psutil

from friday.config import settings
from friday.models import MetricPoint

from .base import Collector


class SystemCollector(Collector):
    """Recolecta métricas del SO usando psutil."""

    @property
    def source(self) -> str:
        return "system"

    @property
    def interval_seconds(self) -> int:
        return settings.system_poll_interval_seconds

    def collect(self) -> list[MetricPoint]:
        now = MetricPoint.utcnow()
        points: list[MetricPoint] = []

        # CPU
        cpu = psutil.cpu_percent(interval=None)
        points.append(MetricPoint(
            timestamp=now, source=self.source, name="cpu_percent",
            value=cpu, unit="%",
        ))

        # RAM
        mem = psutil.virtual_memory()
        points.append(MetricPoint(
            timestamp=now, source=self.source, name="ram_percent",
            value=mem.percent, unit="%",
        ))
        points.append(MetricPoint(
            timestamp=now, source=self.source, name="ram_used_bytes",
            value=float(mem.used), unit="bytes",
        ))

        # Disco
        disk = psutil.disk_usage("/")
        points.append(MetricPoint(
            timestamp=now, source=self.source, name="disk_percent",
            value=disk.percent, unit="%",
        ))

        # Uptime (segundos desde boot)
        boot = psutil.boot_time()
        uptime_seconds = time.time() - boot
        points.append(MetricPoint(
            timestamp=now, source=self.source, name="uptime_seconds",
            value=uptime_seconds, unit="seconds",
        ))

        return points
