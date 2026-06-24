# FRIDAY — Arquitectura (estado actual)

> QUÉ es y CÓMO funciona hoy. Para la visión y lo que falta, ver [ROADMAP.md](ROADMAP.md).

FRIDAY es un asistente personal por voz, **100% local y gratis**. Corre repartido entre
**Windows** (captura de micrófono y reproducción de audio) y **WSL/Ubuntu** (cerebro,
API, dashboard, datos). Esa división existe porque el micrófono y el audio viven en
Windows, y el resto del stack (Python, Ollama, etc.) vive cómodo en WSL.

```
┌─────────────────── Windows ───────────────────┐      ┌──────────────── WSL (Ubuntu) ────────────────┐
│  windows_wake.py (listener, py 3.12)           │      │  friday.app  (FastAPI + scheduler)            │
│   • Wake word: Vosk (grammar restringida)      │      │   • API REST  :8000                           │
│   • STT: faster-whisper (small.en, CPU)        │ HTTP │   • Dashboard Streamlit :8510                 │
│   • TTS: Pocket TTS (voz Jarvis clonada)       │─────▶│   • Brain: Ollama qwen2.5:7b (function calling)│
│     fallback → Piper/Ryan                      │ /api │   • Tools + Agent/PermissionGate              │
│   • Reproduce audio (PowerShell SoundPlayer)   │/chat │   • Collectors (system, nexcourt, gemini)     │
└────────────────────────────────────────────────┘      │   • SQLite (métricas, chat, notificaciones)   │
                                                         │   • Ollama server :11434                      │
                                                         └───────────────────────────────────────────────┘
```

## El pipeline de voz (turno completo)

1. **Wake word** — `friday/voice/windows_wake.py` escucha con **Vosk** y una *grammar*
   restringida (`["friday","hey","wake up"]`). Vocabulario chico = detección casi instantánea.
2. **Arranque** — al detectar "FRIDAY", el listener saluda y, si el backend no está vivo,
   lanza en WSL: `ollama serve` (si hace falta) + `./venv/bin/friday` (`launch_friday()`).
3. **Escucha (STT)** — el endpointing es por **energía del mic (RMS)**: bufferea mientras hay voz
   y cierra el turno recién tras ~1.3s de silencio sostenido (`_listen_turn`), así una pausa para
   pensar NO te corta a mitad de frase. El audio crudo lo transcribe **faster-whisper** (`small.en`,
   CPU int8) — muy superior con acento; Vosk queda como fallback si Whisper no devuelve nada.
4. **Cerebro** — el texto va por HTTP a `POST /api/chat` → `OllamaBrain.chat()`
   (`friday/core/ollama_brain.py`). Usa **qwen2.5:7b** vía Ollama con *function calling*.
5. **Voz (TTS)** — la respuesta se sintetiza con **Pocket TTS** (Kyutai), voz **clonada de
   Jarvis** desde `voices/jarvis.wav`, local en CPU (~1.4s). Si Pocket TTS no cargó, cae a
   **Piper/Ryan**. Se reproduce con `Media.SoundPlayer.PlaySync()` (solo PCM int16).
6. **Interrupción** — mientras FRIDAY habla, el mic sigue escuchando; si hablás, corta y atiende.
7. **Mute** — si decís *"mute"*, FRIDAY se silencia y deja de procesarte; queda escuchando
   SOLO *"unmute"* con una grammar Vosk restringida (sin Whisper ni cerebro, sin timeout)
   hasta que lo reactivás. Vive en `conversation_loop` (`_muted_wait`).

> Tiempos típicos por turno: STT ~1s · LLM ~1-2s · TTS ~1.4s.

## El cerebro y las tools

- **Factory** — `friday/core/brain_factory.py` elige el cerebro según `settings.llm_provider`:
  - `gemini` (**default**): `FridayBrain` (`core/brain.py`), nube, requiere `GEMINI_API_KEY`.
    Modelo `gemini-2.0-flash` (barato, mejor en function-calling que qwen). El routing `auto`
    sube a `2.5-flash` solo en consultas complejas; **nunca** a `pro`. Tope de gasto en la API key.
  - `ollama`: `OllamaBrain`, local, sin costo, offline. Modelo `qwen2.5:7b`. Flip de `llm_provider`.
- **Contrato común** — `core/llm_base.py` (`Brain` Protocol, `ChatResult`). Intercambiables.
- **Function calling** — el brain expone *tools* y ejecuta las que el modelo pide, en loop
  (`MAX_TOOL_ROUNDS`). Schemas generados desde type hints + docstrings (`core/tool_schema.py`).

### Dos capas de tools (importante)

1. **`ToolsRegistry`** (`core/tools_registry.py`) — las funciones que ve el LLM (todas de lectura):
   `consultar_metricas`, `resumen_costos`, `obtener_fecha_hora`, y la observabilidad:
   `estado_sistemas` (cubre NEXCOURT **y** AXIS, filtrable por `sistema`) y `metricas_servicio`.
   En modo `cloudwatch` se suman `alarmas_activas` y `errores_recientes` (AWS en vivo); con
   `axis_enabled` se suma `errores_axis` (logs del container vía SSH).
