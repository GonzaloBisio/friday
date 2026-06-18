"""FRIDAY Wake — Activación por voz con saludo contextual.

Al decir "FRIDAY" (o presionar hotkey), FRIDAY responde con un saludo
de voz y lanza el sistema completo.

Dependencias opcionales (para micrófono):
  pip install SpeechRecognition pyaudio

Sin micrófono funciona con trigger manual: `friday-wake`
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Saludo contextual ────────────────────────────────────────────────────

_GREETINGS = {
    "morning": [
        "Buenos días, Gon. FRIDAY en línea.",
        "Buen día, Gonzalo. Sistema iniciado.",
        "Buenos días. Todo listo para arrancar.",
    ],
    "afternoon": [
        "Buenas tardes, Gon. FRIDAY activo.",
        "Buenas tardes, Gonzalo. ¿En qué te ayudo?",
        "Buenas tardes. Sistema operativo.",
    ],
    "night": [
        "Buenas noches, Gon. FRIDAY listo.",
        "Buenas noches, Gonzalo. Modo nocturno activo.",
        "Buenas noches. Monitoreo activado.",
    ],
}


def _time_of_day() -> str:
    h = datetime.now().hour
    if 6 <= h < 12:
        return "morning"
    elif 12 <= h < 19:
        return "afternoon"
    else:
        return "night"


def get_greeting() -> str:
    """Devuelve un saludo aleatorio según la hora del día."""
    import random
    tod = _time_of_day()
    return random.choice(_GREETINGS[tod])


# ── Text-to-Speech ───────────────────────────────────────────────────────

def speak(text: str) -> bool:
    """Habla el texto usando el mejor motor disponible.

    Prueba en orden: gTTS (online) → espeak → festival → spd-say → log.
    Retorna True si se reprodujo audio.
    """
    logger.info("FRIDAY dice: %s", text)

    # Intentar gTTS (Google TTS, necesita internet)
    if _try_gtts(text):
        return True

    # Intentar engines offline del sistema
    for cmd in [
        ["espeak-ng", "-v", "es", text],
        ["espeak", "-v", "es", text],
        ["festival", "--tts"],
        ["spd-say", "-l", "es", text],
    ]:
        if _try_command(cmd, text):
            return True

    logger.warning("No se pudo reproducir audio. Texto: %s", text)
    return False


def _try_gtts(text: str) -> bool:
    """Genera MP3 con gTTS y lo reproduce."""
    try:
        from gtts import gTTS
    except ImportError:
        return False

    import shutil

    mp3_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            mp3_path = f.name

        tts = gTTS(text=text, lang="es", slow=False)
        tts.save(mp3_path)

        # Buscar players disponibles en el sistema
        players: list[list[str]] = []
        for exe, flags in [
            ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
            ("mpg123", ["-q"]),
            ("mpg321", ["-q"]),
            ("cvlc", ["--play-and-exit", "--no-terminal"]),
            ("aplay", []),
            ("paplay", []),
            ("pw-play", []),
        ]:
            path = shutil.which(exe)
            if path:
                players.append([path] + flags)

        for cmd in players:
            try:
                full_cmd = cmd + [mp3_path]
                proc = subprocess.run(
                    full_cmd, timeout=15,
                    capture_output=True,
                )
                if proc.returncode == 0:
                    return True
            except Exception:
                continue

    except Exception as exc:
        logger.debug("gTTS falló: %s", exc)
    finally:
        if mp3_path:
            try:
                os.unlink(mp3_path)
            except OSError:
                pass

    return False


def _try_command(cmd: list[str], fallback_text: str) -> bool:
    """Intenta ejecutar un comando de TTS. Para festival manda texto por stdin."""
    import shutil
    try:
        exe = cmd[0]
        exe_path = shutil.which(exe)
        if not exe_path:
            return False

        full_cmd = [exe_path] + cmd[1:]
        if exe == "festival":
            proc = subprocess.run(
                full_cmd,
                input=fallback_text.encode(),
                timeout=10, capture_output=True,
            )
        else:
            proc = subprocess.run(full_cmd, timeout=10, capture_output=True)
        return proc.returncode == 0
    except Exception:
        return False


def _which(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None


# ── Wake word detection ──────────────────────────────────────────────────

def listen_for_wake(timeout: float = 60.0) -> bool:
    """Escucha el micrófono buscando 'friday' como wake word.

    Retorna True si detectó la palabra. Si no hay micrófono, retorna False.
    """
    try:
        import speech_recognition as sr
    except ImportError:
        logger.debug("speech_recognition no instalado")
        return False

    try:
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=1)
            logger.info("Escuchando wake word 'FRIDAY'...")
            audio = r.listen(source, timeout=timeout, phrase_time_limit=3)
    except Exception as exc:
        logger.debug("Micrófono no disponible: %s", exc)
        return False

    try:
        text = r.recognize_google(audio, language="es-ES").lower()
        logger.info("Reconocido: %s", text)
        return "friday" in text or "fráiday" in text
    except Exception as exc:
        logger.debug("No se reconoció: %s", exc)
        return False


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point de friday-wake. Saluda y lanza el sistema."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    greeting = get_greeting()
    speak(greeting)

    # Lanzar FRIDAY
    project_root = Path(__file__).resolve().parent.parent
    logger.info("Lanzando FRIDAY...")

    try:
        subprocess.Popen(
            [sys.executable, "-m", "friday.app"],
            cwd=str(project_root),
        )
        logger.info("FRIDAY lanzado en background")
    except Exception as exc:
        logger.error("Error lanzando FRIDAY: %s", exc)


if __name__ == "__main__":
    main()
