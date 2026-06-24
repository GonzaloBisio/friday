"""Rutas REST de rutinas (Pilar 5 expuesto al HUD).

GET  /api/routines      — lista las rutinas disponibles.
POST /api/routines/run  — ejecuta una rutina por nombre.

El HUD pasa de MIRAR a ACTUAR. Cada paso de la rutina corre por el RoutineEngine,
que usa el PermissionGate: solo acciones LOW se ejecutan solas (las MEDIUM/HIGH
quedarían pendientes). Endpoint local; misma superficie que /api/agent/run.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["routines"])


class RunRequest(BaseModel):
    name: str = Field(description="Nombre de la rutina a ejecutar (ej. 'focus')")


@router.get("/routines")
def list_routines(request: Request) -> dict:
    """Lista las rutinas disponibles con su descripción y cantidad de pasos."""
    engine = request.app.state.friday.routines
    if engine is None:
        return {"routines": []}
    return {
        "routines": [
            {"name": r.name, "description": r.description, "steps": len(r.steps)}
            for r in engine.list_routines()
        ]
    }


@router.post("/routines/run")
def run_routine(request: Request, body: RunRequest) -> dict:
    """Ejecuta una rutina. Devuelve el resumen por paso del RoutineEngine."""
    engine = request.app.state.friday.routines
    if engine is None:
        return {"status": "error", "reason": "RoutineEngine no disponible"}
    return engine.run((body.name or "").strip().lower())
