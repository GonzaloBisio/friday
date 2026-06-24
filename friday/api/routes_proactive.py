"""Ruta REST de prueba del canal proactivo (Pilar 1).

POST /api/proactive/test — emite un evento proactivo de prueba al cliente de
voz (voz + toast), sin depender del notifier ni de umbrales. Herramienta de
validación: confirma el circuito backend → WebSocket → cliente Windows de
punta a punta, y sirve para los Pilares 3/5 que también emiten proactivamente.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["proactive"])

_DEFAULT_TEXT = (
    "Sir, this is a proactive channel test. If you can hear me, the link is working."
)


class ProactiveTestRequest(BaseModel):
    text: str = Field(default=_DEFAULT_TEXT, description="Texto hablado (persona, inglés)")
    speak: bool = Field(default=True, description="Si además del toast, decirlo en voz")
    level: str = Field(default="info", description="info | warning | critical")
    title: str = Field(default="FRIDAY — Test", description="Título del toast")
    message: str = Field(default="", description="Cuerpo del toast (vacío = usa text)")


@router.post("/proactive/test")
async def test_proactive(request: Request, body: ProactiveTestRequest) -> dict:
    """Dispara un evento proactivo de prueba al cliente de voz."""
    broadcast = request.app.state.friday.broadcast
    if broadcast is None:
        return {"status": "error", "reason": "broadcast no disponible"}

    await broadcast.broadcast_proactive(
        text=body.text,
        speak=body.speak,
        level=body.level,
        title=body.title,
        message=body.message or body.text,
    )
    return {
        "status": "ok",
        "sent": {"text": body.text, "speak": body.speak, "level": body.level},
        "clients": broadcast.active_connections,
    }
