# FRIDAY — Mapa del código (índice de navegación)

> Para ir **directo al archivo** sin buscar. Cada entrada: qué hace + dónde tocar.
> Catálogo de tools (auto-generado): [TOOLS.md](TOOLS.md) · Modelos: [MODELS.md](MODELS.md) ·
> Por qué está hecho así: [ARCHITECTURE.md](ARCHITECTURE.md).
> Líneas `archivo:N` verificadas al 2026-09-27; si una se corrió, buscá el símbolo.

## 1. Grafo de ejecución

### Turno de voz (camino caliente)

```
voices/  (Vosk, Piper, jarvis.wav)        LaunchAgent com.friday.wake (al login)
   │                                                │
   ▼                                                ▼
friday/voice/wake.py ── main():1162 ─ Vosk grammar ["friday",…] ─► "friday" detectada
   │  ├─ speak() saludo ─ _synthesize():467  _start_speech → _StreamPlayer (Pocket streaming → PyAudio) │ Piper+afplay
   │  ├─ launch_friday() → start.sh (si :8000 no responde) → Ollama + friday.app
   │  └─ conversation_loop → _run_conversation():966
   │        ├─ _listen_turn():888   VAD RMS c/100ms, cierra a 0.8s; STT especulativo a 0.3s
   │        ├─ _transcribe()        Parakeet (GPU, _STT_POOL) │ whisper-turbo │ faster-whisper │ Vosk
   │        ├─ ask_friday() ── HTTP POST 127.0.0.1:8000/api/chat ──────────────┐
   │        └─ _play_with_interrupt()  barge-in con filtro de eco (_is_echo)      │
   ▼                                                                             ▼
friday/api/routes_chat.py:40 post_chat ─► brain.chat(msg, model="auto") (thread executor)
   │
   ▼
friday/core/brain.py  FridayBrain.chat():86           (Gemini; Ollama = ollama_brain.py)
   ├─ _select_model()/_classify()  fast │ balanced │ reasoning (solo "pro" explícito)
   ├─ _compact_old_tool_results()  recorta resultados de turnos previos (context_window.py)
   ├─ with_time_note(msg)          hora en el mensaje → prefijo estable → cache
   ├─ _run_tool_loop  ≤ MAX_TOOL_ROUNDS=10
   │     _call_gemini: system(_build_system_instruction) + tools(27-30) + history
   │     └─ function_call → _execute_tool → ToolsRegistry.execute (_coerce_args)
   │                         └─ tool gated → PermissionGate.request (agent/permissions.py)
   │                               LOW → ejecuta · MEDIUM/HIGH → pending_confirmation
   └─ 429 sin cuota → _fallback_to_ollama():184 (mismo chat_repo/session → continuidad)
```

### Bootstrap y fondo

```
friday.app:main():413 ─► FridaySystem():64
  ├─ SQLite (storage/db.py:get_connection) + RLock compartido por todos los repos
  ├─ tools: build_registry (lectura) + register_agent_tools (acciones gated)
  │         + memory/routine/health/research tools        → catálogo en docs/TOOLS.md
  ├─ brain = build_brain() (core/brain_factory.py:26) según LLM_PROVIDER
  ├─ APScheduler:
  │    collectors (system 10s · gemini_usage · nexcourt/cloudwatch · axis) → metrics_repo
  │    notifier 60s ─► ProactiveDispatcher ─► WS /ws/live ─► wake.proactive_listener
  │    analyst 30min (tendencias, estadístico) · briefings 08:30/22:00 (compose → lite)
  │    research 08:00 → knowledge/<cat>/<fecha>.md · purga métricas >30d (6h)
  └─ start_api():297 uvicorn en settings.api_host (127.0.0.1) : HUD "/" + /api/* + /docs
```

## 2. Archivos (qué es cada uno)

**Raíz**: `start.sh`/`stop.sh` (arranque/parada con pidfile; stop descarga modelos de
Ollama) · `pyproject.toml` (deps + extras `ir`,`voice`,`dev` + comandos `friday`,
`friday-wake`, `friday-spotify-auth`, `friday-ir-learn`) · `.env` (gitignored) ·
`FRIDAY_IMPLEMENTATION_PLAN.md` (plan histórico 2026-06, rutas Windows: **no** es el estado actual).

