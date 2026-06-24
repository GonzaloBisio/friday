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
        # Desglose por modelo para aplicar pricing por modelo en el collector.
        self._by_model: dict[str, dict[str, int]] = {}

    def record(self, tokens_in: int, tokens_out: int, model: str = "") -> None:
        """Registra una llamada al SDK de Gemini, atribuida a un modelo."""
        with self._lock:
            self._requests += 1
            self._tokens_in += tokens_in
            self._tokens_out += tokens_out
            bucket = self._by_model.setdefault(
                model or "unknown",
                {"requests": 0, "tokens_in": 0, "tokens_out": 0},
            )
            bucket["requests"] += 1
            bucket["tokens_in"] += tokens_in
            bucket["tokens_out"] += tokens_out

    def snapshot_and_reset(self) -> dict:
        """Devuelve los contadores acumulados (con desglose por modelo) y resetea."""
        with self._lock:
            data = {
                "requests": self._requests,
                "tokens_in": self._tokens_in,
                "tokens_out": self._tokens_out,
                "by_model": self._by_model,
            }
            self._requests = 0
            self._tokens_in = 0
            self._tokens_out = 0
            self._by_model = {}
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


def _cost_from_snapshot(snap: dict) -> float:
    """Costo total USD aplicando el precio de cada modelo del desglose.

    Modelos fuera de `settings.gemini_pricing` caen al escalar de config. Si no
    hay desglose (registros viejos sin modelo), usa el agregado con el escalar.
    """
    by_model = snap.get("by_model") or {}
    if not by_model:
        return (
            (snap.get("tokens_in", 0) / 1000) * settings.gemini_cost_per_1k_input_tokens
            + (snap.get("tokens_out", 0) / 1000) * settings.gemini_cost_per_1k_output_tokens
        )
    fallback = {
        "in": settings.gemini_cost_per_1k_input_tokens,
        "out": settings.gemini_cost_per_1k_output_tokens,
    }
    total = 0.0
    for model, c in by_model.items():
        price = settings.gemini_pricing.get(model, fallback)
        total += (c["tokens_in"] / 1000) * price["in"]
        total += (c["tokens_out"] / 1000) * price["out"]
    return total


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

        cost_total = _cost_from_snapshot(snap)

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
