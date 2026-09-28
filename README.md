# FRIDAY — Asistente personal por voz

> Asistente estilo Jarvis: lo activás diciendo **"FRIDAY"**, te responde hablando, controla tu Mac
> y tus apps **con tu autorización**, observa tus sistemas (NEXCOURT, AXIS) y te junta
> inteligencia diaria en un **Command Center** propio.

Corre **nativo en macOS (Apple Silicon)**: listener de voz, cerebro, API, HUD y datos en la misma
máquina. Cerebro en la nube con **Gemini 3.x** (`gemini-3.5-flash-lite` por defecto) y cerebro local
con **Gemma 4** vía Ollama (offline, o fallback automático si Gemini se queda sin cuota).

```
┌──────────────────────────────── Mac (M4) ─────────────────────────────────┐
│  friday/voice/wake.py  (LaunchAgent al login)                              │
│    Vosk (wake word) → Parakeet (STT, GPU) → Pocket TTS en streaming         │
│        │ HTTP 127.0.0.1:8000/api/chat          ▲ WS /ws/live (avisos)      │
│        ▼                                        │                          │
│  friday.app  (FastAPI + APScheduler)  ── HUD http://127.0.0.1:8000/        │
│    Cerebro Gemini 3.x ⇄ fallback Ollama (Gemma 4)                          │
│    Tools + PermissionGate · Collectors · SQLite · Research diario          │
└────────────────────────────────────────────────────────────────────────────┘
```

Documentación: [docs/](docs/README.md) · mapa del código [CODEMAP](docs/CODEMAP.md) ·
tools [TOOLS](docs/TOOLS.md) · modelos [MODELS](docs/MODELS.md) · migración desde Windows [MIGRATION](docs/MIGRATION.md).

---

## Instalación (macOS, Apple Silicon)

Requisitos: macOS + [Homebrew](https://brew.sh), ~10 GB libres, micrófono. Opcional: `GEMINI_API_KEY`
de Google AI Studio (sin key corre 100% local). Con billing habilitado, poné un **tope mensual** en la key.

```bash
gh repo clone GonzaloBisio/friday ~/friday && cd ~/friday
bash scripts/macos/setup.sh
```

`setup.sh` es idempotente y hace todo: `brew install python@3.12 portaudio ollama ffmpeg`, venv con
Python 3.12 (`pip install -e ".[ir,voice,dev]"`), modelos de voz en `voices/`, Ollama como servicio al
login + `gemma4:e4b-it-qat`, un `.env` inicial (`LLM_PROVIDER=ollama`) y el **autostart del listener**.
La primera vez macOS pide permiso de **Micrófono**, y el listener baja `whisper-large-v3-turbo` (~1.6 GB).

> ¿Por qué Python 3.12? `vosk`, `pyaudio` y `ctranslate2` no siempre tienen wheels para 3.13+.

### Voz

FRIDAY habla con **Pocket TTS** usando una voz del catálogo (`TTS_VOICE` en `.env`, default `michael`;
escuchá las opciones con `afplay voices/samples/<voz>.wav`). No requiere login.

Opcional, clonar una voz: dejá un clip limpio de ~9 s en `voices/jarvis.wav` (se versiona en git),
aceptá los términos en https://huggingface.co/kyutai/pocket-tts y corré `./venv/bin/hf auth login`.
Usá una voz propia o de alguien que lo haya autorizado. Si Pocket TTS falla, cae a Piper/Ryan.

## Configuración (`.env`)

Los defaults viven en `friday/config.py`; en `.env` va solo lo que cambies (plantilla: `.env.example`).

```ini
LLM_PROVIDER=gemini        # "ollama" = 100% local/offline
GEMINI_API_KEY=tu-api-key
```

| Integración | Variables | Notas |
|---|---|---|
| Spotify | `SPOTIFY_CLIENT_ID/SECRET` | Requiere Premium. Auth one-time: `friday-spotify-auth` |
| Gastos (Sheets) | `GOOGLE_SHEETS_CREDENTIALS`, `GASTOS_SPREADSHEET_ID` | Service account (JSON gitignored) |
| NEXCOURT | `NEXCOURT_MODE=cloudwatch` (AWS) · `direct`/`kong` (local) | Default `off`. En AWS: IAM **read-only** dedicado, nunca root |
| AXIS (SSH) | `AXIS_ENABLED=true` | Alias `axis` en `~/.ssh/config` |

> **Secretos**: nunca van al repo (`.env`, tokens y JSON de service account están en `.gitignore`).
> La API escucha solo en `127.0.0.1` (no tiene auth y el agente lee archivos): no la abras a la red.

## Uso

Normalmente **no arrancás nada a mano**: el listener corre desde el login; decís "FRIDAY", levanta el
backend y abre el HUD.

```bash
bash start.sh / bash stop.sh                    # backend a mano (log en friday.log)
./venv/bin/friday --cli                         # chat por terminal
launchctl kickstart -k gui/$(id -u)/com.friday.wake   # reiniciar el listener
bash scripts/macos/uninstall_autostart.sh       # sacar el listener del login
tail -f voices/friday-wake.log                  # log del listener
```

- **HUD**: http://127.0.0.1:8000/ · **API/Docs**: http://127.0.0.1:8000/docs

| Decí… | Hace |
|---|---|
| **"FRIDAY"** | Activa (saluda + levanta el backend y abre el HUD la primera vez) |
| *(pedile cosas)* | "what time is it", "open Spotify", "qué hay nuevo de IA"… |
| **"mute"** / **"resume"** | Silenciar / reactivar |
| **"stop" / "bye"** | Termina la conversación (sigue escuchando "FRIDAY") |
| **"shutdown"** | Apaga el backend, descarga Gemma de la RAM y cierra el listener (vuelve al próximo login o con `launchctl kickstart`) |

## Tests

```bash
./venv/bin/python -m pytest -q          # incluye chequeo de que docs/TOOLS.md y CODEMAP.md están al día
bash tests/voice/test_shutdown.sh       # integración: arranca y apaga el backend real
```

---

*Proyecto personal. Local-first, gratis donde se puede, con el humano siempre al mando.*
