"""Rutas REST de luces / control IR.

El listener de voz (friday/voice/wake.py) NO importa el resto del paquete friday:
habla con el cerebro solo por HTTP. Así que el estado de voz para las luces se
empuja por acá, igual que /chat.

    POST /api/lights/state   {"state": "listening"}  → aplica color a la tira LED
    GET  /api/lights/state                           → último estado aplicado
    POST /api/ir/send        {"device": "tv", "command": "power"} → emite un código
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from friday.integrations.ir.controller import IRError
from friday.integrations.lights import STATE_TO_COMMAND, get_lights

router = APIRouter(tags=["lights"])


class LightState(BaseModel):
    state: str


class IRCommand(BaseModel):
    device: str
    command: str


@router.post("/lights/state")
def set_light_state(payload: LightState) -> JSONResponse:
    """Aplica un estado de voz a la tira LED (fire-and-forget, nunca falla)."""
    if payload.state not in STATE_TO_COMMAND:
        return JSONResponse(
            {"status": "ignored", "reason": f"estado desconocido: {payload.state}"},
            status_code=200,
        )
    get_lights().set_state(payload.state)
    return JSONResponse({"status": "ok", "state": payload.state})


@router.get("/lights/state")
def get_light_state() -> JSONResponse:
    return JSONResponse({"status": "ok", "state": get_lights().state})


@router.post("/ir/send")
def ir_send(payload: IRCommand) -> JSONResponse:
    """Emite un código IR aprendido (TV, aire, etc.). Síncrono: reporta el error."""
    lights = get_lights()
    try:
        lights._controller.send(payload.device, payload.command)
    except IRError as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=400)
    return JSONResponse({"status": "ok", "device": payload.device, "command": payload.command})
