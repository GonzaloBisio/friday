"""Ruta REST de voz — expone el log del listener de voz (friday/voice/wake.py).

GET /api/voice/log?n=30 — últimas N líneas del log de voz (friday-wake.log).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from friday.config import settings

router = APIRouter(tags=["voice"])

_REPO_DIR = Path(__file__).resolve().parents[2]


def _voice_log_path() -> str:
    """FRIDAY_VOICE_LOG > settings.voices_dir > <repo>/voices (mismo host)."""
    if os.environ.get("FRIDAY_VOICE_LOG"):
        return os.environ["FRIDAY_VOICE_LOG"]
    voices = Path(settings.voices_dir) if settings.voices_dir else _REPO_DIR / "voices"
    return str(voices / "friday-wake.log")


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
