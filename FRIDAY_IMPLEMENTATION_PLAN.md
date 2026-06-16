# FRIDAY — Documento de Diseño y Plan de Implementación

> **Para:** Claude Code (sesión de implementación desde terminal)
> **De:** Gonzalo
> **Estado:** Aprobado para empezar — fases 1 a 3 primero
> **Fecha:** 2026-06-16

---

## 0. Cómo usar este documento

Sos Claude Code y vas a construir **FRIDAY** desde cero en `C:\Users\gonza\Desktop\Friday`.
Implementá **fase por fase**, en orden. No avances de fase hasta que la anterior corra y tenga sus tests en verde. Al final de cada fase, dejá un commit limpio y un breve resumen de lo hecho.

Reglas no negociables:
- **Todo módulo nuevo lleva tests** (pytest) en el mismo commit. Mínimo 3 escenarios por servicio: éxito, error/`not found`, y una regla de negocio/validación. No marques una fase como completa con tests rojos.
- **Nunca** ejecutes acciones destructivas sobre la PC sin pasar por el sistema de allowlist + confirmación descrito en la Fase 5.
- Secretos (API key de Gemini, credenciales NEXCOURT) **siempre** en `.env`, nunca hardcodeados ni commiteados.
- Entorno: **Windows 11**, **Python 3.11+**, shell PowerShell.

---

## 1. Visión

**FRIDAY** es un asistente personal estilo JARVIS, con cerebro **Google Gemini**, que vive en la PC de Gonzalo. Cumple tres funciones:

1. **Observar** — recolecta y guarda métricas de cuatro fuentes (NEXCOURT, uso de Gemini, productividad personal, salud del sistema).
2. **Mostrar** — un dashboard local muestra esos KPIs en vivo: qué está arriba/abajo, performance, costos, índices.
3. **Conversar y actuar** — Gonzalo le pregunta en lenguaje natural ("¿cómo viene NEXCOURT?", "¿cuánto me gastó Gemini este mes?") y FRIDAY responde consultando sus propios datos; además puede ejecutar acciones acotadas sobre la PC.

### Métricas a trackear

| Grupo | Qué | Fuente |
|---|---|---|
| **NEXCOURT** | salud por servicio, requests, errores, latencia, usuarios activos | API Spring Boot Actuator + endpoint de negocio |
| **Uso de Gemini** | requests, tokens in/out, costo estimado | wrapper propio sobre el SDK |
| **Productividad** | tareas completadas, foco, hábitos | entrada manual / fuentes locales |
| **Salud del sistema** | CPU, RAM, disco, uptime, procesos de FRIDAY | `psutil` |

---

## 2. Decisiones de arquitectura (cerradas)

- **Estilo:** monolito modular (un proceso, módulos desacoplados). Simple de correr en una PC.
- **Cerebro:** Google Gemini vía SDK `google-genai`, con **function calling** (Gemini elige qué herramienta usar).
- **Almacenamiento:** **SQLite** como serie temporal simple (cero infra). Una tabla de métricas append-only + tablas auxiliares.
- **NEXCOURT:** ya está desarrollado. FRIDAY lo consulta vía **HTTP polling** contra Spring Boot Actuator (`/actuator/health`, `/actuator/prometheus`) y un endpoint de negocio opcional. URL base configurable (apunta a Kong o directo al servicio).
- **Control de PC:** **allowlist** — catálogo cerrado de acciones; las de riesgo medio/alto piden confirmación.
- **Dashboard:** **Streamlit** local en `localhost`, auto-refresco.
- **Scheduler:** `APScheduler` para correr los collectors en intervalos.

---

## 3. Stack técnico

