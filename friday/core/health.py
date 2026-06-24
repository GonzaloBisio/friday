"""HealthTracker — Pilar 6 del salero proactivo: autoobservabilidad.

El sistema que se mide a sí mismo es el que mejora solo. Mientras el `activity_log`
es un feed EFÍMERO ("qué hace FRIDAY ahora"), este tracker AGREGA señales vitales
de la sesión: tasa de éxito de tools, cuántas veces Gemini cayó a Ollama (429), y
la latencia media de respuesta. Son los signos vitales que el dashboard JARVIS va
a lucir y que FRIDAY puede contar por voz ("¿cómo venís?").

Singleton thread-safe (la API y los cerebros viven en el mismo proceso). En memoria:
refleja la salud de la SESIÓN ACTUAL (se resetea al reiniciar). Persistir tendencias
de la propia salud —para que el analista del Pilar 3 detecte su degradación— es una
extensión natural a futuro.
"""

from __future__ import annotations

import threading


class HealthTracker:
    """Acumula signos vitales de FRIDAY: éxito de tools, fallbacks, latencia."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tool_ok = 0
        self._tool_err = 0
        self._fallbacks = 0
        self._chat_count = 0
        self._latency_sum_ms = 0.0

    def record_tool(self, success: bool) -> None:
        """Cuenta una ejecución de tool ya terminada (no el 'running')."""
        with self._lock:
            if success:
                self._tool_ok += 1
            else:
                self._tool_err += 1

    def record_fallback(self) -> None:
        """Cuenta una degradación de Gemini a Ollama (429 sin cuota)."""
        with self._lock:
            self._fallbacks += 1

    def record_latency(self, ms: float) -> None:
        """Cuenta una respuesta del cerebro y su latencia."""
        with self._lock:
            self._chat_count += 1
            self._latency_sum_ms += ms

    def snapshot(self) -> dict:
        """Estado actual de salud (no resetea). Para el endpoint y la tool de voz."""
        with self._lock:
            tool_total = self._tool_ok + self._tool_err
            success_rate = self._tool_ok / tool_total if tool_total else 1.0
            avg_latency = self._latency_sum_ms / self._chat_count if self._chat_count else 0.0
            return {
                "tool_calls": tool_total,
                "tool_ok": self._tool_ok,
                "tool_errors": self._tool_err,
                "tool_success_rate": round(success_rate, 4),
                "ollama_fallbacks": self._fallbacks,
                "chat_count": self._chat_count,
                "avg_latency_ms": round(avg_latency, 1),
            }

    def reset(self) -> None:
        with self._lock:
            self._tool_ok = 0
            self._tool_err = 0
            self._fallbacks = 0
            self._chat_count = 0
            self._latency_sum_ms = 0.0


# Singleton compartido por ambos cerebros, el activity_log y la API — un solo proceso.
health_tracker = HealthTracker()


def register_health_tools(tools_reg) -> None:
    """Expone la autoobservabilidad como tool del LLM (FRIDAY reporta su salud)."""

    def estado_de_friday() -> str:
        """Reporta la salud actual de FRIDAY: éxito de tools, fallbacks y latencia.

        Usá esto cuando Gonzalo pregunte cómo venís, tu estado, tu diagnóstico o
        si todo anda bien por dentro.
        """
        s = health_tracker.snapshot()
        if s["chat_count"] == 0 and s["tool_calls"] == 0:
            return "Recién arranco, sir; todavía sin actividad para reportar."
        return (
            f"Tools al {s['tool_success_rate'] * 100:.0f}% de éxito en "
            f"{s['tool_calls']} llamadas, {s['ollama_fallbacks']} caídas a local, "
            f"latencia media {s['avg_latency_ms']:.0f} milisegundos."
        )

    tools_reg.register(estado_de_friday)
