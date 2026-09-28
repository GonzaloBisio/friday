"""Registro en memoria de la actividad de tools de FRIDAY — transparencia en vivo.

Cada vez que el cerebro ejecuta una tool registra acá un evento (`running` → `ok`/`error`).
El dashboard lo lee por REST y lo muestra en vivo, así Gonzalo VE qué hace FRIDAY mientras
lo hace. Y lo más importante: DELATA las alucinaciones — si FRIDAY dice "listo, lo cargué"
pero no hay ningún evento de tool, quedó en evidencia que no llamó nada.

Es un ring buffer EN PROCESO (la API y el cerebro viven en el mismo proceso de
`FridaySystem`), thread-safe. No toca la DB a propósito: la ejecución de tools es el hot
path de cada turno de voz y no queremos pegarle a SQLite ahí. Mismo espíritu que el log
de voz (`/api/voice/log`): efímero, barato, suficiente para "ver qué está pasando".
"""

from __future__ import annotations

import threading
import time
from collections import deque

_MAX_EVENTS = 100
_DETAIL_LIMIT = 160


class ToolActivityLog:
    """Ring buffer thread-safe de eventos de ejecución de tools."""

    def __init__(self, maxlen: int = _MAX_EVENTS) -> None:
        self._events: deque[dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0
        # Callbacks por evento (p. ej. push por WebSocket al HUD). Se llaman fuera del
        # lock y cualquier error se traga: la transparencia no puede romper una tool.
        self._subscribers: list = []

    def subscribe(self, callback) -> None:
        """Registra `callback(evento: dict)`; se invoca en cada record()."""
        self._subscribers.append(callback)

    def record(self, tool: str, status: str, detail: str = "") -> None:
        """Registra un evento. status ∈ {running, ok, error}."""
        with self._lock:
            self._seq += 1
            event = {
                "id": self._seq,
                "ts": time.strftime("%H:%M:%S"),
                "tool": tool,
                "status": status,
                "detail": _truncate(detail),
            }
            self._events.append(event)
        for cb in list(self._subscribers):
            try:
                cb(dict(event))
            except Exception:  # noqa: BLE001
                pass
        # Pilar 6: este es el punto único por donde pasan TODAS las tools, así que
        # alimentamos acá la salud agregada. Solo los estados TERMINALES cuentan
        # (no el "running", que es el mismo evento a mitad de camino).
        if status in ("ok", "error"):
            from friday.core.health import health_tracker
            health_tracker.record_tool(success=status == "ok")

    def recent(self, n: int = 30) -> list[dict]:
        with self._lock:
            return list(self._events)[-n:]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._seq = 0


def format_args(args: dict) -> str:
    """Resumen legible de los argumentos de una tool para el feed."""
    if not args:
        return ""
    return ", ".join(f"{k}={v}" for k, v in args.items())


def _truncate(s: str, limit: int = _DETAIL_LIMIT) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


# Singleton compartido por ambos cerebros (Ollama/Gemini) y la API — un solo proceso.
activity_log = ToolActivityLog()
