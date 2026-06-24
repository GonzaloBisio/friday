# FRIDAY — Roadmap e Integraciones

> A DÓNDE VAMOS. Para el estado actual, ver [ARCHITECTURE.md](ARCHITECTURE.md).
>
> **Objetivo**: dejar a FRIDAY *completamente operativo* — que observe los sistemas de
> Gonzalo y controle sus herramientas, **siempre con autorización humana** para lo sensible,
> manteniéndose local y gratis.

## Modelo de autorización

Toda capacidad nueva se registra como una **acción** (`ActionSpec`) en el `ActionRegistry`,
con un **nivel de riesgo**. El `PermissionGate` (`friday/agent/permissions.py`) decide:

| Riesgo | Qué incluye | Comportamiento |
|--------|-------------|----------------|
| **LOW** | Lectura / observabilidad | Ejecuta automáticamente |
| **MEDIUM** | Escritura reversible | Pide confirmación |
| **HIGH** | Acción externa / irreversible / oficial | Pide confirmación explícita |

**Regla de oro**: ante la duda, subir el riesgo. Lo peligroso SIEMPRE pregunta.

### Canales de confirmación (a construir)

Hoy el gate deja la acción "pendiente" pero **solo el dashboard puede confirmarla**
(`POST /api/agent/confirm`). Hay que cerrar el loop en los tres canales:

1. **Voz** (principal): FRIDAY dice *"¿Confirmás que publique X en LinkedIn, sir?"* → escucha
   sí/no → llama `gate.confirm`. **← Gap #1, máxima prioridad.**
2. **Dashboard**: panel de acciones pendientes con botones aprobar/rechazar (API ya existe).
3. **Push notification**: aprobar desde el celular si Gonzalo no está frente a la PC.

## Las integraciones

Patrón único: cada integración es un módulo en `friday/integrations/<nombre>.py` con funciones
simples, registradas como `ActionSpec` con su riesgo. Así **heredan la autorización gratis** y
el LLM las invoca por el mismo puente que las acciones de PC.

### 1. Observabilidad NEXCOURT (AWS) — ✅ HECHO · AXIS (SSH/Docker) — pendiente

> ⚠️ Corrección: **AXIS y NEXCOURT NO corren en el mismo lado.** Son dos mundos de
> observabilidad distintos. El único cluster ECS de la cuenta es `nexcourt-dev-cluster`.

**NEXCOURT — AWS ECS (✅ implementado)**
- **Qué son**: microservicios Spring Boot (`clubs/reservations/stock/reports/sports/media/
  notifications-service`) + `kong` (gateway) + `keycloak` (auth).
- **Dónde corren**: **AWS ECS** cluster `nexcourt-dev-cluster`, región `us-east-1`,
  cuenta `874587839949`.
- **Cómo lo observa FRIDAY**: `collectors/cloudwatch.py` (boto3, **read-only**). Estado y
  conteo de tareas vía ECS API (`describe_services`); CPU/memoria vía CloudWatch
  (`get_metric_data`). Emite `source="nexcourt"`. Se activa con `nexcourt_mode="cloudwatch"`.
- **Tools (LOW)**: `estado_sistemas()`, `metricas_servicio(servicio)`, `alarmas_activas()`,
  `errores_recientes(servicio, minutos)`.
- **Panel** en el dashboard: grilla de servicios con salud/CPU/mem.
- **Pendiente**: hoy **no hay alarmas de CloudWatch** configuradas → `alarmas_activas()`
  devuelve vacío. (Futuro, **HIGH**) acciones: reiniciar/escalar un servicio ECS — con confirmación.
- **Seguridad (sin cerrar)**: hoy corre con credenciales **root**. Crear un **IAM read-only**
  dedicado (cloudwatch:GetMetricData/DescribeAlarms, ecs:DescribeServices, logs:FilterLogEvents)
  y mover las creds al `.env`. **No usar el perfil root.** ⚠️

