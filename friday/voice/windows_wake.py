"""
FRIDAY Wake — Windows native.

Escucha la wake word "FRIDAY" por micrófono (offline, con Vosk),
saluda con voz Ryan (Piper TTS, offline, en inglés), lanza el
sistema FRIDAY en WSL y entra en modo conversación por voz:
transcribe lo que decís, lo manda al cerebro (API /chat) y
responde hablando, en loop, hasta "stop" o silencio.

Requiere (en Python 3.12):
    pip install vosk pyaudio piper-tts

Modelos (en C:\\Users\\gonza\\friday\\voices):
    - en_US-ryan-high.onnx (+ .onnx.json)   -> voz (Piper)
    - vosk-model-small-en-us-0.15           -> reconocimiento (Vosk)
"""

import os
import re
import sys
import json
import time
import wave
import string
import socket
import random
import collections
import tempfile
import threading
import webbrowser
import subprocess
from datetime import datetime

from piper import PiperVoice

try:  # Piper 1.x: length_scale viaja en SynthesisConfig, no como kwarg.
    from piper import SynthesisConfig
except ImportError:  # Piper viejo no lo tiene.
    SynthesisConfig = None

# ── Rutas ──────────────────────────────────────────────────────────
VOICES_DIR = r"C:\Users\gonza\friday\voices"
PIPER_MODEL = os.path.join(VOICES_DIR, "en_US-ryan-high.onnx")
VOSK_MODEL = os.path.join(VOICES_DIR, "vosk-model-small-en-us-0.15")
LOG_FILE = os.path.join(VOICES_DIR, "friday-wake.log")
# Sample de referencia para clonar la voz de Jarvis con Pocket TTS.
# Generado desde el MP3 mejorado (Adobe Podcast) — clip limpio de ~9s.
JARVIS_REF = os.path.join(VOICES_DIR, "jarvis.wav")

# Evita que los subprocess hagan parpadear ventanas de consola (modo oculto).
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# ── Wake word ──────────────────────────────────────────────────────
# Vocabulario restringido: Vosk solo intenta reconocer estas palabras,
# lo que hace la detección casi instantánea y muy precisa.
GRAMMAR = json.dumps(["friday", "hey", "wake up", "[unk]"])
# Si el texto reconocido contiene "friday", se dispara.
TRIGGER = "friday"

# Streamlit legacy (solo si se levanta con `friday --streamlit`). Lo dejamos por
# compat, pero el dashboard que se abre al activar es el HUD nuevo (abajo).
DASHBOARD_PORT = 8510

# API REST de FRIDAY (para conversar). Alcanzable desde Windows vía WSL mirrored.
# 127.0.0.1 (no "localhost") para forzar IPv4 y evitar el timeout de IPv6 (::1).
API_PORT = 8000
API_URL = f"http://127.0.0.1:{API_PORT}/api"

# El dashboard que abre el wake word es el Command Center (HUD JARVIS), servido
# por la MISMA API en la raíz (puerto 8000) — no el Streamlit viejo (8510).
HUD_URL = f"http://127.0.0.1:{API_PORT}/"
DASHBOARD_URL = HUD_URL

# ── Canal proactivo (Pilar 1) ──────────────────────────────────────
# El backend empuja eventos {"type":"proactive",...} por este WebSocket cuando
# algo cruza un umbral (servicio caído, CPU crítica, gasto). El listener corre
# en un thread aparte: muestra un toast SIEMPRE y, si speak=True y no hay una
# conversación en curso, lo dice con la voz Jarvis.
WS_URL = f"ws://127.0.0.1:{API_PORT}/ws/live"
# Timeout de recv() holgado: MAYOR que la cadencia de métricas del backend (~10s)
# para no confundir un silencio normal con una caída. Si pasa este tiempo sin
# NINGÚN mensaje, mandamos un "ping" de keepalive (el server responde "pong") en
# vez de reconectar. Reconectar es solo para caídas REALES del socket.
PROACTIVE_RECV_TIMEOUT = 35

# Serializa TODA reproducción por `speak()` (saludos, salidas, y voz proactiva)
# para que dos SoundPlayer nunca se pisen entre el thread del mic y el del WS.
_audio_lock = threading.Lock()
# Marca que hay una conversación activa: mientras esté seteado, la voz proactiva
# CEDE el canal (igual muestra el toast) para no hablar encima tuyo ni meter eco
# en el micrófono. El toast nunca molesta; la voz sí, por eso se coordina.
_conversation_active = threading.Event()

# ── Voz Jarvis: Pocket TTS (Kyutai) — local, CPU, clonado de voz ───
# Reemplaza a XTTS/GPU. Corre en el MISMO proceso del listener (no hay
# sidecar ni hop de red): ~200ms al primer audio, ~6x realtime en CPU,
# 148MB. Clona la voz desde JARVIS_REF. Si falla la carga, _synthesize
# cae a Piper/Ryan (local). Modelo y voz se cargan UNA vez (lazy).
_pocket = None        # instancia de TTSModel
_pocket_voice = None  # voice_state del clon Jarvis (de JARVIS_REF)

# ── STT conversación: faster-whisper (local, CPU) ──────────────────
# Vosk se usa solo para la wake word y como VAD/endpointer. La transcripción
# del habla libre la hace Whisper: MUCHO mejor con acento no nativo. CPU int8
# (~1s por frase corta); GPU descartado por el lío de DLLs CUDA en Windows.
# small.en va bien; si querés más precisión, subí a "medium.en" (más lento).
WHISPER_MODEL = "small.en"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE = "int8"
_whisper = None       # instancia de WhisperModel (lazy)

