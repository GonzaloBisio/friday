"""Rutas REST de NEXCOURT — estado de auth AWS y re-login desde el dashboard.

GET  /api/nexcourt/auth   — ¿el collector necesita re-login (token AWS vencido)?
POST /api/nexcourt/login  — dispara `aws login` (configurable) y abre el navegador.

Cuando el token SSO vence, el CloudWatchCollector pausa (no martilla AWS ni spamea
tracebacks) y marca needs_login. El HUD muestra un botón que pega acá: lanza el
flujo de login en el navegador y resetea el cooldown para que el collector retome.
"""

from __future__ import annotations

import logging
import shlex
import subprocess

from fastapi import APIRouter, Request

from friday.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nexcourt"])


def _collector(request: Request):
    return getattr(request.app.state.friday, "nexcourt_collector", None)


@router.get("/nexcourt/auth")
def nexcourt_auth(request: Request) -> dict:
    """Estado de autenticación AWS del collector NEXCOURT."""
    col = _collector(request)
    if col is None:
        return {"available": False, "needs_login": False}
    # Solo el CloudWatchCollector (modo AWS) tiene noción de login; el modo direct no.
    needs = bool(getattr(col, "needs_login", False))
    return {"available": True, "needs_login": needs, "login_cmd": settings.nexcourt_aws_login_cmd}


@router.post("/nexcourt/login")
def nexcourt_login(request: Request) -> dict:
    """Lanza el comando de re-login AWS en segundo plano y resetea el cooldown.

    Best-effort: abre el navegador para el flujo SSO. Si el navegador no abre solo
    (WSL sin wslu), el usuario puede correr el comando a mano — el collector retoma
    igual en cuanto el token vuelve.
    """
    col = _collector(request)
    cmd = settings.nexcourt_aws_login_cmd
    try:
        # Detached: no bloqueamos la API esperando el login interactivo del browser.
        subprocess.Popen(shlex.split(cmd))
    except Exception as exc:  # noqa: BLE001
        logger.warning("No pude lanzar el login AWS (%s): %s", cmd, exc)
        return {"status": "error", "reason": str(exc), "cmd": cmd}

    # Que el collector reintente en el próximo ciclo en vez de esperar el cooldown.
    if col is not None and hasattr(col, "reset_auth"):
        col.reset_auth()

    return {
        "status": "started",
        "cmd": cmd,
        "detail": "Completá el login en el navegador; NEXCOURT se reconecta solo.",
    }