**AXIS — droplet SSH + Docker (✅ implementado)**
- **Dónde corre**: `axis-dev-droplet` (DigitalOcean), `ssh axis@174.138.52.161`. 7 containers
  Docker: backend (healthy), frontend, front, nginx, keycloak, postgres (healthy), logs. **No es AWS.**
- **Acceso**: key nativa de WSL autorizada en el droplet; alias `axis` en `~/.ssh/config`.
- **Cómo lo observa FRIDAY**: `collectors/axis.py` (SSH + `docker ps`/`docker stats`, read-only).
  Emite `source="axis"`. Se activa con `axis_enabled=true`.
- **Tools**: `estado_sistemas("axis")`, `metricas_servicio("axis-…")`, `errores_axis(container)`.
- **Panel** en el dashboard, al lado de NEXCOURT.

### 2. LinkedIn — generación de posts

- **Qué es** (`Desktop/Proyectos/LINKEDIN-POSTS/app.py`): Flask (puerto 5000). Con Gemini +
  Google Search busca noticias tech/IA y **genera el borrador** de un post con el estilo de
  Gonzalo. Endpoints `/api/news` y `/api/generate`. **No publica** en LinkedIn.
- **Plan**:
  - Importar/llamar `fetch_news()` y `generate_post()` como tools.
  - Tools: `buscar_noticias_tech()` (**LOW**), `generar_post_linkedin(tema)` (**MEDIUM** — produce texto).
  - Migrar el modelo de Gemini → Ollama local para mantenerlo gratis (opcional).
