# FRIDAY — guía para agentes

Asistente personal por voz de Gonzalo (estilo Jarvis). Python 3.12, nativo en **macOS Apple Silicon**
(M4, 16 GB). Dos procesos en `127.0.0.1`: listener de voz `friday/voice/wake.py` (LaunchAgent) →
HTTP/WS → backend `friday.app` (FastAPI :8000 + APScheduler + SQLite). Cerebro: Gemini 3.x con
fallback a Ollama (Gemma 4). Docs y código en español; la persona de FRIDAY habla en inglés.

## Antes de buscar, leé el índice

| Necesito… | Ir a |
|---|---|
| Dónde está X / qué hace cada archivo / flujo de un turno | `docs/CODEMAP.md` (grafo + tabla + recetas) |
| Qué tools ve el LLM (firma, riesgo, archivo:línea, tamaño) | `docs/TOOLS.md` (generado) |
| Qué modelo usar, precios, thinking, costo por turno | `docs/MODELS.md` |
| Por qué está diseñado así + gotchas | `docs/ARCHITECTURE.md` |
| Traer voz/secretos desde la PC Windows vieja | `docs/MIGRATION.md` |
| Cualquier knob (modelos, umbrales, horarios) | `friday/config.py` (`Settings`; `.env` lo pisa) |

No leas `FRIDAY_IMPLEMENTATION_PLAN.md` (histórico, Windows) ni `friday/dashboard/` (Streamlit legacy)
salvo que la tarea sea sobre eso. `friday/main.py` y `friday/core/cli.py` no se usan.

## Comandos

```bash
./venv/bin/python -m pytest -q                 # ~450 tests, <5 s. Correr SIEMPRE antes de terminar
./venv/bin/python scripts/gen_tool_index.py    # tras tocar cualquier tool (si no, falla un test)
./venv/bin/ruff check friday tests
bash start.sh / bash stop.sh                   # backend (log: friday.log)
./venv/bin/friday --cli                        # chat por terminal, sin API
launchctl kickstart -k gui/$(id -u)/com.friday.wake   # reiniciar listener (log: voices/friday-wake.log)
bash scripts/macos/setup.sh                    # instalación completa idempotente
```

## Invariantes (no romper)

- **Tools**: la 1ra línea del docstring ES la descripción que ve el LLM (+ `Args:`). Corta y precisa;
  cada char viaja en todas las llamadas. Acciones nuevas → `agent/setup.py:build_action_registry` con
  `RiskLevel` honesto (escritura/externo = MEDIUM/HIGH → pasa por `PermissionGate`).
- **Prefijo estable**: nada volátil (hora, contadores, random) en el system prompt ni en los schemas —
  rompe el cache implícito de Gemini y el KV-cache de Ollama. La hora va en el mensaje
  (`core/context_window.py:with_time_note`).
- **subprocess siempre con argv en lista, nunca `shell=True`**; datos a AppleScript por `argv`, no
  interpolados. URLs: solo `http/https/spotify:`.
- **API en `127.0.0.1`** (no tiene auth; el agente lee archivos). No cambiar el default de `api_host`.
- **Clientes HTTP a `127.0.0.1`, no `localhost`** (IPv6 primero = +21 s con Ollama).
- **Modelos Gemini 3.x**: thinking no se apaga y cuenta en `max_output_tokens` → no bajar
  `gemini_max_output_tokens` para "acortar" respuestas; la brevedad la da el prompt.
- **SQLite**: una conexión + `RLock` compartido (`app.py`); repos nuevos reciben ese lock.
- **Secretos** (`.env`, tokens, JSON de service account) nunca al repo. `voices/` está ignorado salvo
  `voices/jarvis.wav`.
- Diferencias de SO del backend solo en `friday/platform_info.py`; en el listener, funciones `[SO]`.

## Convenciones

- Tests espejan el paquete (`tests/core/test_brain.py` ↔ `friday/core/brain.py`); mocks de Gemini con
  `MagicMock`, de Ollama con `respx`. Subprocess se mockea en `pc_actions.subprocess.run`.
- Comentarios explican el **porqué** (incidente/decisión), en español rioplatense, como el código existente.
- Mensajes de tools al LLM: honestos ("No pude…", "no estaba abierta"), nunca éxito inventado.
- Commits en español, estilo `feat:/fix:/chore:/docs:`.