# ── Conversación por voz ───────────────────────────────────────────
# Tras la wake word, FRIDAY entra en modo conversación: escucha tu
# consulta, la manda al cerebro y responde con voz, en loop.
CONV_SILENCE_TIMEOUT = 60  # seg sin hablar -> vuelve a esperar "friday"

# ── Endpointing por silencio (reemplaza el endpoint ansioso de Vosk) ──────────
# El problema: Vosk cerraba el turno apenas hacías una pausa natural y te cortaba
# a mitad de frase. Ahora medimos energía del mic (RMS) y solo cerramos el turno
# tras END_SILENCE_S de silencio SOSTENIDO. Así tolera pausas para pensar.
END_SILENCE_S = 1.3       # silencio sostenido (seg) para dar por terminado el turno
MIN_SPEECH_S = 0.4        # mínimo de habla para que un turno cuente (filtra ruidos)
PREROLL_CHUNKS = 2        # chunks previos al inicio de voz (para no clipear la 1ra sílaba)
_VAD_MARGIN = 2.2         # umbral de voz = piso_de_ruido * margen
_VAD_FLOOR_MIN = 180.0    # umbral mínimo absoluto (RMS int16), por si el ambiente es muy callado


def _rms(data: bytes) -> float:
    """Energía RMS de un bloque PCM int16. Sirve de VAD simple (voz vs silencio)."""
    import numpy as np

    arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(arr * arr))) if arr.size else 0.0
EXIT_WORDS = (
    "stop", "goodbye", "good bye", "bye", "exit",
    "that's all", "thats all", "never mind",
)
# Palabras que apagan TODO el sistema (FRIDAY + Ollama + listener).
SHUTDOWN_WORDS = (
    "shutdown", "shut down", "power off", "turn off",
    "kill yourself", "terminate",
)
# MUTE: silencia a FRIDAY (no habla) y deja de procesarte, hasta "unmute".
# Mientras está muteado se escucha SOLO la palabra de reactivación con una
# gramática Vosk restringida (instantáneo, sin gastar Whisper) — igual que la
# wake word.
#
# ⚠️ "unmute" NO funciona: Vosk small.en-0.15 no la tiene en su vocabulario
# (no es palabra real en inglés) y la rechaza con "Ignoring word missing in
# vocabulary". Por eso se usa "resume", palabra común que Vosk sí reconoce.
MUTE_WORDS = ("mute",)
UNMUTE_GRAMMAR = json.dumps(["resume", "[unk]"])
UNMUTE_TRIGGER = "resume"

# ── Saludos (en inglés, estilo Jarvis) ─────────────────────────────
# Varios por franja para que el arranque no se sienta robótico ni monótono:
# get_greeting() elige uno al azar. Cortos a propósito (los lee el TTS).
GREETINGS = {
    "morning": [
        "Good morning, sir. FRIDAY online and at your service.",
        "Good morning, Gonzalo. All systems nominal and ready.",
        "Morning, sir. Everything's up and running.",
        "Rise and shine, sir. FRIDAY's awake and standing by.",
        "Good morning, sir. Coffee's your department; the rest is mine.",
        "Morning, sir. Systems green across the board.",
    ],
    "afternoon": [
        "Good afternoon, sir. FRIDAY at your service.",
        "Afternoon, sir. Ready whenever you are.",
        "Good afternoon, Gonzalo. All systems running smoothly.",
        "Afternoon, sir. Back in action and standing by.",
        "Good afternoon, sir. What are we tackling?",
    ],
    "night": [
        "Good evening, sir. FRIDAY standing by.",
        "Evening, sir. Systems quiet and ready.",
        "Good evening, Gonzalo. Night mode engaged.",
        "Evening, sir. Burning the midnight oil, are we?",
        "Good evening, sir. At your service, as always.",
    ],
}

# Re-activaciones (cuando ya saludó una vez): cortas y variadas, sin repetir
# el saludo completo. Antes era siempre "Sir?" — monótono.
ACK_GREETINGS = [
    "Sir?",
    "Yes, sir?",
    "At your service.",
    "Listening, sir.",
    "Go ahead, sir.",
]


def log(msg):
    """Escribe a archivo siempre, y a consola si existe (modo visible)."""
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    if sys.stdout is not None:  # None cuando corre oculto (pythonw)
        try:
            print(line)
        except Exception:
            pass


def get_greeting():
    h = datetime.now().hour
    if 6 <= h < 12:
        tod = "morning"
    elif 12 <= h < 19:
        tod = "afternoon"
    else:
        tod = "night"
    return random.choice(GREETINGS[tod])


def _load_pocket():
    """Carga Pocket TTS + el estado de voz Jarvis UNA sola vez. None si falla.

    El modelo (148MB) se baja la primera vez. get_state_for_audio_prompt procesa
    el clip JARVIS_REF y devuelve el voice_state del clon, que se reusa siempre.
    """
    global _pocket, _pocket_voice
    if _pocket is not None:
        return _pocket
    try:
        from pocket_tts import TTSModel
        t0 = time.time()
        _pocket = TTSModel.load_model()
        _pocket_voice = _pocket.get_state_for_audio_prompt(JARVIS_REF)
        log(f"Pocket TTS cargado (voz Jarvis clonada) en {time.time() - t0:.1f}s.")
    except Exception as e:  # noqa: BLE001 — si falla, se usa Piper/Ryan
        log(f"No pude cargar Pocket TTS: {e!r} — usaré Piper/Ryan.")
        _pocket = None
    return _pocket