2. **Agente con permisos** (`friday/agent/`) — la capa para **acciones con riesgo**:
   - `registry.py`: `ActionRegistry` (allowlist) + `ActionSpec(name, description, risk, fn)` + `RiskLevel{LOW,MEDIUM,HIGH}`.
   - `permissions.py`: `PermissionGate`. `LOW` ejecuta solo; `MEDIUM/HIGH` quedan **pendientes**
     y devuelven un `action_id` hasta que el humano confirme (`confirm(action_id, approved)`).
   - `setup.py`: expone **cada acción como una tool de primera clase** con su firma real
     (`abrir_app(nombre)`, `cargar_gasto(monto, …)`), vía `_make_gated_tool` (functools.wraps +
     PermissionGate). Antes todo iba detrás de una sola `ejecutar_accion_pc(accion, argumentos=JSON-string)`,
     pero qwen2.5:7b no podía armar el JSON anidado y **narraba** el éxito sin llamar la tool.
   - API: `routes_agent.py` → `GET /api/agent/tools`, `POST /api/agent/run`, `POST /api/agent/confirm`.

> Este *gate* es la columna vertebral de "FRIDAY controla todo **con mi autorización**".
> Todas las integraciones futuras se cuelgan de acá. Ver [ROADMAP.md](ROADMAP.md).

## Observabilidad (collectors)

`friday/collectors/` con patrón común (`base.Collector`): un scheduler los pollea y guarda
`MetricPoint`s en SQLite.

- `system.py` — CPU/RAM/disco de la máquina local.
- `nexcourt.py` — pollea `/actuator/health` y `/actuator/prometheus` de cada microservicio
  NEXCOURT **en hosts locales** (puertos de gestión **9081-9087** en modo `direct`, o vía
  **Kong** en modo `kong`). Para docker-compose local.
- `cloudwatch.py` — NEXCOURT **en producción (AWS ECS)**, 100% read-only. Estado y conteo de
  tareas vía ECS API (`describe_services`), CPU/memoria vía CloudWatch (`get_metric_data`).
  Emite con `source="nexcourt"` para reusar el wiring del dashboard/WebSocket. Se activa con
  `nexcourt_mode="cloudwatch"`. ⚠️ Credenciales: IAM read-only dedicado, **nunca root**.
- `axis.py` — AXIS **en el droplet DigitalOcean**, vía SSH (alias `axis`), read-only. Un solo
  round-trip ejecuta `docker ps` + `docker stats`; emite `source="axis"` con status/cpu/mem por
  container. Se activa con `axis_enabled=true`. Monitorea una lista explícita de containers.
- `gemini_usage.py` — tracking de costo/tokens de Gemini (relevante solo si se usa Gemini).

## Almacenamiento, API y dashboard

- **SQLite** (`friday/storage/`) — `metrics_repo`, `chat_repo` (historial de conversaciones),
  `notification_repo`, `memory_repo`. DB en `friday.db`.
- **Conocimiento** (`friday/storage/knowledge_store.py`) — capa de DOCUMENTOS (no métricas):
  archivos `.md` en `knowledge/<categoria>/<fecha>.md`. Hoy la usa `ResearchService`
  (`core/research.py`): un job diario que junta novedades de IA/tech + backend y arma un
  digest markdown determinista (links reales, sin LLM en el camino crítico). El cerebro lo
  lee on-demand con `consultar_research`; el HUD lo muestra en el tab RESEARCH. Es la capa
  de "inteligencia/second brain": telemetría va a SQLite, conocimiento va a markdown.
- **API** (`friday/api/`) — FastAPI: `routes_chat`, `routes_agent`, `routes_status`,
  `routes_notifications`, `routes_voice` (expone el log del listener), `ws` (websocket "thinking").
- **Dashboard** (`friday/dashboard/`) — Streamlit en `:8510` (métricas, chat, estado de voz).

## Stack y por qué (todo gratis/local)

| Pieza | Tecnología | Por qué |
|-------|-----------|---------|
| Wake word | Vosk (small, grammar) | Offline, instantáneo, CPU mínima |
| STT | faster-whisper `small.en` (CPU int8) | Mucho mejor con acento; gratis/local. GPU descartada (DLLs CUDA en Windows). |
| Cerebro | Ollama `qwen2.5:7b` | Local, sin costo, soporta tools. Buena conversación. |
| TTS | Pocket TTS (Kyutai, MIT) | Clona la voz de Jarvis, CPU ~1.4s, sin GPU. Fallback Piper. |
| API/Sched | FastAPI + APScheduler | Estándar, liviano |
| UI | Streamlit | Rápido de iterar |
| Datos | SQLite | Cero infra |

## Cómo corre todo

- **Windows** lanza `windows_wake.py` (autostart oculto `friday-wake.vbs`, o `friday-wake.bat` visible para debug).
  Pre-carga Pocket TTS y faster-whisper al arrancar (una vez).
- **WSL** corre `friday.app` (API `:8000` + dashboard `:8510`) y `ollama serve` (`:11434`).
  El listener lo levanta solo al decir "FRIDAY"; o manual con `start.sh` / `stop.sh`.
- **Apagado**: decir "shutdown" (o `stop.sh`) → mata FRIDAY + Ollama y libera la RAM de WSL2.

## Gotchas conocidos

- **`127.0.0.1`, nunca `localhost`** para HTTP WSL↔Windows (si no, +21s por timeout IPv6).
- **Pocket TTS clonado es gated** en HuggingFace: hay que aceptar términos + login local una vez.
- **Media.SoundPlayer solo reproduce WAV PCM int16** (un WAV float sale mudo).
- **`.bat` en ASCII puro**: nada de `chcp 65001` ni acentos/recuadros Unicode (rompe el parseo de CMD).
- **No correr el `.bat` desde `\\wsl.localhost\...`** si te molesta el warning de UNC (es inofensivo).
