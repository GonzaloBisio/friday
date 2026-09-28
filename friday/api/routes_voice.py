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


# ── Etapas de voz en vivo + control del listener (HUD) ─────────────────────
# El listener (otro proceso) reporta cada etapa del turno por POST y el backend la
# reemite por /ws/live: así el HUD anima el voice loop con datos reales (antes solo
# adivinaba el estado leyendo el log cada 3 s). El control va al revés: el HUD manda
# ajustes y el listener, suscripto al mismo WS, los aplica.

from pydantic import BaseModel, Field  # noqa: E402
from fastapi import Request  # noqa: E402

VOICE_STAGES = {"wake", "listening", "hearing", "stt", "thinking", "speaking", "muted", "idle"}
_VOICE_VOICES = ("michael", "charles", "george", "paul", "jean", "marius")

# Estado de control vigente (en memoria; el listener arranca con sus defaults y
# el HUD lo lee al conectar). Semilla: lo que dice la config.
_control: dict = {"muted": False, "voice": settings.tts_voice, "end_silence": 0.8}


class VoiceEvent(BaseModel):
    stage: str
    text: str | None = Field(default=None, max_length=2000)
    who: str | None = None            # "you" | "friday"
    timings: dict | None = None       # {"endpoint","stt","llm","tts_first","total"}


class VoiceControl(BaseModel):
    muted: bool | None = None
    voice: str | None = None
    end_silence: float | None = Field(default=None, ge=0.4, le=2.0)


@router.post("/voice/event")
def voice_event(request: Request, ev: VoiceEvent) -> JSONResponse:
    if ev.stage not in VOICE_STAGES:
        return JSONResponse({"status": "ignored", "reason": f"etapa desconocida: {ev.stage}"}, status_code=400)
    broadcast = request.app.state.friday.broadcast
    if broadcast is not None:
        broadcast.emit({"type": "voice", **ev.model_dump(exclude_none=True)})
    return JSONResponse({"status": "ok"})


@router.get("/voice/control")
def get_voice_control() -> JSONResponse:
    return JSONResponse({**_control, "voices": list(_VOICE_VOICES)})


@router.post("/voice/control")
def set_voice_control(request: Request, body: VoiceControl) -> JSONResponse:
    changes = body.model_dump(exclude_none=True)
    if "voice" in changes and changes["voice"] not in _VOICE_VOICES:
        return JSONResponse({"status": "error", "reason": f"voz desconocida: {changes['voice']}"}, status_code=400)
    _control.update(changes)
    broadcast = request.app.state.friday.broadcast
    if broadcast is not None:
        broadcast.emit({"type": "voice_control", **_control})
    return JSONResponse({"status": "ok", **_control})