def _load_whisper():
    """Carga faster-whisper UNA sola vez. None si falla (cae a Vosk)."""
    global _whisper
    if _whisper is not None:
        return _whisper
    try:
        from faster_whisper import WhisperModel
        t0 = time.time()
        _whisper = WhisperModel(
            WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE
        )
        log(f"faster-whisper '{WHISPER_MODEL}' cargado en {time.time() - t0:.1f}s.")
    except Exception as e:  # noqa: BLE001 — si falla, se usa Vosk como fallback
        log(f"No pude cargar faster-whisper: {e!r} — usaré Vosk.")
        _whisper = None
    return _whisper


def _transcribe(audio_bytes):
    """Transcribe audio PCM int16 16kHz mono con Whisper. '' si no está disponible."""
    if _load_whisper() is None:
        return ""
    try:
        import numpy as np

        arr = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = _whisper.transcribe(arr, language="en")
        return " ".join(s.text for s in segments).strip()
    except Exception as e:  # noqa: BLE001 — ante fallo, el caller usa Vosk
        log(f"  Whisper error: {e!r}")
        return ""


# Pocket TTS chunkea internamente a 50 tokens y SALTEA palabras si te pasás
# ("Chunk has 51 tokens... may skip words"). Partimos el texto en bloques bajo
# ~40 tokens estimados y concatenamos el audio. Ojo: los números ("3,495,935")
# tokenizan en MUCHOS tokens, por eso estimamos tokens y no palabras.
_TTS_MAX_TOKENS = 35


def _est_tokens(s):
    """Estimación grosera de tokens: palabras + signos de puntuación por separado."""
    return len(re.findall(r"\w+|[^\w\s]", s))


def _split_for_tts(text, max_tokens=_TTS_MAX_TOKENS):
    """Parte el texto en bloques < max_tokens, por oración → coma → palabra."""
    # 1) piezas atómicas que de por sí no superen el tope.
    atoms = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        if not sent:
            continue
        if _est_tokens(sent) <= max_tokens:
            atoms.append(sent)
            continue
        for clause in re.split(r"(?<=,)\s+", sent):  # subdividir por comas
            if _est_tokens(clause) <= max_tokens:
                atoms.append(clause)
                continue
            cur = []  # último recurso: por palabras
            for w in clause.split():
                if cur and _est_tokens(" ".join(cur + [w])) > max_tokens:
                    atoms.append(" ".join(cur))
                    cur = [w]
                else:
                    cur.append(w)
            if cur:
                atoms.append(" ".join(cur))
    # 2) empaquetar átomos consecutivos sin pasar el tope.
    chunks, cur = [], ""
    for a in atoms:
        cand = (cur + " " + a).strip()
        if cur and _est_tokens(cand) > max_tokens:
            chunks.append(cur)
            cur = a
        else:
            cur = cand
    if cur:
        chunks.append(cur)
    return chunks or [text]


def _pocket_synthesize(text, wav_path):
    """Sintetiza con Pocket TTS (voz Jarvis clonada, local/CPU). True si escribió.

    Escribe WAV PCM int16 con la stdlib (no scipy): Media.SoundPlayer de Windows
    solo reproduce PCM, un WAV float saldría mudo. Convierte float[-1,1]→int16.
    Parte el texto en bloques cortos para no superar el límite de Pocket TTS.
    """
    if _load_pocket() is None:
        return False
    try:
        import numpy as np

        pieces = []
        for chunk in _split_for_tts(text):
            audio = _pocket.generate_audio(_pocket_voice, chunk)
            a = audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio)
            pieces.append(np.squeeze(a))  # (1, N) → (N,)
        arr = np.concatenate(pieces) if len(pieces) > 1 else pieces[0]
        if arr.dtype.kind == "f":
            arr = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)
        elif arr.dtype != np.int16:
            arr = arr.astype(np.int16)

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16
            wf.setframerate(int(_pocket.sample_rate))
            wf.writeframes(arr.tobytes())
        return True
    except Exception as e:  # noqa: BLE001 — cualquier fallo → fallback a Piper
        log(f"  Pocket TTS error: {e!r}")
        return False


def _synthesize(text, voice, wav_path=None):
    """Genera el WAV. Voz Jarvis (Pocket TTS local/CPU); si falla, Piper/Ryan.

    wav_path: ruta de salida. Si es None usa una fija.
    En el fallback soporta piper-tts viejo y nuevo (con/sin synthesize_wav).
    """
    wav = wav_path or os.path.join(tempfile.gettempdir(), "friday_voice.wav")

    # 1. Voz Jarvis clonada con Pocket TTS (local, CPU, ~200ms al primer audio).
    if _pocket_synthesize(text, wav):
        log("  [voz] Jarvis (Pocket TTS)")
        return wav

    # 2. Fallback: Piper/Ryan local (por si Pocket TTS no cargó).
    log("  [voz] Ryan (Piper) — Pocket TTS no disponible")
    # Piper 1.x: synthesize_wav() escribe header + frames y setea el formato
    # del WAV (canales/sample rate) solo. synthesize() devuelve un iterable
    # de AudioChunk y NO toca el wave file → dejaba el WAV vacío y close()
    # explotaba con "# channels not specified".
    if hasattr(voice, "synthesize_wav"):
        syn_config = (
            SynthesisConfig(length_scale=1.08) if SynthesisConfig else None
        )
        wf = wave.open(wav, "w")
        try:
            voice.synthesize_wav(text, wf, syn_config)
        finally:
            wf.close()
        return wav

    # Fallback Piper viejo: synthesize(text, wave_file) escribía directo.
    wf = wave.open(wav, "w")
    try:
        voice.synthesize(text, wf)
    finally:
        wf.close()
    return wav


