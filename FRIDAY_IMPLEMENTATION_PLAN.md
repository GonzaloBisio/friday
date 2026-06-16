# FRIDAY — Documento de Diseño y Plan de Implementación

> **Para:** Claude Code (sesión de implementación desde terminal)
> **De:** Gonzalo
> **Estado:** Aprobado para empezar — backend primero, luego shell del frontend
> **Fecha:** 2026-06-16

---

## 0. Cómo usar este documento

Sos Claude Code y vas a construir **FRIDAY** desde cero en `C:\Users\gonza\Desktop\Friday`.
Implementá **fase por fase**, en orden. No avances de fase hasta que la anterior corra y tenga sus tests en verde. Al final de cada fase, dejá un commit limpio y un breve resumen de lo hecho.

Reglas no negociables:
- **Todo módulo de backend nuevo lleva tests** (pytest) en el mismo commit. Mínimo 3 escenarios por servicio: éxito, error/`not found`, y una regla de negocio/validación. No marques una fase como completa con tests rojos.
- **Nunca** ejecutes acciones destructivas sobre la PC sin pasar por el sistema de allowlist + confirmación (Fase 6).
- Secretos (API key de Gemini, credenciales NEXCOURT) **siempre** en `.env`, nunca hardcodeados ni commiteados.
- Entorno: **Windows 11**, **Python 3.11+**, **Node 20+**, shell PowerShell.

---

## 1. Visión

**FRIDAY** es un asistente personal estilo JARVIS, con cerebro **Google Gemini**, que corre como **app de escritorio** en la PC de Gonzalo. Cumple tres funciones:

1. **Observar** — recolecta y guarda métricas de cuatro fuentes (NEXCOURT, uso de Gemini, productividad personal, salud del sistema).
2. **Mostrar** — una UI de escritorio estilo HUD muestra esos KPIs en vivo: qué está arriba/abajo, performance, costos, índices.
3. **Conversar y actuar** — Gonzalo le pregunta en lenguaje natural ("¿cómo viene NEXCOURT?", "¿cuánto me gastó Gemini este mes?") y FRIDAY responde consultando sus propios datos; además puede ejecutar acciones acotadas sobre la PC.

### Métricas a trackear

| Grupo | Qué | Fuente |
|---|---|---|
| **NEXCOURT** | salud por servicio, requests, errores, latencia, usuarios activos | API Spring Boot Actuator + endpoint de negocio |
| **Uso de Gemini** | requests, tokens in/out, costo estimado | wrapper propio sobre el SDK |
| **Productividad** | tareas completadas, foco, hábitos | entrada manual / fuentes locales |
| **Salud del sistema** | CPU, RAM, disco, uptime, red, procesos | `psutil` |

---

## 2. Arquitectura (cliente/servidor en una app de escritorio)

FRIDAY es una app de escritorio compuesta por dos partes que corren en la misma máquina:

```
┌─────────────────────────────────────────────────────┐
│  Ventana Tauri (frontend React + Tailwind, HUD dark) │
│   sidebar · hero+radar · chat · paneles · gauges     │
└───────────────▲───────────────────▲─────────────────┘
                │ REST (snapshot)    │ WebSocket (live)
┌───────────────┴───────────────────┴─────────────────┐
│  Backend Python (FastAPI)                            │
│   core (Gemini) · collectors · agent · storage       │
│   APScheduler corre los collectors → SQLite          │
└──────────────────────────────────────────────────────┘
            │            │             │
        NEXCOURT     Gemini API     PC (psutil/allowlist)
```