| Pieza | Librería | Notas |
|---|---|---|
| Lenguaje | Python 3.11+ | |
| Cerebro IA | `google-genai` | SDK unificado de Gemini; usar modelo `gemini-2.5-pro` para razonamiento y `gemini-2.5-flash` para tareas rápidas/baratas |
| HTTP | `httpx` | cliente async para pollear NEXCOURT |
| Scheduler | `apscheduler` | jobs periódicos de los collectors |
| Métricas SO | `psutil` | CPU/RAM/disco/procesos |
| Storage | `sqlite3` (stdlib) + `sqlalchemy` (opcional) | empezar con `sqlite3` plano |
| Dashboard | `streamlit` + `plotly` | gráficos y KPIs |
| Config | `python-dotenv` + `pydantic-settings` | `.env` + settings tipadas |
| Tests | `pytest` + `pytest-mock` + `responses`/`respx` | mock de HTTP y del SDK |
| Logging | `structlog` o `logging` stdlib | logs estructurados |

---

## 4. Estructura del proyecto

```
Friday/
├─ friday/
│  ├─ __init__.py
│  ├─ main.py                 # entrypoint: arranca scheduler + (opcional) dashboard
│  ├─ config.py               # settings con pydantic (lee .env)
│  ├─ core/
│  │  ├─ brain.py             # cliente Gemini + bucle de function calling
│  │  └─ tools_registry.py    # registro de "tools" expuestas a Gemini
│  ├─ collectors/
│  │  ├─ base.py              # interfaz Collector (run() -> list[MetricPoint])
│  │  ├─ system.py            # psutil
│  │  ├─ gemini_usage.py      # tokens/costo
│  │  ├─ productivity.py      # métricas personales
│  │  └─ nexcourt.py          # poll a NEXCOURT Actuator + negocio
│  ├─ storage/
│  │  ├─ db.py                # conexión SQLite + migraciones simples
│  │  └─ metrics_repo.py      # guardar/consultar MetricPoint
│  ├─ agent/
│  │  ├─ registry.py          # @tool decorator, allowlist, niveles de riesgo
│  │  ├─ permissions.py       # confirmación para acciones riesgosas
│  │  └─ actions/             # acciones concretas (abrir app, mover archivo, etc.)
│  └─ dashboard/
│     └─ app.py               # Streamlit
├─ tests/
│  ├─ collectors/
│  ├─ storage/
│  ├─ agent/
│  └─ core/
├─ .env.example
├─ .gitignore
├─ requirements.txt
├─ pyproject.toml
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

Tabla SQLite `metrics(id, ts, source, service, name, value, unit, tags_json)`, con índice `(source, name, ts)`.

---

## 6. Integración NEXCOURT (contrato de conexión)

NEXCOURT es **Spring Boot (microservicios)** detrás de Kong. FRIDAY lo consulta por HTTP. Configuración esperada en `.env`:

```
NEXCOURT_BASE_URL=https://<kong-o-host>:<port>
NEXCOURT_SERVICES=nexcourt-clubs-service,nexcourt-...    # lista de servicios
NEXCOURT_API_KEY=...                                     # si aplica
NEXCOURT_POLL_INTERVAL_SECONDS=30
```

El collector `nexcourt.py` debe:

1. **Salud:** por cada servicio, `GET {base}/{service}/actuator/health` → mapear `status` (`UP`/`DOWN`) a `nexcourt.status` (1/0) con tag `{service}`.
2. **Métricas:** preferir `GET {base}/{service}/actuator/prometheus` y parsear las series relevantes (`http_server_requests_seconds_count`, `..._sum` para latencia, `jvm_memory_used_bytes`, etc.). Si no está expuesto, caer a `/actuator/metrics/{metric.name}`.
3. **Negocio (opcional):** si NEXCOURT expone un endpoint propio tipo `GET /metrics` con JSON, parsearlo:
   ```json
   {
     "timestamp": "2026-06-16T12:00:00Z",
     "service": "nexcourt",
     "status": "up",
     "metrics": { "requests_total": 1234, "active_users": 42, "errors_last_hour": 3, "latency_p95_ms": 180 }
   }
   ```
4. **Resiliencia:** timeouts, reintentos con backoff, y si un servicio no responde → registrar `nexcourt.status=0` (no romper el ciclo). Nunca dejar caer el scheduler por un error de red.

> Verificá las rutas reales de Actuator/Kong contra el repo de NEXCOURT en `C:\Users\gonza\Desktop\CourtMaster\NexCourt` (revisá `application*.yml` para `management.endpoints` y prefijos de Kong) antes de fijar las URLs.

---

## 7. Integración Gemini

- Wrapper `core/brain.py` que centraliza **todas** las llamadas al SDK `google-genai`.
- Cada llamada registra un `MetricPoint` con `source="gemini"`: `requests` (count), `tokens_in`, `tokens_out`, y `cost_usd` estimado (tabla de precios configurable por modelo en `config.py`).
- **Function calling:** Gemini recibe el catálogo de tools del `tools_registry` y puede invocar:
  - `consultar_metricas(source, name, rango)` → lee SQLite y responde ("¿cómo viene NEXCOURT?").
  - `resumen_costos(rango)` → agrega `cost_usd` ("¿cuánto me gastó este mes?").
  - acciones de PC (Fase 5), sujetas a allowlist.
- API key en `.env` como `GEMINI_API_KEY`. Nunca logiear la key.

---

## 8. Agente de PC (allowlist + confirmación)

Cada acción es una función registrada con nombre, parámetros tipados y nivel de riesgo:

```python
@tool(name="abrir_app", risk="low")
def abrir_app(nombre: str) -> str: ...

