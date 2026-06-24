"""Rutas REST de research — el digest de inteligencia para el HUD (vista RESEARCH).

GET  /api/research/latest  → el digest markdown más reciente (content + metadatos).
GET  /api/research/list    → lista de digests disponibles (para navegar por fecha).
POST /api/research/refresh → fuerza una recolección AHORA (botón "actualizar").

Best-effort: si la capa de conocimiento no está cableada, devuelven available=False
en vez de reventar. La vista del HUD degrada con gracia.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["research"])

CATEGORY = "research"


def _store(request: Request):
    return getattr(request.app.state.friday, "knowledge", None)


@router.get("/research/latest")
def research_latest(request: Request) -> dict:
    """Último digest de research (content markdown + metadatos). available=False si no hay."""
    store = _store(request)
    if store is None:
        return {"available": False, "reason": "knowledge store no configurado"}
    note = store.latest(CATEGORY)
    if note is None:
        return {"available": False, "reason": "todavía no hay research"}
    content = store.read(CATEGORY, note.name) or ""
    return {
        "available": True,
        "name": note.name,
        "title": note.title,
        "modified_at": note.modified_at.isoformat(),
        "content": content,
    }


@router.get("/research/list")
def research_list(request: Request) -> dict:
    """Digests disponibles, más recientes primero (name = fecha, title, modified_at)."""
    store = _store(request)
    if store is None:
        return {"available": False, "items": []}
    items = [
        {"name": n.name, "title": n.title, "modified_at": n.modified_at.isoformat()}
        for n in store.list(CATEGORY, limit=30)
    ]
    return {"available": True, "items": items}


@router.post("/research/refresh")
def research_refresh(request: Request) -> dict:
    """Dispara una recolección AHORA (síncrona; tarda unos segundos). Devuelve el digest nuevo."""
    service = getattr(request.app.state.friday, "research_service", None)
    if service is None:
        return {"status": "error", "reason": "research no configurado"}
    try:
        service.run()
    except Exception as exc:  # noqa: BLE001 — red/IO: lo reportamos suave
        logger.warning("Research refresh falló", exc_info=True)
        return {"status": "error", "reason": str(exc)}
    return research_latest(request) | {"status": "ok"}
