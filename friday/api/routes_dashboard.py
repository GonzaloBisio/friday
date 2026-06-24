"""Sirve el dashboard web JARVIS (Pilar 4) — un único index.html estático.

Es el port vanilla del diseño de Claude Design: sin runtime externo ni build,
habla con la API + WebSocket de este mismo backend. Se sirve en la raíz para que
abrir http://127.0.0.1:8000/ muestre el Command Center. El dashboard Streamlit
(:8510) sigue intacto como red de seguridad hasta jubilarlo.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["dashboard"])

_INDEX = Path(__file__).resolve().parent.parent / "dashboard_web" / "index.html"


@router.get("/", response_class=HTMLResponse)
def command_center() -> FileResponse:
    """Devuelve el HUD del Command Center."""
    return FileResponse(_INDEX, media_type="text/html")