| Área | Archivo | Qué hace / cuándo tocarlo |
|---|---|---|
| **Config** | `friday/config.py` | `Settings` (pydantic). **Todo** knob vive acá; `.env` lo pisa. Modelos, umbrales, horarios, temas de research. |
| | `friday/platform_info.py` | `PLATFORM` (macos/linux) y `disk_path()`. Único lugar con diferencias de SO del backend. |
| | `friday/models.py` | `MetricPoint` (la unidad de telemetría). |
| **Arranque** | `friday/app.py` | `FridaySystem`: cablea todo (repos, tools, brain, scheduler, API). Agregar un job/servicio nuevo = acá. |
| **Cerebro** | `friday/core/llm_base.py` | `FRIDAY_SYSTEM_PROMPT` (persona + reglas) y `Brain` Protocol. Cambiar la personalidad = acá. |
| | `friday/core/brain.py` | Gemini: routing de modelo, thinking por familia (`_thinking_for`), tool loop, fallback 429. |
| | `friday/core/ollama_brain.py` | Ollama: misma interfaz; `num_ctx`, `keep_alive`, tool loop OpenAI-style. |
| | `friday/core/brain_factory.py` | Elige cerebro por `LLM_PROVIDER`. |
| | `friday/core/context_window.py` | Ahorro de tokens: `day_stamp`, `with_time_note`, `compact_tool_result`. |
| **Tools** | `friday/core/tools_registry.py` | `ToolsRegistry` + tools de lectura (métricas, costos, estado de sistemas) + `_coerce_args` (tipos flojos del LLM). |
| | `friday/core/tool_schema.py` | Firma + docstring → JSON schema (Ollama). **La 1ra línea del docstring es la descripción que ve el LLM.** |
| | `friday/core/memory_tools.py` | `recordar` / `olvidar` (memoria → SQLite → system prompt). |
| | `friday/core/routines.py` | Rutinas compuestas (`focus`, `winddown`, `pausa`) que reusan el gate. |
| | `friday/core/research.py` | Digest diario de novedades + tool `consultar_research`. |
| | `friday/core/health.py` | Autoobservabilidad (latencia, fallbacks, éxito de tools) + tool `estado_de_friday`. |
| **Agente** | `friday/agent/registry.py` | `ActionRegistry` (allowlist) + `RiskLevel`. |
| | `friday/agent/permissions.py` | `PermissionGate`: LOW ejecuta, MEDIUM/HIGH pendientes de `confirm()`. |
| | `friday/agent/setup.py` | `build_action_registry()`: **dónde se registra cada acción y su riesgo**. |
| | `friday/agent/actions/pc_actions.py` | Abrir/cerrar apps (`open -a` / AppleScript), URLs, procesos, archivos, info del sistema. Alias de apps: `_MAC_APP_TARGETS`. |
| **Proactivo** | `friday/core/notifier.py` | Umbrales fijos (CPU/RAM/disco/costo/servicios) → notificaciones. |
| | `friday/core/proactive.py` | Política de severidad → evento WS (voz si critical, toast si warning). |
| | `friday/core/analyst.py` | Tendencias (media reciente vs baseline), sin LLM. |
| | `friday/core/briefing.py` | Briefings matutino/nocturno redactados con `brain.compose()`. |
| | `friday/core/activity.py` | Log en memoria de tools ejecutadas (para el HUD). |
| **Collectors** | `friday/collectors/base.py` | Interfaz `Collector` (`source`, `interval_seconds`, `collect()`). |
| | `system.py` · `gemini_usage.py` | SO local · tokens/costo por modelo (precios en `config.gemini_pricing`). |
| | `nexcourt.py` · `cloudwatch.py` | NEXCOURT local (Actuator) · en AWS ECS/CloudWatch (read-only). |
| | `axis.py` | AXIS por SSH (`docker ps/stats`), alias `axis` en `~/.ssh/config`. |
| **Integraciones** | `friday/integrations/spotify.py` (+`spotify_auth.py`) | Web API (requiere Premium). Auth one-time: `friday-spotify-auth`. |
| | `gastos.py` | Google Sheets vía service account; `registrar_gasto` parsea la frase en Python. |
| | `web_research.py` | `buscar_web` (ddgs) + `leer_pagina` (trafilatura, tope 6000 chars). |
| | `lights.py` + `ir/` | Luces LED por estado de voz vía IR (Broadlink o mock). |
| **Storage** | `friday/storage/db.py` | Conexión + migraciones (`schema_version` en `_meta`). Tabla nueva = acá. |
| | `metrics_repo` · `chat_repo` · `notification_repo` · `memory_repo` | Repos SQLite (todos con el mismo lock). |
| | `knowledge_store.py` | Documentos markdown en `knowledge/` (research). |
| **API** | `friday/api/main.py` | `create_app()`: monta routers (casi todos bajo `/api`). |
| | `routes_*.py` | chat, agent (`/api/agent/run|confirm|tools|activity`), status/metrics, notifications, research, routines, lights/ir, nexcourt (re-login AWS), voice (log del listener), health, gastos, proactive/test, dashboard (`/`). |
| | `ws.py` | `/ws/live`: métricas, "thinking", estado de servicios, eventos proactivos. |
| **UI** | `friday/dashboard_web/index.html` | HUD "Command Center" (HTML puro, sin build). Intervalos en `POLL_INTERVALS`; escrituras al DOM por `__setHTML`/`__setText` (solo si cambió); alertas por WS. |
| | `friday/dashboard/` | Streamlit legacy (solo con `friday --streamlit`). |
| **Voz** | `friday/voice/wake.py` | Listener completo (wake word, VAD, STT, TTS, barge-in, mute, proactivo). Funciones `[SO]`: `_play_wav_async`, `_show_toast`, `launch_friday`, `shutdown_systems`. |
| | `friday/voice/shutdown_friday.sh` | Mata procesos por patrón/puerto; descarga modelos de Ollama. |
| **Scripts** | `scripts/macos/setup.sh` | Instalación completa e idempotente. |
| | `scripts/macos/install_autostart.sh` | LaunchAgent del listener (template en `com.friday.wake.plist.template`). |
| | `scripts/gen_tool_index.py` | Regenera `docs/TOOLS.md` (test `tests/test_tool_index.py` lo exige). |
| | `scripts/fix_codemap_refs.py` | Recalcula las `simbolo():N` de este archivo (test `tests/test_codemap.py` lo exige). |
| **Legacy** | `friday/main.py`, `friday/core/cli.py` | Entrypoints de fases viejas; **nadie los importa** (usar `friday --cli`). Candidatos a borrar. |