Decisiones cerradas:
- **Frontend:** **Tauri** (ventana nativa liviana) + **React + Vite + TailwindCSS**. Estética HUD oscura fija (ver §9).
- **Backend:** **Python + FastAPI**, expone **REST** (snapshots/consultas) y **WebSocket** (métricas en vivo + pasos de "pensamiento" del chat). Mantiene toda la lógica (core/collectors/agent/storage).
- **Arranque:** Tauri levanta el backend Python como **sidecar** (proceso hijo) al abrir la app. En desarrollo se corren por separado.
- **Almacenamiento:** **SQLite** como serie temporal simple (cero infra), append-only.
- **NEXCOURT:** ya desarrollado. FRIDAY lo consulta por **HTTP polling** contra Spring Boot Actuator (`/actuator/health`, `/actuator/prometheus`) + endpoint de negocio opcional.
- **Control de PC:** **allowlist** — catálogo cerrado de acciones; riesgo medio/alto pide confirmación (modal en la UI).
- **Scheduler:** `APScheduler` corre los collectors en intervalos en el backend.

---

## 3. Stack técnico

### Backend (Python 3.11+)
| Pieza | Librería | Notas |
|---|---|---|
| API | `fastapi` + `uvicorn` | REST + WebSocket |
| Cerebro IA | `google-genai` | Gemini; `gemini-2.5-pro` (razonamiento), `gemini-2.5-flash` (rápido/barato) |
| HTTP cliente | `httpx` | poll a NEXCOURT (async) |
| Scheduler | `apscheduler` | jobs periódicos de collectors |
| Métricas SO | `psutil` | CPU/RAM/disco/red/procesos |
| Storage | `sqlite3` (stdlib) | tabla de MetricPoint; `sqlalchemy` opcional |
| Config | `pydantic-settings` + `python-dotenv` | `.env` tipado |
| Tests | `pytest` + `pytest-mock` + `respx` | mock de HTTP y del SDK |
| Lint | `ruff` | format + lint |

### Frontend (Node 20+)
| Pieza | Librería | Notas |
|---|---|---|
| Shell nativo | `Tauri` (Rust) | ventana, sidecar del backend, empaquetado Windows |
| UI | `React` + `Vite` + `TypeScript` | |
| Estilos | `TailwindCSS` | tema HUD oscuro (tokens en §9) |
| Estado/datos | `@tanstack/react-query` + WebSocket nativo | snapshots + stream en vivo |
| Gráficos | `recharts` o `visx` | líneas de tiempo, gauges (anillos SVG) |
| Iconos | `@tabler/icons-react` | set del boceto |

---

## 4. Estructura del proyecto

```
Friday/
├─ backend/
│  ├─ friday/
│  │  ├─ __init__.py
│  │  ├─ config.py              # settings pydantic (.env)
│  │  ├─ core/
│  │  │  ├─ brain.py            # cliente Gemini + bucle de function calling
│  │  │  └─ tools_registry.py   # tools expuestas a Gemini
│  │  ├─ collectors/
│  │  │  ├─ base.py             # interfaz Collector
│  │  │  ├─ system.py           # psutil
│  │  │  ├─ gemini_usage.py     # tokens/costo
│  │  │  ├─ productivity.py     # métricas personales
│  │  │  └─ nexcourt.py         # poll a NEXCOURT
│  │  ├─ storage/
│  │  │  ├─ db.py               # SQLite + migraciones simples
│  │  │  └─ metrics_repo.py     # guardar/consultar MetricPoint
│  │  ├─ agent/
│  │  │  ├─ registry.py         # @tool, allowlist, niveles de riesgo
│  │  │  ├─ permissions.py      # gate de confirmación
│  │  │  └─ actions/            # acciones concretas
│  │  └─ scheduler.py           # APScheduler: corre collectors
│  ├─ api/
│  │  ├─ main.py                # app FastAPI (REST + WS)
│  │  ├─ routes_status.py       # /api/status, /api/metrics
│  │  ├─ routes_chat.py         # /api/chat
│  │  ├─ routes_agent.py        # /api/agent/*
│  │  └─ ws.py                  # /ws/live (push de métricas + thinking)
│  ├─ tests/
│  ├─ .env.example
│  ├─ requirements.txt
│  └─ pyproject.toml
├─ frontend/
│  ├─ src/
│  │  ├─ App.tsx
│  │  ├─ theme.ts               # paleta HUD (§9)
│  │  ├─ api/                   # cliente REST + hook de WebSocket
│  │  ├─ layout/                # Sidebar, TopBar, StatusBar
│  │  └─ panels/                # Hero+Radar, Chat, Thinking, Vitals, SystemGauges, Nexcourt
│  ├─ src-tauri/                # config Tauri + sidecar del backend
│  ├─ index.html
│  ├─ package.json
│  └─ tailwind.config.js
├─ .gitignore
└─ README.md
```

