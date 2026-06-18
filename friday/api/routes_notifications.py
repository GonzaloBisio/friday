"""Rutas REST de notificaciones.

GET  /api/notifications       — listar notificaciones activas.
POST /api/notifications/dismiss — dismiss una o todas.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["notifications"])


class DismissRequest(BaseModel):
    id: int | None = Field(default=None, description="ID de notificación (None = todas)")


@router.get("/notifications")
def list_notifications(request: Request, limit: int = 20) -> list[dict]:
    """Lista notificaciones activas (no dismiss)."""
    notif_repo = request.app.state.friday.notif_repo
    if notif_repo is None:
        return []

    notifs = notif_repo.list_recent(limit=limit)
    return [
        {
            "id": n.id,
            "level": n.level,
            "title": n.title,
            "message": n.message,
            "source": n.source,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifs
    ]


@router.post("/notifications/dismiss")
def dismiss_notification(request: Request, body: DismissRequest) -> dict:
    """Dismiss de una notificación o todas."""
    notif_repo = request.app.state.friday.notif_repo
    if notif_repo is None:
        return {"status": "error", "reason": "Repo no disponible"}

    if body.id is not None:
        ok = notif_repo.dismiss(body.id)
        return {"status": "ok" if ok else "not_found", "dismissed_id": body.id}
    else:
        count = notif_repo.dismiss_all()
        return {"status": "ok", "dismissed_count": count}
