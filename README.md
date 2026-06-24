# FRIDAY — Asistente personal por voz

> Asistente personal estilo Jarvis: lo activás por voz diciendo **"FRIDAY"**, te
> responde hablando, controla tu PC y tus apps **con tu autorización**, observa tus
> sistemas y te junta inteligencia (research diario) en un **Command Center** propio.

Corre repartido entre **Windows** (micrófono, wake word, voz) y **WSL/Ubuntu**
(cerebro, API, dashboard, datos). El cerebro usa **Gemini** (`gemini-2.5-flash`) con
fallback local a **Ollama** (`qwen2.5:7b`) si Gemini se queda sin cuota o estás offline.

```
┌──────────────── Windows ────────────────┐      ┌──────────────── WSL (Ubuntu) ───────────────┐
│  windows_wake.py (listener, py 3.12)     │      │  friday.app  (FastAPI + scheduler)           │
│   • Wake word: Vosk   • STT: Whisper     │ HTTP │   • API REST + Command Center  :8000          │
│   • TTS: Pocket TTS (voz Jarvis clonada) │─────▶│   • Cerebro: Gemini (fallback Ollama)        │
│   • Reproduce audio (PowerShell)         │ /api │   • Tools + Agent/PermissionGate             │
│   • Autostart oculto: friday-wake.vbs    │      │   • Collectors + SQLite + Research diario     │
└──────────────────────────────────────────┘      └───────────────────────────────────────────────┘
```

Detalle profundo en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · visión y roadmap en
[`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## Requisitos

- **Windows 10/11** con **WSL2 + Ubuntu**.
- **Python 3.12** en *ambos* lados (en Windows: pyaudio no tiene wheels para 3.13/3.14).
- Un **micrófono**.
- **GEMINI_API_KEY** (Google AI Studio). Con billing habilitado conviene poner un
  **tope mensual** en la API key (p. ej. $4) — FRIDAY no lo controla, lo hace Google.
- *(Opcional)* cuentas/credenciales de las integraciones que quieras usar (Spotify,
  Google Sheets, AWS).

---

## Instalación

### Parte A — Backend (WSL/Ubuntu)

```bash
# 1. Clonar
git clone <tu-repo-privado> friday && cd friday

# 2. Entorno e instalación (instala TODO el backend de una)
python3.12 -m venv venv
source venv/bin/activate
pip install -e .            # o  pip install -e ".[ir]"  para el emisor IR (luces)

# 3. Ollama (cerebro local de fallback)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b

# 4. Configurar secretos (ver sección Configuración)
cp .env.example .env && nano .env
```

### Parte B — Listener de voz (Windows)

El listener corre en **Windows** (donde está el mic). Vive en una copia local que el
autostart sincroniza desde WSL.

```powershell
# 1. Carpeta y dependencias (en PowerShell, con Python 3.12)
mkdir C:\Users\<vos>\friday\voices
py -3.12 -m pip install vosk pyaudio piper-tts faster-whisper pocket-tts websocket-client numpy

# 2. Modelos → dejarlos en C:\Users\<vos>\friday\voices\
#    - vosk-model-small-en-us-0.15      (wake word)    → alphacephei.com/vosk/models
#    - en_US-ryan-high.onnx (+ .json)   (TTS fallback) → github.com/rhasspy/piper voices
#    - jarvis.wav                       (clip ~9s para clonar la voz con Pocket TTS)
```

> Las rutas en `windows_wake.py` y los `.vbs/.bat` asumen el usuario `gonza`. Si el tuyo
> es otro, ajustá `C:\Users\gonza\...` en `friday-wake.vbs`, `friday-wake.bat` y
> `windows_wake.py` (constante `VOICES_DIR`).

#### Autostart al iniciar sesión (recomendado)

1. `Win + R` → escribí `shell:startup` → Enter.
2. Copiá `friday-wake.vbs` a esa carpeta.
3. Listo: en cada login arranca **oculto**, sincroniza el listener desde WSL y queda
   escuchando "FRIDAY". (Para debug con logs: doble-click en `friday-wake.bat`.)

---

## Configuración (`.env`)

Copiá `.env.example` → `.env` y completá. Lo mínimo para que hable:

```ini
GEMINI_API_KEY=tu-api-key        # requerido (provider por defecto: gemini)
LLM_PROVIDER=gemini              # "ollama" para 100% local/offline
```

Integraciones opcionales (cada una se activa al poner sus credenciales):

| Integración | Variables | Notas |
|---|---|---|
| Spotify | `SPOTIFY_CLIENT_ID/SECRET` | Requiere Premium. Auth one-time: `friday-spotify-auth` |
| Gastos (Sheets) | `GOOGLE_SHEETS_CREDENTIALS`, `GASTOS_SPREADSHEET_ID` | Service account (JSON gitignored) |
| NEXCOURT (AWS) | cadena boto3 + `NEXCOURT_MODE=cloudwatch` | IAM **read-only** dedicado, nunca root |
| AXIS (SSH) | `AXIS_ENABLED=true` | Alias `axis` en `~/.ssh/config` |

> **Secretos**: nunca van al repo. `.env`, los tokens y los JSON de service account
> están en `.gitignore`. No commitees keys.

---

## Correr y verificar

```bash
# Backend (WSL) — manual
bash start.sh                       # API + dashboard en background (log en friday.log)
bash stop.sh                        # apaga todo (FRIDAY + Ollama)

# Verificar que el cerebro responde
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello","model":"auto"}'
```

- **Command Center (HUD)**: http://127.0.0.1:8000/
- **API / Docs**: http://127.0.0.1:8000/docs

En uso normal **no arrancás el backend a mano**: decís "FRIDAY" y el listener lo levanta
solo y te abre el HUD.

### Comandos de voz

| Decí… | Hace |
|---|---|
| **"FRIDAY"** | Activa (saluda + abre el HUD la primera vez) |
| *(pedile cosas)* | "what time is it", "open Spotify", "qué hay nuevo de IA"… |
| **"mute"** / **"resume"** | Silenciar / reactivar |
| **"stop" / "bye"** | Termina la conversación (sigue escuchando "FRIDAY") |
| **"shutdown"** | Apaga TODO (FRIDAY + Ollama + libera la RAM de WSL2) |

---

## Tests

```bash
./venv/bin/python -m pytest -q
```

## Estructura

```
friday/
  app.py            # bootstrap: API + scheduler + collectors + research
  core/             # cerebros (gemini/ollama), tools, proactividad, research, briefing
  agent/            # ActionRegistry + PermissionGate (acciones con riesgo)
  collectors/       # telemetría → SQLite (system, nexcourt, axis, gemini_usage)
  integrations/     # spotify, gastos, web_research, ir/lights
  api/              # rutas FastAPI + WebSocket
  storage/          # repos SQLite + KnowledgeStore (research en markdown)
  dashboard_web/    # Command Center (HUD, HTML puro)
  voice/            # windows_wake.py (listener) + shutdown
docs/               # ARCHITECTURE.md · ROADMAP.md · README.md
```

---

*Proyecto personal. Local-first, gratis donde se puede, con el humano siempre al mando.*