---

## 5. Modelo de datos

Todas las métricas se normalizan a un **MetricPoint** y se guardan append-only:

```python
@dataclass
class MetricPoint:
    timestamp: datetime      # UTC
    source: str              # "nexcourt" | "gemini" | "system" | "productivity"
    service: str | None      # ej. "nexcourt-clubs-service" (opcional)
    name: str                # ej. "cpu_percent", "tokens_out", "errors_last_hour"
    value: float
    unit: str | None         # "%", "ms", "tokens", "usd", "count"
    tags: dict | None        # metadata libre (status, region, etc.)
```

Tabla SQLite `metrics(id, ts, source, service, name, value, unit, tags_json)`, índice `(source, name, ts)`.

---

## 6. Contrato de la API (backend ↔ frontend)

REST:
- `GET /api/status` → snapshot de signos vitales (NEXCOURT up/total, Gemini hoy/mes USD, CPU/RAM/disco/uptime, tareas/foco, estado de servicios para la barra inferior).
- `GET /api/metrics?source=&name=&from=&to=` → serie temporal para gráficos.
- `POST /api/chat` `{ message }` → respuesta de FRIDAY (Gemini). Los pasos intermedios ("pensando…") se emiten por WS.
- `GET /api/agent/tools` → catálogo (allowlist) de acciones disponibles.
- `POST /api/agent/run` `{ tool, args }` → ejecuta; si la acción es `confirm=True` devuelve `pending` hasta confirmación.
- `POST /api/agent/confirm` `{ action_id, approved }`.

WebSocket `/ws/live`:
- push de métricas nuevas (para gauges/vitales en vivo),
- push de pasos de "pensamiento" del chat (panel Thinking),
- push de cambios de estado de servicios (barra inferior).

---

## 7. Integración NEXCOURT (contrato de conexión)

NEXCOURT es **Spring Boot (microservicios)** detrás de Kong. Config en `.env`:

```
NEXCOURT_BASE_URL=https://<kong-o-host>:<port>
NEXCOURT_SERVICES=nexcourt-clubs-service,nexcourt-...
NEXCOURT_API_KEY=...
NEXCOURT_POLL_INTERVAL_SECONDS=30
```

El collector `nexcourt.py` debe:
1. **Salud:** `GET {base}/{service}/actuator/health` → mapear `UP`/`DOWN` a `nexcourt.status` (1/0) con tag `{service}`.
2. **Métricas:** preferir `GET {base}/{service}/actuator/prometheus` (parsear `http_server_requests_seconds_count`/`_sum`, `jvm_memory_used_bytes`, etc.). Fallback a `/actuator/metrics/{name}`.
3. **Negocio (opcional):** `GET /metrics` JSON `{ timestamp, service, status, metrics:{requests_total, active_users, errors_last_hour, latency_p95_ms} }`.
4. **Resiliencia:** timeouts, reintentos con backoff; servicio caído → `nexcourt.status=0` sin romper el scheduler.

> Verificá rutas reales de Actuator/Kong en el repo de NEXCOURT (`C:\Users\gonza\Desktop\CourtMaster\NexCourt`, revisar `application*.yml` → `management.endpoints` y prefijos de Kong) antes de fijar las URLs.

---

## 8. Integración Gemini

