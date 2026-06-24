"""WebSocket /ws/live — push de métricas, thinking steps, y estado de servicios.

Los collectors y el brain emiten eventos que se broadcast a todos los clientes conectados.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

logger = logging.getLogger(__name__)


class WebSocketBroadcast:
    """Maneja múltiples conexiones WebSocket y broadcast a todos los clientes."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("WS client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("WS client disconnected (%d remaining)", len(self._connections))

    async def send_json(self, data: dict) -> None:
        """Envía un mensaje JSON a todos los clientes conectados."""
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_metric(self, source: str, name: str, value: float, **extra) -> None:
        """Emite un punto de métrica en vivo."""
        payload = {"type": "metric", "source": source, "name": name, "value": value}
        payload.update(extra)
        await self.send_json(payload)

    async def broadcast_thinking(self, step: str) -> None:
        """Emite un paso de pensamiento del chat."""
        await self.send_json({"type": "thinking", "step": step})

    async def broadcast_service_state(self, service: str, status: str) -> None:
        """Emite cambio de estado de un servicio."""
        await self.send_json({"type": "service_state", "service": service, "status": status})

    async def broadcast_proactive(
        self, text: str, *, speak: bool, level: str, title: str, message: str = "",
    ) -> None:
        """Emite un mensaje proactivo para el cliente de voz (Pilar 1).

        `text` es la línea hablada (persona, inglés); `speak` indica si además de
        mostrar el toast hay que decirla en voz. El cliente Windows escucha estos
        eventos en /ws/live y actúa: toast siempre, voz solo si speak=True.
        """
        await self.send_json({
            "type": "proactive",
            "text": text,
            "speak": speak,
            "level": level,
            "title": title,
            "message": message,
        })

    @property
    def active_connections(self) -> int:
        return len(self._connections)


# ── WebSocket endpoint ───────────────────────────────────────────────────

@router.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    """Conexión WebSocket para recibir actualizaciones en vivo."""
    broadcast = ws.app.state.friday.broadcast
    if broadcast is None:
        await ws.close(code=1011, reason="Broadcast not initialized")
        return

    await broadcast.connect(ws)
    try:
        # Enviar snapshot inicial
        await ws.send_json({"type": "connected", "message": "FRIDAY live feed active"})

        # Mantener la conexión abierta recibiendo heartbeats
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS error: %s", exc)
    finally:
        broadcast.disconnect(ws)
