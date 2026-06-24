"""Ruta REST de voz — expone el log del listener de voz en Windows.

GET /api/voice/log?n=30 — últimas N líneas del log de voz (friday-wake.log).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(tags=["voice"])

# Ruta al log del listener de voz (Windows, accesible desde WSL vía /mnt/c).
_VOICE_LOG_DEFAULT = "/mnt/c/Users/gonza/friday/voices/friday-wake.log"


def _voice_log_path() -> str:
    return os.environ.get("FRIDAY_VOICE_LOG", _VOICE_LOG_DEFAULT)


@router.get("/voice/log")
def voice_log(n: int = Query(default=30, ge=1, le=200)) -> JSONResponse:
    """Devuelve las últimas N líneas del log de voz con estado detectado.

    El estado se infiere del contenido de las líneas:
    - "conversacion" o "escuchando" → listening
    - "Vos:" o "FRIDAY:" o "[tiempos]" → conversing
    - "Escuchando wake word" → waiting
    - sin actividad → idle
    """
    path = _voice_log_path()

    if not Path(path).exists():
        return JSONResponse({
            "status": "no_log",
            "lines": [],
            "state": "idle",
        })

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            all_lines = [ln.rstrip() for ln in f.readlines()]
    except OSError:
        return JSONResponse({
            "status": "error",
            "lines": [],
            "state": "idle",
        })

    recent = all_lines[-n:]

    # Detectar estado
    state = "idle"
    for ln in reversed(all_lines):
        lns = ln.strip()
        if "Te escucho" in lns or "escuchando tu voz" in lns:
            state = "listening"
            break
        if "[tiempos]" in lns or "FRIDAY:" in lns or "Vos:" in lns:
            state = "conversing"
            break
        if "Escuchando wake word" in lns:
            state = "waiting"
            break

    return JSONResponse({
        "status": "ok",
        "lines": recent,
        "state": state,
        "total_lines": len(all_lines),
    })