def _play_wav_async(wav):
    """Reproduce WAV en Windows sin bloquear a Python. Retorna el Popen.

    Usa PlaySync() (no Play()): Play() reproduce en un thread de fondo y el
    `powershell -c` termina al instante, MATANDO el audio antes de que suene
    (por eso la conversación se veía en el log pero no se escuchaba). PlaySync()
    mantiene vivo el proceso de PowerShell hasta que el audio termina; como corre
    dentro de un Popen, Python no se bloquea y `player.poll()` sigue devolviendo
    None mientras suena — justo lo que necesita el loop de interrupción.
    """
    ps = f'(New-Object Media.SoundPlayer "{wav}").PlaySync()'
    return subprocess.Popen(
        ["powershell", "-c", ps],
        creationflags=NO_WINDOW,
    )


def _stop_player(player):
    """Mata el proceso de reproducción de audio."""
    try:
        player.kill()
        player.wait(timeout=2)
    except Exception:
        pass


def speak(text, voice):
    """Genera y reproduce voz de forma bloqueante (para saludos y despedidas).

    Toma `_audio_lock` alrededor de síntesis+reproducción: como la voz proactiva
    (otro thread) también pasa por acá, el lock evita que dos audios se solapen.
    """
    with _audio_lock:
        wav = _synthesize(text, voice)
        ps = f'(New-Object Media.SoundPlayer "{wav}").PlaySync()'
        subprocess.run(["powershell", "-c", ps], capture_output=True,
                       creationflags=NO_WINDOW)


# Anti-eco: mientras FRIDAY habla, el mic capta su PROPIA voz (eco acústico) y Vosk
# transcribía basura corta ("spencer", "fathers") → falsa interrupción. Endurecemos:
# (1) grace period inicial (ignorar el arranque del audio), (2) SOLO resultados
# COMPLETOS de Vosk (no parciales), (3) con sustancia real (>= MIN chars). Lo ideal
# sería AEC o auriculares, pero esto corta el 95% de los falsos positivos.
INTERRUPT_GRACE_S = 0.8
INTERRUPT_MIN_CHARS = 5


def _play_with_interrupt(wav, stream, model):
    """Reproduce un WAV escuchando si el usuario interrumpe. True si interrumpió."""
    from vosk import KaldiRecognizer

    player = _play_wav_async(wav)
    interrupt_rec = KaldiRecognizer(model, 16000)
    start = time.time()

    while player.poll() is None:
        try:
            chunk = stream.read(2000, exception_on_overflow=False)
        except OSError:
            break

        final = interrupt_rec.AcceptWaveform(chunk)
        # Durante el grace inicial consumimos audio pero no actuamos (es el eco del TTS).
        if time.time() - start < INTERRUPT_GRACE_S:
            continue
        if final:
            spoken = json.loads(interrupt_rec.Result()).get("text", "").strip()
            if len(spoken) >= INTERRUPT_MIN_CHARS:
                log(f"  [interrupción] '{spoken}'")
                _stop_player(player)
                return True
    return False


def _matches_any(text, phrases):
    """True si el texto contiene alguna de las frases.

    Palabras sueltas → match de palabra COMPLETA (no substring), para no cortar
    la charla si 'bye'/'stop'/'exit' aparecen dentro de otra palabra o de una
    transcripción larga. Frases con espacio → substring.

    Whisper agrega puntuación ("mute.", "stop!"), así que limpiamos cada token:
    sin esto, "mute" nunca matcheaba contra "mute." y el comando se iba al cerebro.
    """
    words = {w.strip(string.punctuation) for w in text.split()}
    for ph in phrases:
        if " " in ph:
            if ph in text:
                return True
        elif ph in words:
            return True
    return False


