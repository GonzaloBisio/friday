"""Ruta REST de chat con FRIDAY.

POST /api/chat       — enviar mensaje (con modelo auto/flash/pro).
GET  /api/chat/sessions — listar sesiones.
POST /api/chat/sessions/switch — cambiar de sesión.
GET  /api/chat/sessions/{id} — mensajes de una sesión.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["chat"])

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    model: str = Field(default="auto", pattern="^(auto|flash|pro)$")
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    session_id: str | None = None


class SwitchSessionRequest(BaseModel):
    session_id: str = Field(..., min_length=1)


@router.post("/chat")
async def post_chat(request: Request, body: ChatRequest) -> ChatResponse:
    """Envía un mensaje a FRIDAY. Usa modelo adaptativo por defecto."""
    state = request.app.state.friday
    brain = state.brain

    if brain is None:
        return ChatResponse(
            response="FRIDAY no tiene el cerebro configurado. Configurá GEMINI_API_KEY en .env",
            model="none",
        )

    broadcast = state.broadcast

    async def _think(step: str) -> None:
        if broadcast:
            try:
                await broadcast.send_json({"type": "thinking", "step": step})
            except Exception:
                pass

    await _think("Procesando...")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, brain.chat, body.message, body.model
        )
    except Exception as exc:
        logger.exception("Error en brain.chat")
        return ChatResponse(
            response=f"Error interno: {exc}",
            model="error",
        )

    await _think("Listo.")

    return ChatResponse(
        response=result.text,
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        session_id=brain.session_id,
    )


@router.get("/chat/sessions")
def list_sessions(request: Request) -> list[dict]:
    """Lista las sesiones de chat disponibles."""
    brain = request.app.state.friday.brain
    if brain is None or brain._chat_repo is None:
        return []
    return brain._chat_repo.list_sessions()


@router.post("/chat/sessions/switch")
def switch_session(request: Request, body: SwitchSessionRequest) -> dict:
    """Cambia a una sesión existente."""
    brain = request.app.state.friday.brain
    if brain is None:
        return {"status": "error", "reason": "Brain no disponible"}
    brain.switch_session(body.session_id)
    return {
        "status": "ok",
        "session_id": body.session_id,
        "message_count": len(brain.history),
    }


@router.get("/chat/sessions/{session_id}")
def get_session_messages(request: Request, session_id: str) -> dict:
    """Devuelve los mensajes de una sesión."""
    brain = request.app.state.friday.brain
    if brain is None or brain._chat_repo is None:
        return {"session_id": session_id, "messages": [], "error": "Brain no disponible"}

    messages = brain._chat_repo.load_session(session_id)
    return {
        "session_id": session_id,
        "message_count": len(messages),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "model": m.model,
                "tokens_in": m.tokens_in,
                "tokens_out": m.tokens_out,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }
