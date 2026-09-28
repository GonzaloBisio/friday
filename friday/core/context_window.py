"""Helpers de contexto compartidos por los cerebros (Gemini y Ollama).

Objetivo: gastar menos tokens por turno sin perder información útil.

1. **Prefijo estable** — system prompt + tools se mandan en CADA llamada (~2.6K
   tokens). Gemini los cachea implícitamente (90% off) y Ollama reusa su KV-cache
   SOLO si el prefijo es idéntico byte a byte. Por eso el system prompt lleva la
   fecha del día (`day_stamp`) y la hora viaja en el mensaje (`with_time_note`).
2. **Resultados viejos recortados** — un resultado de tool ya consumido por el
   modelo se reenvía en cada llamada durante toda la ventana de historial. Se
   recorta (`compact_tool_result`) al arrancar el turno siguiente.
"""

from __future__ import annotations

from datetime import datetime

_TRUNC_MARK = "…[recortado; volvé a llamar la tool si necesitás el detalle]"


def day_stamp(now: datetime | None = None) -> str:
    """Fecha sin hora (ej. 'Saturday 26 September 2026'): cambia 1 vez por día."""
    return (now or datetime.now()).strftime("%A %d %B %Y")


def with_time_note(message: str, now: datetime | None = None) -> str:
    """Anexa la hora local al mensaje del usuario (queda fija en el historial)."""
    return f"{message}\n\n[local time {(now or datetime.now()):%H:%M}]"


def compact_tool_result(result: str, limit: int) -> str:
    """Recorta un resultado de tool a `limit` chars. Devuelve el MISMO objeto si
    no hace falta (así el caller detecta "sin cambios" con `is`)."""
    if limit <= 0 or len(result) <= limit or result.endswith(_TRUNC_MARK):
        return result
    return result[:limit].rstrip() + _TRUNC_MARK