`tests/` espeja `friday/` 1:1 (`tests/core/test_brain.py` ↔ `friday/core/brain.py`, etc.).

## 3. Recetas: "quiero…"

| Quiero… | Tocar | No olvidar |
|---|---|---|
| **Agregar una acción** (algo que FRIDAY *hace*) | función en `friday/integrations/<x>.py` o `agent/actions/` + `reg.register(...)` en `agent/setup.py:build_action_registry` | Riesgo honesto (escritura/externo → MEDIUM/HIGH). Docstring: 1ra línea corta + `Args:`. Regenerar `docs/TOOLS.md`. |
| **Agregar una tool de lectura** | closure en `core/tools_registry.py:build_registry` (o `register_*_tools` propio llamado desde `app.py`) | Devolver JSON compacto; resultados grandes se recortan en turnos siguientes. |
| **Agregar un collector** | subclase de `collectors/base.Collector` + alta en `app.py:_register_collectors` | Emitir `MetricPoint` con `source` estable (lo usan HUD y notifier). |
| **Cambiar modelos / thinking** | `config.py` (`gemini_model_*`, `gemini_thinking_levels`, `ollama_model`) o `.env` | Precio nuevo en `gemini_pricing`. Ver [MODELS.md](MODELS.md). |
| **Cambiar personalidad / reglas de voz** | `core/llm_base.py:FRIDAY_SYSTEM_PROMPT` | Cada token acá viaja en *todas* las llamadas. |
| **Nuevo alias de app** ("abrí X") | `_MAC_APP_TARGETS` en `agent/actions/pc_actions.py` | Nombre exacto de la app en `/Applications`. |
| **Nuevo aviso proactivo** | regla en `core/notifier.py` (umbral) o `core/analyst.py` (tendencia) | Nivel `critical` habla en voz: usarlo con cuidado. |
| **Nueva tabla SQLite** | `storage/db.py` (migración + subir `schema_version`) + repo nuevo con el lock compartido | — |
| **Nueva ruta HTTP** | `api/routes_<x>.py` + `include_router` en `api/main.py` | La API no tiene auth: queda en 127.0.0.1. |
| **Cambiar comandos de voz** (stop/mute/shutdown) | constantes `EXIT_WORDS`, `MUTE_WORDS`, `SHUTDOWN_WORDS` en `voice/wake.py` | "unmute" no existe en el vocabulario de Vosk → se usa "resume". |