@tool(name="mover_archivo", risk="medium", confirm=True)
def mover_archivo(origen: str, destino: str) -> str: ...
```

Reglas del motor:
- Gemini **solo** puede invocar funciones presentes en el registro (allowlist). Cualquier otra cosa se rechaza.
- `risk="low"` ejecuta directo; `medium`/`high` requieren confirmación explícita del usuario antes de correr.
- Toda invocación queda logueada (acción, parámetros, resultado, timestamp).
- Set inicial mínimo: `abrir_app`, `listar_procesos`, `leer_archivo` (low); `mover_archivo`, `ejecutar_comando` (medium/high, confirm).

---

## 9. Dashboard (Streamlit)

`dashboard/app.py`, corre con `streamlit run friday/dashboard/app.py`. Lee todo desde SQLite (no llama APIs directo) y auto-refresca cada N segundos.

### Dirección visual elegida: asistente conversacional, HUD oscuro fijo

El layout principal es **conversacional** (FRIDAY al frente), no una grilla densa. Estética **oscura tipo HUD (Iron Man)**, con tema oscuro **fijo** (no sigue el tema del SO). Referencia visual aprobada: ver el boceto "friday_hud_conversational_dark".

Layout (dos columnas):
- **Columna principal (≈60%) — chat con FRIDAY:** burbujas de conversación; el usuario pregunta en lenguaje natural y FRIDAY responde con datos reales + chips de métricas inline (ej. "1.2k req/min", "3 err/h"). Input de texto abajo con botón de micrófono (voz es un extra futuro).
- **Columna lateral (≈40%) — signos vitales:** lista compacta con NEXCOURT (up/total), Gemini hoy/mes (USD), CPU, RAM, tareas/foco. Barras finas para CPU/RAM.
- **Header:** logo/estado "FRIDAY · ONLINE", reloj.

### Tema HUD (paleta fija)

Forzar tema oscuro vía `.streamlit/config.toml` (`[theme] base="dark"`) y CSS propio inyectado. Paleta de referencia:

| Rol | Hex |
|---|---|
| Fondo app | `#0B0F14` |
| Superficie / panel | `#10161E` |
| Burbuja neutra | `#1A232E` |
| Texto primario | `#E6EDF3` |
| Texto secundario | `#8B97A5` / `#5C6773` |
| Acento (cian/teal) | `#2DD4BF` / `#38BDF8` |
| Éxito | `#41C682` |
| Warning | `#F5B445` |
| Peligro | `#E2575B` |

Detalles de estilo: bordes finos `rgba(255,255,255,0.07)`, esquinas redondeadas (11–14px), **fuente monoespaciada para números/labels técnicos** (estética terminal), **sin glow/neón** (planos y limpios). Los números del boceto son placeholder; en runtime salen de SQLite.