- Wrapper `core/brain.py` centraliza **todas** las llamadas a `google-genai`.
- Cada llamada registra un `MetricPoint` `source="gemini"`: `requests`, `tokens_in`, `tokens_out`, `cost_usd` estimado (tabla de precios por modelo en `config.py`).
- **Function calling:** Gemini recibe el catálogo de tools y puede invocar:
  - `consultar_metricas(source, name, rango)` → lee SQLite ("¿cómo viene NEXCOURT?").
  - `resumen_costos(rango)` → agrega `cost_usd` ("¿cuánto gasté este mes?").
  - acciones de PC (Fase 6), sujetas a allowlist.
- `GEMINI_API_KEY` en `.env`. Nunca loguear la key.

---

## 9. Frontend: shell de escritorio estilo JARVIS

Dirección visual **aprobada** (ref.: bocetos "friday_jarvis_shell_dark" y "friday_hud_conversational_dark"). App de escritorio con **estética HUD oscura fija** (no sigue el tema del SO).

Layout (shell de app):
- **Sidebar izquierda:** logo "FRIDAY · INTEL SYSTEM" + navegación con iconos (Dashboard, Chat, Agents, Tasks, Memory, Tools, NEXCOURT, Health). Ítem activo resaltado con fondo, no borde lateral.
- **Top bar:** input "Preguntale a FRIDAY…", indicador ONLINE, reloj, selector de modelo, iconos de acción.
- **Hero:** saludo ("Buenas tardes, Gonzalo"), "¿En qué te ayudo hoy?", waveform y **radar/órbita** animado (SVG, sin glow). Accesos rápidos (Compose, Research, Execute, Debug).
- **Tarjetas de estado:** Modelo actual (gemini-2.5-pro), Tools activas, Tareas en curso, Memoria.
- **Panel derecho:** "Estado" (online/degradado), "FRIDAY pensando" (checklist en vivo vía WS), Actividad reciente, **System Overview** (gauges de anillo CPU/RAM/Disco/Net).
- **Chat:** burbujas conversacionales con chips de métricas inline; input con micrófono (voz = extra futuro).
- **Barra inferior de servicios:** dots de estado (SQLite, Redis, Gemini, NEXCOURT, Tailscale) + "sincronizado recién".

### Tema HUD (paleta fija — Tailwind tokens)

| Rol | Hex |
|---|---|
| Fondo app | `#0A0E14` |
| Superficie / panel | `#0C1320` / `#0C1118` |
| Burbuja neutra | `#1A232E` |
| Texto primario | `#E6EDF3` |
| Texto secundario | `#8B97A5` / `#5C6773` |
| Acento (cian/teal) | `#2DD4BF` / `#38BDF8` |
| Acento secundario (púrpura) | `#7F77DD` / `#D4537E` |
| Éxito | `#41C682` · Warning `#F5B445` · Peligro `#E2575B` |

Detalles: bordes finos `rgba(255,255,255,0.07)`, esquinas 8–14px, **fuente monoespaciada para números/labels técnicos**, **sin glow/neón** (planos y limpios). Gauges = anillos SVG con `stroke-dasharray` (no conic-gradient). Los datos en runtime salen de `/api/status` y `/ws/live`.

---

## 10. Plan por fases (orden de ejecución)

### Fase 1 — Backend: cimientos
- Scaffolding de `backend/` (`requirements.txt`, `pyproject.toml`, `.env.example`, ruff).
- `config.py` (pydantic-settings), `storage/db.py` + `metrics_repo.py` (tabla `metrics`, `save()/query()`).
- App FastAPI mínima con `GET /api/status` (datos mock al principio) y healthcheck.
- **Tests:** repo de métricas (guardar, consultar por rango, vacío). 
- **DoD:** `pytest` verde; `uvicorn` levanta y `/api/status` responde.

