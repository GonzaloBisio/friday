"""Collector de uso de Gemini — trackea requests, tokens y costo estimado.

Este módulo expone un singleton `gemini_tracker` que otros módulos (brain.py)
llaman con `record()` tras cada request al SDK. El collector lee los contadores
acumulados desde el último snapshot y genera MetricPoints.
"""

from __future__ import annotations

import threading

from friday.config import settings
from friday.models import MetricPoint

from .base import Collector


class GeminiTracker:
    """Acumula uso de Gemini de forma thread-safe. Brain.py llama record() tras cada request."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: int = 0
        self._tokens_in: int = 0
        self._tokens_out: int = 0

    def record(self, tokens_in: int, tokens_out: int) -> None:
        """Registra una llamada al SDK de Gemini."""
        with self._lock:
            self._requests += 1
            self._tokens_in += tokens_in
            self._tokens_out += tokens_out

    def snapshot_and_reset(self) -> dict[str, int]:
        """Devuelve los contadores acumulados y los resetea a cero (atómico)."""
        with self._lock:
            data = {
                "requests": self._requests,
                "tokens_in": self._tokens_in,
                "tokens_out": self._tokens_out,
            }
            self._requests = 0
            self._tokens_in = 0
            self._tokens_out = 0
            return data

    @property
    def totals(self) -> dict[str, int]:
        """Lee los contadores sin resetear (para inspección)."""
        with self._lock:
            return {
                "requests": self._requests,
                "tokens_in": self._tokens_in,
                "tokens_out": self._tokens_out,
            }


# Singleton global — importar y usar desde cualquier módulo
gemini_tracker = GeminiTracker()


class GeminiUsageCollector(Collector):
    """Genera MetricPoints a partir de los contadores acumulados del tracker."""

    def __init__(self, tracker: GeminiTracker | None = None) -> None:
        self._tracker = tracker or gemini_tracker

    @property
    def source(self) -> str:
        return "gemini"

    @property
    def interval_seconds(self) -> int:
        return 30  # cada 30s volcamos el snapshot

    def collect(self) -> list[MetricPoint]:
        snap = self._tracker.snapshot_and_reset()
        now = MetricPoint.utcnow()

        cost_in = (snap["tokens_in"] / 1000) * settings.gemini_cost_per_1k_input_tokens
        cost_out = (snap["tokens_out"] / 1000) * settings.gemini_cost_per_1k_output_tokens
        cost_total = cost_in + cost_out

        return [
            MetricPoint(
                timestamp=now, source=self.source, name="requests",
                value=float(snap["requests"]), unit="count",
            ),
            MetricPoint(
                timestamp=now, source=self.source, name="tokens_in",
                value=float(snap["tokens_in"]), unit="tokens",
            ),
            MetricPoint(
                timestamp=now, source=self.source, name="tokens_out",
                value=float(snap["tokens_out"]), unit="tokens",
            ),
            MetricPoint(
                timestamp=now, source=self.source, name="cost_usd",
                value=cost_total, unit="usd",
            ),
        ]
