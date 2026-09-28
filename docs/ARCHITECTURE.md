# FRIDAY — Arquitectura (estado actual)

> QUÉ es y POR QUÉ está hecho así. Dónde está cada cosa: [CODEMAP.md](CODEMAP.md) ·
> tools: [TOOLS.md](TOOLS.md) · modelos: [MODELS.md](MODELS.md) · a dónde va: [ROADMAP.md](ROADMAP.md).

FRIDAY es un asistente personal por voz, **local-first**, que corre **entero en una Mac Apple Silicon**:
un proceso *listener* (micrófono, wake word, STT, TTS) y un proceso *backend* (API, cerebro, tools,
scheduler, datos), hablando por HTTP y WebSocket en `127.0.0.1`.

> Historia: hasta 2026-09 corría repartido entre Windows (voz) y WSL/Ubuntu (backend), porque el
> micrófono vivía en Windows. En la Mac todo está en el mismo host y ese puente (interop `cmd.exe`,
> PowerShell, `wsl --shutdown`) se retiró. Ver el historial de git si hiciera falta.

## Los dos procesos

| | Listener (`friday/voice/wake.py`) | Backend (`friday.app`) |
|---|---|---|
| Arranca | LaunchAgent `com.friday.wake` al login | lo lanza el listener (`start.sh`) al oír "FRIDAY", o a mano |
| Hace | wake word, VAD, STT, TTS, barge-in, mute, avisos proactivos | API + HUD `:8000`, cerebro, tools, collectors, scheduler, SQLite |
| Por qué separado | la voz tiene que estar siempre escuchando con poca RAM; el backend solo cuando se usa | se reinicia/actualiza sin cortar la escucha |

Ollama corre como servicio de `brew services` al login (idle ≈ sin RAM; el modelo se carga al primer
uso y `keep_alive=30m`). "shutdown" por voz descarga el modelo, no mata el servicio.

## Pipeline de voz (un turno)

1. **Wake word** — Vosk con *grammar* restringida (`["friday","hey","wake up"]`): vocabulario chico =
   detección casi instantánea y CPU mínima.
2. **Arranque** — si `:8000` no responde, `launch_friday()` corre `start.sh` (pidfile, asegura Ollama) y
   abre el HUD.
3. **Escucha** — endpointing por **energía (RMS)** leyendo el mic cada 100 ms: cierra el turno tras
   0.8 s de silencio sostenido (`FRIDAY_END_SILENCE`), así una pausa corta no te corta.
4. **STT** — **Parakeet `tdt-0.6b-v3` en la GPU** (0.14 s por frase); fallback whisper-turbo (MLX),
   faster-whisper (CPU) y el texto de Vosk. **Especulativo**: arranca a los 0.3 s de silencio, dentro de
   la espera del cierre → casi siempre ya está listo. Todo el STT corre en UN thread (`_STT_POOL`):
   MLX ata sus streams al thread que los creó.
5. **Cerebro** — `POST /api/chat` → `brain.chat()` con function calling (ver abajo).
6. **TTS** — Pocket TTS **en streaming** (`_StreamPlayer`: chunks directo a PyAudio, 1er audio ~0.09 s)
   con voz de catálogo (`TTS_VOICE`, default `michael`) o clonada si hay `voices/jarvis.wav`; fallback
   Piper/Ryan + `afplay`. El texto se parte en bloques <35 tokens (Pocket saltea palabras si se pasa).
7. **Interrupción** — mientras habla, el mic sigue: si decís algo con sustancia (≥5 chars, tras 0.8 s de
   gracia) que **no** sea eco de lo que FRIDAY está diciendo (`_is_echo`, ≥50% de palabras en común),
   corta en ≤0.1 s y te atiende.
8. **Mute** — "mute" silencia; queda escuchando solo "resume" (grammar Vosk, sin Whisper ni LLM).

## El cerebro

- **Factory** (`core/brain_factory.py`) según `LLM_PROVIDER`: `gemini` (`FridayBrain`) u `ollama`
  (`OllamaBrain`). Misma interfaz (`core/llm_base.py:Brain`), mismo system prompt.
- **Routing** (`FridayBrain._classify`): mensajes cortos/métricas y el default → `fast`
  (3.5-flash-lite); >200 chars → `balanced` (3.8-flash); `pro` **solo explícito** (preview, sin free
  tier). Detalle y costos en [MODELS.md](MODELS.md).
- **Thinking** — la familia 3.x siempre piensa y el thinking consume `max_output_tokens`: techo 1024 y
  `thinking_level` por modelo. La brevedad para voz ("two sentences") la impone el prompt.
- **Fallback** — un 429 de Gemini degrada esa respuesta a Ollama con el **mismo** `chat_repo` + sesión:
  Ollama carga la conversación desde SQLite (fuente de verdad neutral) y la continúa.
- **Contexto acotado** — ventana de 12 turnos cortando en bordes de turno (nunca un
  `function_response` huérfano), memorias (≤30) en el system prompt, **prefijo estable** (fecha, no
  hora) para cache implícito/KV-cache, y resultados de tools de turnos previos recortados a 600 chars
  (`core/context_window.py`).
- **Coerción de args** (`tools_registry._coerce_args`) — los LLM mandan `"24"` por `24` o dicts por
  strings; se corrige según los type hints, el único punto por el que pasan todas las calls.

### Dos capas de tools

1. **`ToolsRegistry`** (`core/tools_registry.py`) — lo que ve el LLM. Schemas generados de firma +
   docstring (`core/tool_schema.py`): **la 1ra línea del docstring es la descripción**.