def is_running(port=DASHBOARD_PORT, host="127.0.0.1"):
    """True si el puerto está escuchando (check TCP rápido)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def api_ready(timeout=40):
    """Espera a que la API REST responda de VERDAD (HTTP GET /api/status).

    A diferencia de is_running (solo TCP connect), esto verifica que el
    servidor HTTP esté sirviendo — no solo que el puerto esté abierto.
    Evita falsos positivos: si FRIDAY arranca, binda el puerto y crashea
    0.5s después, is_running diría True pero la API no responde.
    """
    import urllib.request, urllib.error
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{API_URL}/status", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(1)
    return False


def launch_friday():
    """Lanza FRIDAY en WSL (el comando `wsl` auto-inicia la distro).

    La voz Jarvis ahora corre LOCAL en Windows (Pocket TTS en este mismo
    proceso), así que acá solo se levanta el backend: Ollama + FRIDAY (API +
    dashboard). Ya no hay sidecar TTS en WSL.
    """
    subprocess.Popen([
        "wsl", "-d", "Ubuntu", "--", "bash", "-c",
        # Asegurar Ollama ANTES de arrancar FRIDAY: si no, el cerebro local
        # queda sin backend y responde el mensaje offline. pgrep -x evita
        # arrancar un segundo `ollama serve` si ya está corriendo.
        "pgrep -x ollama >/dev/null 2>&1 || (ollama serve >/dev/null 2>&1 &) ; "
        "cd /home/gonzalo/dev/personal/friday && ./venv/bin/friday",
    ], creationflags=NO_WINDOW)


def open_dashboard(timeout=40):
    """Espera a que la API esté SIRVIENDO y abre el HUD (Command Center).

    Usa api_ready (GET /api/status real, no solo TCP) porque el HUD lo sirve la
    misma API: si responde /api/status, la raíz / con el dashboard también está.
    """
    if api_ready(timeout):
        webbrowser.open(HUD_URL)
        log(f"  Abriendo HUD {HUD_URL}")
    else:
        log(f"  La API no respondió en {timeout}s; abro el HUD igual.")
        webbrowser.open(HUD_URL)


def wait_api_ready(timeout=40):
    """Espera a que la API REST de FRIDAY (puerto 8000) esté lista."""
    start = time.time()
    while time.time() - start < timeout:
        if is_running(API_PORT):
            return True
        time.sleep(1)
    return False


def ask_friday(message, timeout=120):
    """Manda el mensaje a la API de FRIDAY y devuelve la respuesta en texto."""
    import urllib.request

    data = json.dumps({"message": message, "model": "auto"}).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL}/chat", data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()).get("response", "")


def _set_light(state):
    """Fire-and-forget: empuja el estado de voz a la API para las luces IR.

    Las luces son feedback cosmético: corre en un thread daemon y traga TODO
    error. Si la API o el emisor están caídos, el loop de voz NO se entera.
    """
    def _post():
        try:
            import urllib.request
            data = json.dumps({"state": state}).encode("utf-8")
            req = urllib.request.Request(
                f"{API_URL}/lights/state", data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=2).close()
        except Exception:
            pass

    threading.Thread(target=_post, daemon=True).start()


def shutdown_systems():
    """Apaga FRIDAY (API + dashboard + scheduler), Ollama y libera RAM de WSL2.

    Mata TODOS los procesos relacionados a friday sin importar cómo fueron
    arrancados (`python -m friday.app` o `./venv/bin/friday`), usando un
    script externo para evitar que pkill -f mate al shell que ejecuta los
    comandos (footgun clásico cuando el patrón aparece en la propia línea
    de comando del bash -c).

    Retorna True si se pudo matar todo, False si hubo error.
    """
    log("⚡ SHUTDOWN: apagando todo...")

    # 1. Kill graceful (best-effort). Mata FRIDAY + Ollama via script externo
    #    para que SQLite/Piper flusheen prolijo. NO es crítico para liberar
    #    RAM: el paso 2 (wsl --shutdown) mata todo lo de adentro igual.
    #    Por eso va blindado: si se cuelga o falla, NO debe impedir el paso 2.
    SHUTDOWN_SCRIPT = "/home/gonzalo/dev/personal/friday/friday/voice/shutdown_friday.sh"
    log("  → Matando FRIDAY + Ollama (graceful)...")
    try:
        r1 = subprocess.run(
            ["wsl", "-d", "Ubuntu", "--", "bash", SHUTDOWN_SCRIPT],
            capture_output=True, text=True, timeout=10,
        )
        if "done" in (r1.stdout or ""):
            log("  ✓ FRIDAY (API + Dashboard) + Ollama apagados")
        else:
            log(f"  ⚠ shutdown_friday.sh: sin 'done' (stdout={r1.stdout!r} stderr={r1.stderr!r})")
    except subprocess.TimeoutExpired:
        log("  ⚠ graceful kill se colgó — sigo igual al paso 2 (wsl --shutdown)")
    except Exception as e:  # noqa: BLE001 — nada puede frenar el paso 2
        log(f"  ⚠ graceful kill error: {e!r} — sigo igual al paso 2")

    # 2. PASO CRÍTICO — Liberar la RAM de VmmemWSL.
    #    VmmemWSL es el proceso HOST de Windows que sostiene la VM de WSL2.
    #    Matar procesos ADENTRO de WSL (paso 1) NO le devuelve la RAM a
    #    Windows: WSL2 se la queda. La ÚNICA forma de que VmmemWSL baje a ~0
    #    es apagar la VM entera. Esto mata TODO lo de adentro (Friday,
    #    dashboard, modelo, Ollama) de un saque y libera los GB reservados.
    #    Por eso este paso SIEMPRE corre, pase lo que pase en el paso 1.
    log("  → Liberando RAM de WSL2 (wsl --shutdown)...")
    ok = False
    try:
        r2 = subprocess.run(
            ["wsl", "--shutdown"],
            capture_output=True, text=True, timeout=30,
        )
        if r2.returncode == 0:
            log("  ✓ wsl --shutdown OK")
            ok = True
        else:
            log(f"  ⚠ wsl --shutdown falló (código {r2.returncode}, stderr={r2.stderr!r})")
    except Exception as e:  # noqa: BLE001
        log(f"  ✗ wsl --shutdown error: {e!r}")

    # 3. Verificar que NINGUNA distro siga corriendo (= VmmemWSL bajando).
    #    Si quedó alguna viva, reintentamos una vez.
    try:
        chk = subprocess.run(
            ["wsl", "--list", "--running"],
            capture_output=True, text=True, timeout=10,
        )
        # WSL devuelve UTF-16; capture_output+text suele dar texto con NULs.
        running = (chk.stdout or "").replace("\x00", "").strip()
        # La primera línea es un encabezado ("Distribuciones... en ejecución").
        still_up = [ln for ln in running.splitlines()[1:] if ln.strip()]
        if still_up:
            log(f"  ⚠ distros aún vivas: {still_up} — reintento wsl --shutdown")
            subprocess.run(["wsl", "--shutdown"], capture_output=True,
                           text=True, timeout=30)
            ok = True  # se mandó el shutdown igual
        else:
            log("  ✓ VmmemWSL apagado — RAM liberada")
            ok = True
    except Exception as e:  # noqa: BLE001
        log(f"  ⚠ no pude verificar distros corriendo: {e!r}")

    return ok


def _muted_wait(stream, model):
    """Bloquea en modo MUTE: ignora todo lo que digas y escucha SOLO 'unmute'.

    Usa una gramática Vosk restringida (como la wake word): no consume Whisper
    ni consulta al cerebro, y no hay timeout — se queda muteado indefinidamente
    hasta que digas 'unmute'. Sin tiempo de silencio que lo saque solo.
    """
    from vosk import KaldiRecognizer

    rec = KaldiRecognizer(model, 16000, UNMUTE_GRAMMAR)
    if stream.is_stopped():
        stream.start_stream()
    log("  [mute] MUTEADO — solo escucho 'resume'.")
    while True:
        try:
            data = stream.read(4000, exception_on_overflow=False)
        except OSError:
            continue
        if not rec.AcceptWaveform(data):
            continue
        text = json.loads(rec.Result()).get("text", "").lower()
        if UNMUTE_TRIGGER in text:
            log("  [mute] RESUME detectado — vuelvo a escuchar.")
            return


def _calibrate_vad(stream):
    """Mide el piso de ruido (~0.75s) y fija el umbral de voz para el endpointer."""
    samples = []
    for _ in range(3):
        try:
            samples.append(_rms(stream.read(4000, exception_on_overflow=False)))
        except OSError:
            pass
    floor = sorted(samples)[len(samples) // 2] if samples else 0.0
    threshold = max(floor * _VAD_MARGIN, _VAD_FLOOR_MIN)
    log(f"  [vad] piso de ruido ~{floor:.0f}, umbral de voz {threshold:.0f}")
    return threshold


def _listen_turn(stream, model, vad_threshold):
    """Escucha UNA elocución con endpointing por SILENCIO sostenido.

    Acumula audio mientras detecta voz (RMS > umbral) y cierra el turno recién
    tras END_SILENCE_S de silencio — así una pausa para pensar NO te corta. La
    transcripción la hace Whisper (mejor con acento); Vosk queda como fallback.

    Returns:
        (text, stt_dt, spoke). text=None si pasó CONV_SILENCE_TIMEOUT sin hablar;
        text="" si fue un ruido demasiado corto (el caller hace continue).
    """
    preroll = collections.deque(maxlen=PREROLL_CHUNKS)
    frames = bytearray()
    speech_started = False
    speech_start = last_voice = 0.0
    idle_start = time.time()

    while True:
        try:
            data = stream.read(4000, exception_on_overflow=False)
        except OSError:
            continue
        now = time.time()
        voiced = _rms(data) > vad_threshold

        if not speech_started:
            preroll.append(data)
            if voiced:
                speech_started = True
                speech_start = last_voice = now
                frames = bytearray(b"".join(preroll))  # incluir pre-roll, no clipear
                log("  [conversacion] escuchando tu voz...")
            elif now - idle_start > CONV_SILENCE_TIMEOUT:
                return None, 0.0, 0.0
            continue

        frames += data
        if voiced:
            last_voice = now
        elif now - last_voice >= END_SILENCE_S:
            break  # silencio sostenido → fin del turno

    spoke = last_voice - speech_start
    if spoke < MIN_SPEECH_S:
        return "", 0.0, 0.0  # ruido corto, no es un turno real

    t_stt = time.time()
    text = (_transcribe(bytes(frames)) or "").strip().lower()
    if not text:  # fallback Vosk si Whisper no devolvió nada
        from vosk import KaldiRecognizer
        r = KaldiRecognizer(model, 16000)
        r.AcceptWaveform(bytes(frames))
        text = json.loads(r.FinalResult()).get("text", "").strip().lower()
    return text, time.time() - t_stt, spoke


def conversation_loop(stream, model, voice):
    """Marca el canal de audio ocupado y delega al loop real.

    Mientras dura la conversación, `_conversation_active` está seteado y la voz
    proactiva (otro thread) CEDE — solo muestra toasts, no habla encima. El
    finally garantiza liberar el flag aunque el loop salga por return o excepción.
    """
    _conversation_active.set()
    try:
        return _run_conversation(stream, model, voice)
    finally:
        _conversation_active.clear()


def _run_conversation(stream, model, voice):
    """Conversación por voz continua: escucha, consulta al cerebro, responde.

    Usa endpointing por SILENCIO (energía del mic), no el endpoint ansioso de Vosk
    que cortaba a mitad de frase. Termina al decir una palabra de salida o tras un
    silencio prolongado.
    """
    if stream.is_stopped():
        stream.start_stream()
    log("  [conversacion] Te escucho... (deci 'stop' para terminar)")
    vad_threshold = _calibrate_vad(stream)
    last_activity = time.time()

    while True:
        _set_light("listening")  # celeste: te estoy escuchando
        text, stt_dt, spoke = _listen_turn(stream, model, vad_threshold)
        if text is None:
            log("  [conversacion] silencio; vuelvo a esperar 'friday'.")
            _set_light("idle")  # blanco cálido: vuelta al reposo
            return
        if not text:
            continue
        last_activity = time.time()
        log(f"  Vos: {text}  [habla {spoke:.1f}s | STT {stt_dt:.1f}s]")

        if _matches_any(text, SHUTDOWN_WORDS):
            stream.stop_stream()
            log("⚡ SHUTDOWN detectado. Apagando todo...")
            return "shutdown"

        if _matches_any(text, EXIT_WORDS):
            stream.stop_stream()
            speak("Goodbye, sir.", voice)
            _set_light("idle")
            return

        if _matches_any(text, MUTE_WORDS):
            # Confirmación corta con el stream parado (evita captar el eco),
            # luego silencio total hasta que digas 'unmute'.
            stream.stop_stream()
            speak("Muted, sir. Say resume to bring me back.", voice)
            _muted_wait(stream, model)        # bloquea hasta 'resume'
            stream.stop_stream()
            speak("I'm back, sir.", voice)
            stream.start_stream()
            last_activity = time.time()
            continue

        # ── Consultar al cerebro ──────────────────────────────────────
        _set_light("thinking")  # procesando (preset opcional)
        t = time.time()
        try:
            answer = ask_friday(text)
        except Exception as exc:
            log(f"  error API: {exc}")
            answer = "I couldn't reach my brain right now, sir."
        llm_dt = time.time() - t
        answer = (answer or "").strip() or "I have no answer for that, sir."
        log(f"  FRIDAY: {answer}")

        # ── Responder con voz (Pocket TTS ~200ms) + interrupción ──────
        _set_light("responding")  # ámbar/dorado: FRIDAY hablando
        t_tts = time.time()
        wav = _synthesize(answer, voice)
        interrupted = _play_with_interrupt(wav, stream, model)
        tts_dt = time.time() - t_tts

        if interrupted:
            # "Yes?" rápido y volver a escuchar
            ack_wav = _synthesize("Yes?", voice)
            ack_player = _play_wav_async(ack_wav)
            ack_player.wait(timeout=2)
            log("  [conversacion] interrumpido. Te escucho...")
        else:
            log(f"  [tiempos] LLM {llm_dt:.1f}s | TTS {tts_dt:.1f}s")

        last_activity = time.time()


# ── Canal proactivo: toast + listener WebSocket ────────────────────
def _ps_escape(s):
    """Sanitiza un string para incrustarlo en un literal PowerShell de comillas dobles."""
    return (s or "").replace("`", "").replace('"', "'").replace("\n", " ").strip()


def _show_toast(title, message):
    """Muestra un toast nativo de Windows (WinRT vía PowerShell, sin dep nueva).

    Best-effort: si el toast falla (perfil raro de Windows, permisos), se loguea
    y se sigue — la voz ya cubre lo crítico. No queremos que un toast tumbe el
    listener.
    """
    title_e = _ps_escape(title) or "FRIDAY"
    message_e = _ps_escape(message)
    ps = (
        '[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;'
        '[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;'
        '[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;'
        '$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);'
        '$x = $t.GetElementsByTagName("text");'
        f'$x.Item(0).AppendChild($t.CreateTextNode("{title_e}")) | Out-Null;'
        f'$x.Item(1).AppendChild($t.CreateTextNode("{message_e}")) | Out-Null;'
        '$toast = [Windows.UI.Notifications.ToastNotification]::new($t);'
        '$n = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("FRIDAY");'
        '$n.Show($toast);'
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, creationflags=NO_WINDOW, timeout=8,
        )
    except Exception as e:  # noqa: BLE001
        log(f"  [proactivo] toast falló: {e!r}")


def _handle_proactive(data, voice):
    """Actúa un evento proactivo: toast SIEMPRE; voz solo si speak y no hay charla."""
    text = (data.get("text") or "").strip()
    title = data.get("title") or "FRIDAY"
    message = data.get("message") or text
    log(f"  [proactivo] {data.get('level','?')}: {title}")

    _show_toast(title, message)

    # La voz CEDE ante una conversación activa: el toast ya quedó, no hablamos
    # encima. `speak()` toma `_audio_lock`, así que no se solapa con otro audio.
    if data.get("speak") and text and not _conversation_active.is_set():
        speak(text, voice)


def proactive_listener(voice):
    """Thread de fondo: se suscribe al WS del backend y actúa eventos proactivos.

    Reconecta solo si el backend todavía no levantó o se cae la conexión. Si la
    lib `websocket-client` no está instalada en el Python de Windows, loguea y el
    thread termina silenciosamente (el resto del listener de voz sigue intacto).
    """
    try:
        import websocket  # websocket-client
    except ImportError:
        log("  [proactivo] falta 'websocket-client' (pip install websocket-client); "
            "sin canal proactivo.")
        return

    while True:
        try:
            ws = websocket.create_connection(WS_URL, timeout=10)
        except Exception:
            # Backend todavía abajo: reintentar sin spamear el log.
            time.sleep(5)
            continue

        log("  [proactivo] conectado al canal del backend.")
        # recv() bloqueante con timeout largo: el silencio NO es una caída. El
        # timeout=10 de create_connection era el bug — mataba la conexión idle
        # cada vez que pasaban >10s sin mensaje, reconectando en loop (churn) y
        # abriendo ventanas de ~5s donde un aviso se perdía.
        ws.settimeout(PROACTIVE_RECV_TIMEOUT)
        try:
            while True:
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    # Silencio prolongado: keepalive activo en vez de reconectar.
                    # Si el ping falla, el socket murió de verdad → reconnect.
                    try:
                        ws.send("ping")
                        continue
                    except Exception:
                        break
                if not raw:
                    break
                try:
                    data = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if data.get("type") == "proactive":
                    _handle_proactive(data, voice)
        except Exception:
            pass  # caída real del socket → reconectar
        finally:
            try:
                ws.close()
            except Exception:
                pass
        time.sleep(2)  # respiro breve antes de reconectar tras una caída real


# Flag: saludo completo solo en la primera wake word. Las siguientes
# solo dicen "sir?" — el usuario no quiere que lo salude de nuevo cada vez.
_greeted_once = False


def main():
    global _greeted_once
    import pyaudio
    from vosk import Model, KaldiRecognizer, SetLogLevel

    SetLogLevel(-1)  # silenciar logs internos de Vosk

    log("=" * 50)
    log("FRIDAY WAKE - iniciando (offline)")

    if not os.path.exists(PIPER_MODEL):
        log(f"ERROR: no encuentro la voz: {PIPER_MODEL}")
        return
    if not os.path.isdir(VOSK_MODEL):
        log(f"ERROR: no encuentro el modelo Vosk: {VOSK_MODEL}")
        return

    model = Model(VOSK_MODEL)
    rec = KaldiRecognizer(model, 16000, GRAMMAR)

    # ── Piper persistente: cargar la voz UNA sola vez (115 MB) ──────────
    # Piper queda como red de seguridad si Pocket TTS no carga.
    log("Cargando voz Piper (Ryan)...")
    voice = PiperVoice.load(PIPER_MODEL)
    log("Voz Piper cargada.")

    # ── Pocket TTS: voz Jarvis clonada (local, CPU). Pre-carga para que el
    #    primer saludo ya salga en Jarvis, sin demora en el primer "FRIDAY".
    log("Cargando Pocket TTS (voz Jarvis)...")
    _load_pocket()

    # ── faster-whisper: STT del habla libre (mejor con acento). Pre-carga
    #    para que el primer turno no pague los ~16s de carga del modelo.
    log("Cargando faster-whisper (reconocimiento)...")
    _load_whisper()

    # ── Canal proactivo: thread que escucha al backend y avisa (voz + toast).
    #    Daemon: no impide que el proceso cierre. Reconecta solo si el backend
    #    todavía no está arriba.
    threading.Thread(
        target=proactive_listener, args=(voice,), daemon=True, name="friday-proactive",
    ).start()
    log("Canal proactivo activo (escuchando avisos del backend).")

    p = pyaudio.PyAudio()
    try:
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                        input=True, frames_per_buffer=8000)
    except Exception as e:
        log(f"ERROR de micrófono: {e}")
        return
    stream.start_stream()
    log(f"Escuchando wake word: '{TRIGGER}'... (Ctrl+C para salir)")

    try:
        while True:
            data = stream.read(4000, exception_on_overflow=False)
            if not rec.AcceptWaveform(data):
                continue
            text = json.loads(rec.Result()).get("text", "").lower()
            if not text:
                continue
            log(f"  → {text}")
            if TRIGGER in text:
                log("🎤 WAKE WORD detectada!")
                # Pausar la escucha para no captar el propio saludo (eco).
                stream.stop_stream()
                # Saludo completo solo la primera vez; después, "sir?".
                # El usuario no quiere que lo salude de nuevo cada vez que
                # dice "friday" después del arranque inicial.
                if not _greeted_once:
                    greeting = get_greeting()
                    _greeted_once = True
                else:
                    greeting = random.choice(ACK_GREETINGS)
                log(f"  FRIDAY: {greeting}")
                speak(greeting, voice)

                # Asegurar que el backend (API) esté corriendo para conversar.
                if not is_running(API_PORT):
                    log("  Lanzando FRIDAY en WSL...")
                    launch_friday()
                    open_dashboard()  # abre la pestaña solo en el primer arranque

                if api_ready():
                    result = conversation_loop(stream, model, voice)
                    if result == "shutdown":
                        # Apagar todo y salir del script completamente.
                        speak("Shutting down all systems. Goodbye, sir.", voice)
                        shutdown_systems()
                        log("FRIDAY completamente apagado. Chau!")
                        return  # sale de main() → fin del script
                else:
                    log("  La API no respondió a tiempo.")
                    speak("My systems are still starting, sir. Give me a moment.", voice)

                # Volver a esperar la wake word.
                rec = KaldiRecognizer(model, 16000, GRAMMAR)
                if stream.is_stopped():
                    stream.start_stream()
                log(f"Escuchando wake word: '{TRIGGER}'...")
    except KeyboardInterrupt:
        log("Saliendo.")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


if __name__ == "__main__":
    main()
