"""Rutas REST del agente de PC.

GET /api/agent/tools    — listar acciones disponibles.
POST /api/agent/run     — ejecutar acción.
POST /api/agent/confirm — confirmar acción pendiente.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

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