> Nota: el render real en Streamlit puede requerir CSS inyectado con `st.markdown(unsafe_allow_html=True)` o un componente HTML para lograr el layout de burbujas; evaluá `streamlit-chat` o un componente custom si los widgets nativos no alcanzan.

---

## 10. Plan por fases (orden de ejecución)

### Fase 1 — Cimientos
- Scaffolding completo de carpetas, `requirements.txt`, `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`.
- `config.py` (pydantic-settings leyendo `.env`).
- `storage/db.py` + `storage/metrics_repo.py` con la tabla `metrics` y `save()/query()`.
- **Tests:** repo de métricas (guardar, consultar por rango, vacío/not found).
- **DoD:** `pytest` verde; se puede insertar y leer un MetricPoint.

### Fase 2 — Collectors base
- `collectors/base.py` (interfaz) + `system.py` (psutil) + `gemini_usage.py` (registro de uso).
- `APScheduler` corriendo los collectors en intervalo y persistiendo en SQLite.
- **Tests:** cada collector (éxito, fuente no disponible, valor inválido) con psutil/SDK mockeados.
- **DoD:** corriendo `main.py`, la DB se llena con métricas de sistema reales.

### Fase 3 — Dashboard
- `dashboard/app.py` con todas las secciones leyendo de SQLite, auto-refresco.
- **DoD:** `streamlit run ...` muestra CPU/RAM/uptime y uso de Gemini en vivo.

### Fase 4 — Core conversacional
- `core/brain.py` (Gemini + function calling) y `core/tools_registry.py`.
- Tools de lectura: `consultar_metricas`, `resumen_costos`.
- **Tests:** registro de tools y parseo de respuestas del modelo (SDK mockeado).
- **DoD:** desde una REPL/CLI, preguntar "¿cómo viene el sistema?" devuelve datos reales de la DB.

### Fase 5 — Agente de PC
- `agent/registry.py`, `agent/permissions.py`, `agent/actions/` con el set inicial.
- Integración con `tools_registry` para que Gemini las invoque bajo allowlist.
- **Tests:** allowlist (acción permitida vs. rechazada), gate de confirmación para `risk` alto, logging.
- **DoD:** FRIDAY abre una app por pedido en lenguaje natural; una acción riesgosa pide confirmación.

### Fase 6 — NEXCOURT
- `collectors/nexcourt.py` contra Actuator/Prometheus + endpoint de negocio.
- Sección NEXCOURT del dashboard con datos reales; tool `consultar_metricas(source="nexcourt")`.
- **Tests:** parseo de health y prometheus, servicio caído → `status=0`, timeout/reintento (HTTP mockeado).
- **DoD:** preguntar "¿cómo viene NEXCOURT?" devuelve estado y métricas reales.

---

## 11. Estándar de testing (obligatorio)

- Framework: **pytest**. Mocks con `pytest-mock`/`unittest.mock`; HTTP con `respx`/`responses`.
- Por cada módulo de servicio (collector, repo, agente, brain): mínimo **3 escenarios** — éxito, error/no disponible, y una regla de validación/negocio.
- No se testean DTOs/dataclasses triviales ni la UI de Streamlit.
- CI local: `pytest -q` debe pasar antes de cerrar cada fase.

---

## 12. Convenciones

- Código y nombres de función en español o inglés consistente (elegir uno; sugerido: identificadores en inglés, mensajes/UI en español).
- Type hints en todo el código nuevo. `ruff` para lint/format.
- Sin secretos en el repo; `.env` en `.gitignore`.
- Commits por fase, mensaje claro de qué incluye.

---

## 13. Primer paso concreto para Claude Code

1. Inicializar git en `C:\Users\gonza\Desktop\Friday`.
2. Crear el scaffolding de la **Fase 1** completo.
3. Pedir a Gonzalo la `GEMINI_API_KEY` y los datos de `NEXCOURT_BASE_URL`/servicios para completar el `.env` (dejar `.env.example` listo mientras tanto).
4. Implementar storage + tests, correr `pytest`, y reportar antes de pasar a la Fase 2.
