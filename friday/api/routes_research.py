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


# ── Brief de FRIDAY sobre el digest (INTEL) ────────────────────────────────
# El digest es determinista (titulares crudos) y muchos resultados son portales
# agregadores ("LLM News Today…"). El brief lo redacta el modelo lite UNA vez por
# digest (cache en memoria por nombre): ~1 llamada/día, centavos.
_BRIEF_CACHE: dict[str, str] = {}
_BRIEF_PROMPT = (
    "Resumí este digest de novedades para Gonzalo en 2 o 3 frases, en español rioplatense, "
    "sin markdown ni listas. Ignorá los portales agregadores genéricos (páginas tipo "
    "'AI News', 'LLM News Today', 'latest updates') y quedate con hechos concretos: "
    "lanzamientos, anuncios, fechas. Si no hay nada concreto, decilo en una frase.\n\n"
)


@router.get("/research/brief")
def research_brief(request: Request) -> dict:
    """Resumen corto del último digest, redactado por el cerebro (cacheado por digest)."""
    latest = research_latest(request)
    if not latest.get("available"):
        return {"available": False, "reason": latest.get("reason", "sin research")}
    name = latest["name"]
    if name not in _BRIEF_CACHE:
        brain = getattr(request.app.state.friday, "brain", None)
        if brain is None:
            return {"available": False, "reason": "sin cerebro configurado"}
        try:
            _BRIEF_CACHE[name] = (brain.compose(_BRIEF_PROMPT + latest["content"][:3500]) or "").strip()
        except Exception as exc:  # noqa: BLE001 — 429/red: el HUD muestra el digest igual
            logger.warning("Brief de research falló: %s", exc)
            return {"available": False, "reason": "no pude redactar el brief ahora"}
    return {"available": True, "name": name, "brief": _BRIEF_CACHE[name]}