### Fase 2 — Backend: collectors + tiempo real
- `collectors/base.py` + `system.py` (psutil) + `gemini_usage.py`.
- `scheduler.py` (APScheduler) persistiendo en SQLite; `GET /api/metrics` real; `/ws/live` empuja métricas.
- **Tests:** cada collector (éxito, fuente no disponible, valor inválido) con psutil/SDK mockeados.
- **DoD:** la DB se llena con métricas reales del sistema y el WS emite updates.

### Fase 3 — Frontend: shell HUD
- App Tauri + React + Vite + Tailwind con el tema HUD.
- Layout completo: sidebar, top bar, hero+radar, tarjetas, panel derecho con **gauges** y barra de servicios, consumiendo `/api/status` + `/ws/live`.
- Tauri levanta el backend como sidecar.
- **DoD:** la ventana abre y muestra CPU/RAM/uptime, costo de Gemini y estado de servicios reales, en vivo.

### Fase 4 — Core conversacional
- `core/brain.py` (Gemini + function calling) + `tools_registry.py`; tools de lectura (`consultar_metricas`, `resumen_costos`).
- `POST /api/chat` + panel de Chat en la UI + panel "FRIDAY pensando" alimentado por WS.
- **Tests:** registro de tools y parseo de respuestas del modelo (SDK mockeado).
- **DoD:** preguntar "¿cómo viene el sistema?" en la UI devuelve datos reales de la DB.

### Fase 5 — Agente de PC
- `agent/registry.py`, `permissions.py`, `actions/` (set inicial: `abrir_app`, `listar_procesos`, `leer_archivo` low; `mover_archivo`, `ejecutar_comando` medium/high con confirm).
- `/api/agent/*` + modal de confirmación en la UI para acciones riesgosas.
- **Tests:** allowlist (permitida vs. rechazada), gate de confirmación, logging.
- **DoD:** FRIDAY abre una app por pedido en lenguaje natural; una acción riesgosa pide confirmación.

### Fase 6 — NEXCOURT
- `collectors/nexcourt.py` (Actuator/Prometheus + negocio) + panel NEXCOURT en la UI + tool `consultar_metricas(source="nexcourt")`.
- **Tests:** parseo de health y prometheus, servicio caído → `status=0`, timeout/reintento (HTTP mockeado).
- **DoD:** preguntar "¿cómo viene NEXCOURT?" devuelve estado y métricas reales.

### Fase 7 (después) — Empaquetado
- Bundle del backend con PyInstaller como sidecar de Tauri; instalador Windows. (No bloquea el MVP.)

---

## 11. Estándar de testing (obligatorio)

- Backend: **pytest** + `pytest-mock`/`unittest.mock`; HTTP con `respx`. Por cada módulo de servicio (collector, repo, agente, brain): mínimo **3 escenarios** — éxito, error/no disponible, regla de validación/negocio. `pytest -q` verde antes de cerrar cada fase.
- No se testean DTOs/dataclasses triviales.
- Frontend: tests de componentes con `vitest` + Testing Library **recomendados** para lógica no trivial (hook de WS, formateo de métricas); no obligatorios para layout puro.

---

## 12. Convenciones

- Identificadores en inglés; mensajes/UI en español.
- Type hints en todo el Python; TypeScript estricto en el frontend.
- `ruff` (Python) y `eslint`/`prettier` (frontend).
- Sin secretos en el repo; `.env` en `.gitignore`.
- **Round** de todo número que llega a la UI.
- Commits por fase con mensaje claro.

---

## 13. Primer paso concreto para Claude Code

1. Inicializar git en `C:\Users\gonza\Desktop\Friday`.
2. Crear el scaffolding de **backend/** (Fase 1): config, storage, FastAPI con `/api/status` mock, tests.
3. Dejar `.env.example` listo y pedir a Gonzalo la `GEMINI_API_KEY` y los datos de `NEXCOURT_BASE_URL`/servicios.
4. Correr `pytest`, verificar que `uvicorn` levanta, y reportar antes de pasar a la Fase 2.