2. **Agente con permisos** (`friday/agent/`) — cada *acción* se registra con un `RiskLevel` y se expone
   como tool de **primera clase** con su firma real (`agent/setup.py:_make_gated_tool`). Antes todo
   iba detrás de `ejecutar_accion_pc(accion, argumentos=JSON-string)` y un 7B no armaba el JSON
   anidado: narraba el éxito sin llamar la tool. El `PermissionGate` ejecuta LOW y deja MEDIUM/HIGH
   pendientes de `confirm()` (hoy solo desde el HUD/API; por voz es el gap #1 del roadmap).

Catálogo completo con riesgo y fuente: [TOOLS.md](TOOLS.md) (generado; un test exige que esté al día).

## HUD en vivo (eventos por /ws/live)

| Evento | Lo emite | Para qué |
|---|---|---|
| `voice` (`stage`: wake/listening/hearing/stt/thinking/speaking/muted/idle, `text`, `timings`) | listener → `POST /api/voice/event` | orbe, etapas, transcript, cascada de latencia |
| `tool` (`running`/`ok`/`error`) | `activity_log.subscribe` en `app.py` | event stream, etapa TOOLS |
| `hud` (`mode`: card/stage/view, `panel`, `data`, `reason`) | `core/hud.py` (auto por `TOOL_PANELS` o `mostrar_en_hud`) | **tarjeta de foco** / **ventana grande** (video, INTEL) |
| `voice_control` | `POST /api/voice/control` (CONTROL) | el listener aplica mute / voz / cierre de turno en caliente |
| `metric`, `proactive` | collectors / notifier | vitals, alertas |

Emisión desde threads: `WebSocketBroadcast.emit()` agenda en el loop de uvicorn
(`run_coroutine_threadsafe`). El HUD se identifica mandando `"hud"` al conectar
(`mostrar_en_hud` sabe si hay pantalla mirando).

## Proactividad (el backend habla primero)

`notifier` (umbrales, cada 60 s) y `analyst` (tendencias estadísticas, cada 30 min; el LLM no decide
anomalías) → `ProactiveDispatcher` aplica la política de severidad ("derecho a callarse": `critical`
habla, `warning` solo notificación) → WS `/ws/live` → el listener muestra una notificación de macOS y,
si corresponde y no estás conversando, lo dice. Briefings 08:30/22:00 (`compose()` con el modelo lite)
y research diario 08:00 (digest markdown determinista, sin LLM en el camino crítico).

## Datos

- **SQLite** `friday.db` (WAL, un `RLock` compartido por todos los repos porque APScheduler escribe
  desde varios threads): métricas (purga >30 días), chat, notificaciones, memorias.
- **Conocimiento** en markdown: `knowledge/<categoría>/<fecha>.md` — curable a mano, portable (Obsidian).
- **Telemetría** a SQLite, **documentos** a markdown: regla de la casa.

## Stack y por qué

| Pieza | Tecnología | Por qué |
|---|---|---|
| Wake word | Vosk small + grammar | Offline, instantáneo, ~50 MB |
| STT | mlx-whisper large-v3-turbo (Metal) | Mucho mejor con acento; ~1 s en GPU |
| Cerebro | Gemini 3.x + Gemma 4 (Ollama) | Nube barata con buen tool calling; local gratis/offline |
| TTS | Pocket TTS (Kyutai) → Piper | Clona la voz de Jarvis en CPU; Piper como red |
| API/Sched | FastAPI + APScheduler | Estándar, liviano |
| UI | HUD HTML puro servido por la API | Sin build; Streamlit queda legacy (`--streamlit`) |
| Datos | SQLite + markdown | Cero infra |

## Gotchas conocidos

- **`127.0.0.1`, nunca `localhost`** en clientes HTTP: evita el intento IPv6 (`::1`) primero (+21 s de
  timeout con Ollama).
- **La API no tiene auth** → bind en `127.0.0.1` (`API_HOST`). El agente lee archivos sin confirmación.
- **`.env` pisa los defaults**: una línea `GEMINI_MODEL_*=gemini-2.5-…` vieja rompe el cerebro.
- **Ollama sin `num_ctx`** recorta el principio del prompt (el system prompt). Se fija en 8192.
- **Gemma 4 piensa por defecto** → sin `think:false` gasta `num_predict` razonando y responde vacío
  (`ollama_think`). Mismo patrón que Gemini 3.x con `max_output_tokens`.
- **`ollama pull` puede salir con código 0 tras un timeout de red**: verificar con `ollama list`.
- **Pocket TTS con clonado es gated** en HuggingFace: aceptar términos + `hf auth login`.
- **"unmute" no está en el vocabulario de Vosk** → la palabra de reactivación es "resume".
- **macOS `/` es el volumen sellado**: el disco se mide en `/System/Volumes/Data` (`platform_info.disk_path`).
- **HUD**: `render()` corre en cada `setState` (el reloj, cada 1 s). Toda escritura al DOM va por
  `el.__setHTML` / `el.__setText` (solo escriben si cambió) — si no, parpadea todo. Polling pausado con la
  pestaña oculta; alertas proactivas por WebSocket (historial una vez por conexión).
- **RAM en macOS**: `psutil` cuenta caché/comprimida como usada (~80% en reposo). Se usa
  `kern.memorystatus_level` (`platform_info.mac_memory_used_pct`). El notifier tiene histéresis
  (5 pts) y enfriamiento (30 min) para warnings: sin eso las alertas de RAM flapeaban en loop.
- **MLX + threads**: "There is no Stream(cpu, 1) in current thread" = se usó un modelo MLX desde otro
  thread. Todo el STT va por `_STT_POOL`.
- **`pkill -f 'venv/bin/friday'` matchearía `friday-wake`**: el patrón está anclado en `shutdown_friday.sh`.
