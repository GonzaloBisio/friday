"""Rutas REST del agente de PC.

GET /api/agent/tools    — listar acciones disponibles.
POST /api/agent/run     — ejecutar acción.
POST /api/agent/confirm — confirmar acción pendiente.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from friday.core.activity import activity_log

router = APIRouter(tags=["agent"])

logger = logging.getLogger(__name__)


class AgentRunRequest(BaseModel):
    tool: str = Field(..., description="Nombre de la herramienta a ejecutar")
    args: dict = Field(default_factory=dict, description="Argumentos de la herramienta")


class AgentConfirmRequest(BaseModel):
    action_id: str = Field(..., description="ID de la acción pendiente")
    approved: bool = Field(..., description="True para aprobar, False para rechazar")


# ── GET /api/agent/tools ─────────────────────────────────────────────────

@router.get("/tools")
def list_tools(request: Request) -> list[dict]:
    """Lista las herramientas de PC disponibles (catalog)."""
    gate = request.app.state.friday.gate
    if gate is None:
        return []

    catalog = gate._registry.catalog
    return [
        {
            "name": a.name,
            "description": a.description,
            "risk": a.risk.value,
        }
        for a in catalog
    ]


# ── GET /api/agent/activity ──────────────────────────────────────────────
# Feed de transparencia: qué tools ejecutó FRIDAY en vivo (running → ok/error).
# Lo consume el dashboard para mostrar la actividad y delatar alucinaciones.

@router.get("/activity")
def agent_activity(n: int = Query(default=30, ge=1, le=100)) -> JSONResponse:
    """Últimos N eventos de ejecución de tools (transparencia en vivo)."""
    return JSONResponse({"events": activity_log.recent(n)})


# ── POST /api/agent/run ──────────────────────────────────────────────────

@router.post("/run")
def run_tool(request: Request, body: AgentRunRequest) -> dict:
    """Ejecuta una herramienta de PC. Retorna resultado o estado pendiente."""
    gate = request.app.state.friday.gate
    if gate is None:
        return {"status": "error", "reason": "Agente de PC no disponible"}

    result = gate.request(body.tool, body.args)
    return result


# ── POST /api/agent/confirm ──────────────────────────────────────────────

@router.post("/confirm")
def confirm_action(request: Request, body: AgentConfirmRequest) -> dict:
    """Confirma o rechaza una acción pendiente."""
    gate = request.app.state.friday.gate
    if gate is None:
        return {"status": "error", "reason": "Agente de PC no disponible"}

    result = gate.confirm(body.action_id, body.approved)
    return result
