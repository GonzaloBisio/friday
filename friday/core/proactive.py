"""ProactiveDispatcher — Pilar 1 del salero proactivo.

Toma las Notification que detecta el notifier y decide CÓMO te llegan:
- voz (te interrumpe, reservada a lo grave),
- toast (visual, silencioso),
- o nada,
según la política de severidad (settings.proactive_*_min_level).

El texto hablado es una PLANTILLA con persona (inglés, voz Jarvis), NO una
llamada al LLM: el camino que te avisa que algo se rompió no puede depender de
una llamada de red frágil (costo, latencia, 429). El detalle exacto (en español,
tal como lo arma el notifier) viaja en el toast, para los ojos.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from friday.config import settings
from friday.storage.notification_repo import Notification

logger = logging.getLogger(__name__)

# info < warning < critical. Un nivel se emite por un canal si su rango es >= al mínimo.
_LEVEL_RANK = {"info": 0, "warning": 1, "critical": 2}


@dataclass
class ProactiveMessage:
    """Lo que el dispatcher decide enviar al cliente de voz."""

    text: str        # línea hablada (persona, inglés)
    speak: bool      # decirla en voz (además del toast)
    toast: bool      # mostrar toast visual
    level: str
    title: str
    message: str


def _spoken_text(n: Notification) -> str:
    """Plantilla de voz (inglés, persona FRIDAY) según source y si es recuperación.

    Genérica a propósito: el detalle exacto va en el toast. La voz solo te orienta
    ("algo se cayó", "el gasto cruzó el umbral") sin leerte números en español.
    """
    is_recovery = n.level == "info"
    if n.source == "nexcourt":
        return (
            "Sir, a service is back online."
            if is_recovery
            else "Sir, a service just went down. I've flagged it for you."
        )
    if n.source == "gemini":
        return "Sir, today's AI spend has crossed your threshold."
    # system / desconocido
    if is_recovery:
        return "Sir, systems are back to normal."
    return (
        "Sir, a system resource just hit a critical level. "
        "You may want to take a look."
    )


class ProactiveDispatcher:
    """Decide canal (voz/toast/nada) por notificación y lo emite por WebSocket."""

    def __init__(
        self,
        broadcast=None,
        *,
        speak_min_level: str | None = None,
        toast_min_level: str | None = None,
    ) -> None:
        self._broadcast = broadcast
        self._speak_min = speak_min_level or settings.proactive_speak_min_level
        self._toast_min = toast_min_level or settings.proactive_toast_min_level

    def plan(self, n: Notification) -> ProactiveMessage | None:
        """Decide qué hacer con una notificación. Pura y testeable (sin red).

        Retorna None si la notificación no alcanza ningún umbral (se silencia).
        """
        rank = _LEVEL_RANK.get(n.level, 0)
        speak = rank >= _LEVEL_RANK.get(self._speak_min, 99)
        toast = rank >= _LEVEL_RANK.get(self._toast_min, 99)
        if not (speak or toast):
            return None
        return ProactiveMessage(
            text=_spoken_text(n),
            speak=speak,
            toast=toast,
            level=n.level,
            title=n.title,
            message=n.message,
        )

    def dispatch(self, notifications: list[Notification]) -> list[ProactiveMessage]:
        """Planifica y emite cada notificación que califique. Retorna las emitidas."""
        emitted: list[ProactiveMessage] = []
        for n in notifications:
            msg = self.plan(n)
            if msg is None:
                continue
            self._emit(msg)
            emitted.append(msg)
        return emitted

    def _emit(self, msg: ProactiveMessage) -> None:
        """Emite el mensaje proactivo por WebSocket desde el thread del scheduler.

        Igual que el notifier: corremos la corutina en un loop efímero porque el
        job vive en un thread sin event loop propio. Best-effort: si falla el
        broadcast, no debe tumbar el chequeo proactivo.
        """
        if self._broadcast is None:
            return
        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self._broadcast.broadcast_proactive(
                        msg.text,
                        speak=msg.speak,
                        level=msg.level,
                        title=msg.title,
                        message=msg.message,
                    )
                )
            finally:
                loop.close()
        except Exception:
            logger.exception("Error emitiendo mensaje proactivo")