- **Decisión pendiente**: ¿FRIDAY solo **genera el borrador**, o también **publica** de verdad?
  Publicar requiere LinkedIn API + OAuth y sería **HIGH**. (Ver [Preguntas abiertas](#preguntas-abiertas).)

### 3. SIRADIG — carga de tickets fiscales

- **Qué es** (`Desktop/Proyectos/SIRADIG-COMPLETION/pipeline.py`): CLI. Flujo
  **Google Drive** (fotos de tickets) → **Gemini Vision** (extrae datos fiscales) → validación →
  **Google Sheets**. Modos: `--file`, `--dry-run`, `--stats`, completo. Auth vía
  `credentials.json` / `token.json` (Google APIs).
- **Plan**:
  - Tools: `siradig_pendientes()` (dry-run, **LOW**), `siradig_stats()` (**LOW**),
    `siradig_procesar()` (corre el pipeline completo → escribe en Sheets, **HIGH** porque es
    un trámite fiscal oficial e irreversible en la planilla).
  - Integración por `subprocess` al CLI o importando sus funciones (`src/`).

### 4. Gastos personales — ✅ HECHO

- **Dónde vive**: Google Sheet `Gastos_Personales` (ID en `settings.gastos_spreadsheet_id`).
  Tabs: Config · Reparto Fijos · **GASTOS GON** · GASTOS CHINA · Cómo usar. Los gastos de
  Gonzalo van en **GASTOS GON**: tabla MOVIMIENTOS con header en fila 33 (Fecha·Tipo·Categoría·
  Detalle·Monto·Medio de pago), datos desde la 34, buffer vacío desde la ~69.
- **Auth**: **Service Account** dedicado (NO SIRADIG, NO OAuth). JSON en
  `.google-service-account.json` (gitignored); la planilla se comparte con su `client_email`
  como Editor. Vars `.env`: `GOOGLE_SHEETS_CREDENTIALS`, `GASTOS_SPREADSHEET_ID`.
- **Tools** (`friday/integrations/gastos.py`, vía `gspread`): `ver_gastos()` y
  `cargar_gasto(monto, categoria, detalle, medio_pago, tipo)`. `cargar_gasto` busca la primera
  fila vacía tras el header (no append — hay tablas debajo) y escribe el monto como número
  (`USER_ENTERED`) para no romper las fórmulas. Categorías/medios son lista cerrada (`_match`
  normaliza acentos + sinónimos).
- **Riesgo**: hoy **LOW** (frictionless por voz; reversible borrando la fila). Subir a
  **MEDIUM** cuando exista la confirmación por voz (Fase 0 / Gap #1).

### 5. Navegación web + Spotify — ✅ HECHO

- **Web** (`friday/agent/actions/pc_actions.py`): `abrir_url(url)` y `buscar_en_google(consulta)`.
  Usan PowerShell `Start-Process` (no `cmd.exe start`) porque cmd parte la URL en el `&` de
  los query params. Esquemas permitidos: `http/https/spotify`. Ambas **LOW**.
- **Spotify** (`friday/integrations/spotify.py`): Web API como control remoto del **dispositivo
  activo** (la app de escritorio). `reproducir_spotify(consulta, tipo)` (con fallback de tipo),
  `pausar_spotify()`, `siguiente_cancion()`, `ajustar_volumen(0-100)`. Todas **LOW**. Requiere
  **Premium** (control de reproducción) + OAuth.
  - **Auth one-time**: `friday-spotify-auth` (o `python -m friday.integrations.spotify_auth`).
    Guarda el `refresh_token` en `.spotify_token.json` (gitignored). Vars en `.env`:
    `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback`.

### 6. Research web — ✅ HECHO

> A diferencia de `buscar_en_google` (abre el navegador para Gonzalo), estas traen el TEXTO
> al modelo para discutir/comparar/recomendar sobre data real. Arregla la alucinación de
> "inventar noticias" dándole la capacidad de verdad.

- `friday/integrations/web_research.py`: `buscar_web(consulta)` (DuckDuckGo vía `ddgs`, sin
  API key) + `leer_pagina(url)` (extrae contenido principal con `trafilatura`, trunca a 6k).
  Ambas **LOW**. Guard anti-SSRF: solo http/https, bloquea IPs privadas/loopback (incluso
  tras redirect) para no sondear servicios internos.

### 7. Memoria / aprendizaje (Fase A) — ✅ HECHO

> "Aprender" NO es reentrenar el modelo: el conocimiento vive en SQLite, inyectado al prompt
> cada turno. Inspeccionable y borrable.

- Tabla `memories` (schema v4), `friday/storage/memory_repo.py` (`remember` con upsert por key,
  `forget` por substring), `friday/core/memory_tools.py` (tools `recordar`/`olvidar`).
- Inyección al contexto en `OllamaBrain._memory_block()`.
- **Pendiente (Fase F)**: auto-captura de preferencias + detección de hábitos (lo proactivo).

### 8. Transparencia: feed de actividad de tools en vivo — ✅ HECHO

> Gonzalo VE qué hace FRIDAY mientras lo hace. Y delata alucinaciones: si dice "listo" pero
> no aparece un evento de tool, queda en evidencia.

- `friday/core/activity.py`: ring buffer en proceso (thread-safe), singleton `activity_log`.
  Ambos cerebros (`FridayBrain`/`OllamaBrain`) registran `running → ok/error` en `_execute_tool`.
- `GET /api/agent/activity?n=30` lo expone; el dashboard lo renderiza con fetch cada 1s
  (`tool_activity_html`), mismo patrón que el log de voz (sin rerun de Streamlit).

### 9. Mic visualizer en vivo (estilo Wispr) — ✅ HECHO

- `live_mic_visualizer_html` (`friday/dashboard/components.py`): barras que reaccionan a la voz
  REAL vía Web Audio (`getUserMedia` + `AnalyserNode`) del navegador (localhost = contexto
  seguro). Fallback a animación idle si se niega el mic. Estado real (WAITING/LISTENING/
  CONVERSING) leído de `/api/voice/log`. La zona "Live Voice" del dashboard junta mic +
  Voice Activity + Tool Activity.

### 10. Research — capa de inteligencia (digest diario) — ✅ HECHO

> El salto de "telemetría" a "conocimiento". Los collectors traen métricas (SQLite);
> esto trae INTEL externa fresca como documentos markdown. Es la pieza que el video
> del "agentic OS" llama *second brain auto-alimentado*.

- **Store** (`friday/storage/knowledge_store.py`): `KnowledgeStore`, archivos `.md` en
  `knowledge/<categoria>/<YYYY-MM-DD>.md`. Documentos (no métricas): curables a mano,
  portables, versionables, leídos nativo por el LLM. Portátil a Obsidian sin migrar.
- **Servicio** (`friday/core/research.py`): `ResearchService` — agendado (NO un collector,
  mismo molde que `BriefingService`). Junta novedades por tema vía `buscar_web_items` y
  escribe un digest markdown **determinista** (titulares + links reales + snippets).
  Regla de oro: el LLM NO está en el camino crítico → nunca se cae ni alucina.
- **Síntesis on-demand**: tool `consultar_research()` (**LOW**) deja que el cerebro lea el
  digest y lo resuma hablado cuando Gonzalo pregunta "¿qué hay nuevo?".
- **Cron**: diario a las `research_hour:research_minute` (08:00, antes del briefing 08:30).
  Temas en `settings.research_topics` (IA/tech + backend innovador, editables).
- **HUD**: tab **RESEARCH** en el Command Center (renderiza el markdown + botón REFRESH).
- **API** (`routes_research.py`): `GET /api/research/latest`, `/list`, `POST /refresh`.
- **Pendiente (próximo incremento)**: síntesis con LLM al juntar (necesita un
  `compose_document()` en el `Brain` Protocol, sin el corsé de voz de `compose()`); y
  **estado de proyectos** (Jira/Notion) como collectors → SQLite → tab, junto a NEXCOURT/AXIS.

## Fases (incremental — cada una es usable sola)

- **Fase 0 — Generalizar el agente**: que `ActionRegistry`/`PermissionGate` soporte acciones
  más allá de la PC; crear `friday/integrations/`; **cerrar el loop de confirmación por voz**.
- **Fase 1 — Observabilidad** ✅: NEXCOURT (AWS/CloudWatch) + AXIS (SSH/Docker), ambos collectors
  read-only, tools de lectura y paneles en el dashboard. *Máximo valor, mínimo riesgo (todo LOW).*
- **Fase 2 — Gastos**: ver + cargar (una vez aclarado dónde vive la planilla).
- **Fase 3 — LinkedIn**: noticias + borrador (y publicación si se decide).
- **Fase 4 — SIRADIG**: el más delicado (escribe trámite oficial), al final y con confirmación HIGH.

## Mejora continua (principios)

- Cada integración entra **detrás del gate** con su riesgo bien calibrado.
- **Secretos** fuera del código: `.env` (ya gitignoreado) o un vault. Nunca commitear tokens.
- **AWS read-only** para observación; credenciales separadas y de mínimo privilegio para
  cualquier acción de escritura.
- Preferir **modelos locales** (Ollama) sobre APIs pagas; si una tool usa Gemini, evaluar migrarla.
- Mantener esta documentación viva: al agregar/cambiar una integración, actualizar este archivo
  y [ARCHITECTURE.md](ARCHITECTURE.md).

## Preguntas abiertas

1. **Gastos personales**: ¿dónde vive la planilla y cómo se accede? (No hay script en `Proyectos/`.)
2. **LinkedIn**: ¿solo generar el borrador, o también publicar automáticamente (LinkedIn API)?
3. **AWS**: ¿OK con crear un IAM read-only dedicado para FRIDAY en vez del perfil root actual?
4. **Confirmación por voz**: ¿alcanza con sí/no, o querés una palabra de confirmación específica
   (ej. "autorizo") para acciones HIGH?
