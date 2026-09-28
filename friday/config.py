"""Configuración centralizada de FRIDAY — lee variables de .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM provider ---
    # "gemini" (nube, requiere GEMINI_API_KEY) o "ollama" (local, sin costo).
    # Default gemini: 2.5-flash es mejor que qwen2.5:7b en function-calling
    # (apertura de apps, análisis) y barato; el tope mensual de la API key
    # protege el gasto. Flip a "ollama" para volver a local/offline.
    llm_provider: str = "gemini"

    # --- Ollama (cerebro local) ---
    # 127.0.0.1 (no "localhost") para forzar IPv4: con localhost, httpx intenta
    # IPv6 (::1) primero, donde Ollama no escucha, y suma ~21s de timeout.
    ollama_host: str = "http://127.0.0.1:11434"
    # Gemma 4 E4B QAT (6.1GB): tools nativas, 128K ctx, entra holgado en 16GB junto
    # con Whisper + TTS. Si te sobra RAM: "gemma4:12b-it-qat" (7.2GB, razona mejor).
    # Ver docs/MODELS.md para la matriz completa.
    ollama_model: str = "gemma4:e4b-it-qat"
    ollama_timeout_seconds: float = 120.0
    # Ventana de contexto EXPLÍCITA. Sin esto Ollama usa su default (2-4K) y, con
    # ~2.6K tokens fijos (system + 27 tools) + memoria + historial, RECORTA EL
    # PRINCIPIO del prompt — o sea el system prompt — sin avisar.
    ollama_num_ctx: int = 8192
    # Gemma 4 (y otros "thinking models") PIENSAN por defecto y el razonamiento se
    # come num_predict → content vacío ("(sin respuesta)"). Medido en el M4:
    # think=on → 12.8s y vacío; think=false → 0.4s y correcto. Para voz: False.
    # None = no mandar el parámetro (modelos sin soporte de thinking).
    ollama_think: bool | None = False

    # --- Gemini ---
    gemini_api_key: str = ""
    # 2026-09: la familia 2.5 quedó "access limited" y 2.0 fue apagada (404). Los
    # 3.x SIEMPRE piensan (no hay thinking off) y el thinking cuenta dentro de
    # max_output_tokens → ver gemini_thinking_levels y gemini_max_output_tokens.
    # Matriz completa y precios en docs/MODELS.md.
    #
    # fast: turnos de voz con tools (~80% del tráfico). 3.5-flash-lite cuesta LO
    # MISMO que el viejo 2.5-flash ($0.30/$2.50 por 1M) → respeta el tope mensual.
    # Modo calidad: "gemini-3.6-flash" (thinking "minimal", 2.5x el precio).
    gemini_model_fast: str = "gemini-3.5-flash-lite"
    # balanced: consultas largas/complejas del clasificador AUTO. NUNCA mandamos
    # auto a pro (sin free tier + caro); pro solo bajo pedido explícito.
    # $0.75/$3.75 por 1M (promo hasta 2026-12-31; después se duplica).
    gemini_model_balanced: str = "gemini-3.8-flash"
    # lite: redacción one-shot sin tools (briefings, compose). El más barato con
    # buena calidad: $0.30/$2.50 por 1M.
    gemini_model_lite: str = "gemini-3.5-flash-lite"
    # reasoning: SOLO pedido explícito (chat model="pro"). Preview y SIN free tier.
    gemini_model_reasoning: str = "gemini-3.1-pro-preview"
    # thinking_level por modelo (3.x). Lo no listado usa el default del modelo.
    gemini_thinking_levels: dict = Field(default_factory=lambda: {
        "gemini-3.6-flash": "minimal",
        "gemini-3.8-flash": "low",
        "gemini-3.5-flash-lite": "low",
    })
    # Techo de salida (thinking + respuesta). 200 alcanzaba con 2.5 + budget=0, pero
    # en 3.x el pensar se come el techo y la respuesta sale vacía. La brevedad para
    # voz la impone el system prompt ("two sentences"), no este número.
    gemini_max_output_tokens: int = 1024

    # Pricing por MODELO (USD per 1K tokens). El tracker acumula tokens por modelo
    # y el collector aplica el precio de cada uno → costo real cuando convive flash
    # con pro. Esta tabla NO se sobreescribe desde .env (haría falta un JSON), así
    # que el costo queda correcto aunque el .env tenga viejos escalares.
    # Precios verificados en ai.google.dev/gemini-api/docs/pricing (2026-09). Los
    # 3.6/3.7/3.8-flash tienen precio promo hasta 2026-12-31 (después se duplica).
    gemini_pricing: dict = Field(default_factory=lambda: {
        "gemini-3.8-flash":       {"in": 0.00075, "out": 0.00375},  # $0.75 / $3.75
        "gemini-3.7-flash":       {"in": 0.00075, "out": 0.00375},
        "gemini-3.6-flash":       {"in": 0.00075, "out": 0.00375},
        "gemini-3.5-flash":       {"in": 0.0015,  "out": 0.009},    # $1.50 / $9
        "gemini-3.5-flash-lite":  {"in": 0.0003,  "out": 0.0025},   # $0.30 / $2.50
        "gemini-3.1-flash-lite":  {"in": 0.00025, "out": 0.0015},   # $0.25 / $1.50
        "gemini-3.1-pro-preview": {"in": 0.002,   "out": 0.012},    # $2 / $12 (≤200K)
        # Legacy (sesiones viejas en la DB): mantener para que el costo histórico cuadre.
        "gemini-2.0-flash": {"in": 0.0001,  "out": 0.0004},
        "gemini-2.5-flash": {"in": 0.0003,  "out": 0.0025},
        "gemini-2.5-pro":   {"in": 0.00125, "out": 0.01},
    })

    # Fallback escalar para modelos fuera de la tabla (modelo desconocido). OJO: si
    # tu .env define estos valores, solo afectan al fallback, no a los modelos de
    # la tabla de arriba.
    gemini_cost_per_1k_input_tokens: float = 0.0001
    gemini_cost_per_1k_output_tokens: float = 0.0004

    # --- NEXCOURT ---
    # Modo de acceso:
    #   "off"        → desactivado (default, no hace polling cada 30s)
    #   "direct"     → management ports 9081-9087 (docker-compose local)
    #   "kong"       → via gateway (/health/{service})
    #   "cloudwatch" → AWS ECS + CloudWatch (producción, read-only). Ver collectors/cloudwatch.py
    nexcourt_mode: str = "off"

    # Modo "direct": URL base para health (ej. http://localhost)
    nexcourt_direct_host: str = "http://localhost"

    # Modo "kong": URL base del gateway (ej. https://dev-api.nexcourts.com)
    nexcourt_kong_url: str = "https://dev-api.nexcourts.com"

    # Servicios a monitorear con sus puertos de gestión (908x) y paths Kong
    # Formato: {"docker_name": {"mgmt_port": 9081, "kong_path": "clubs"}}
    nexcourt_services_config: dict = Field(default_factory=lambda: {
        "clubs-service":          {"mgmt_port": 9081, "kong_path": "clubs"},
        "reservations-service":   {"mgmt_port": 9082, "kong_path": "reservations"},
        "stock-service":          {"mgmt_port": 9083, "kong_path": "stock"},
        "reports-service":        {"mgmt_port": 9084, "kong_path": "reports"},
        "sports-service":         {"mgmt_port": 9085, "kong_path": "sports"},
        "media-service":          {"mgmt_port": 9086, "kong_path": "media"},
        "notifications-service":  {"mgmt_port": 9087, "kong_path": "notifications"},
    })

    # Legacy: alias plano de nombres de servicio (solo los activos)
    nexcourt_services: list[str] = Field(default_factory=list)
    nexcourt_api_key: str = ""
    nexcourt_poll_interval_seconds: int = 30

    # --- NEXCOURT en AWS (modo "cloudwatch") ---
    # Credenciales: cadena estándar de boto3 (env AWS_*, ~/.aws/credentials, perfil).
    # ⚠️ Crear un IAM read-only dedicado para FRIDAY — NO usar root.
    aws_region: str = "us-east-1"
    nexcourt_ecs_cluster: str = "nexcourt-dev-cluster"
    nexcourt_cloudwatch_poll_interval_seconds: int = 60
    # Re-login AWS: comando que abre el flujo de auth (SSO) en el navegador. El
    # error de botocore pide 'aws login'; ajustá si tu setup usa otro (ej.
    # 'aws sso login --profile nexcourt'). Lo dispara el botón del dashboard.
    nexcourt_aws_login_cmd: str = "aws login"
    # Cuando el token vence, el collector deja de martillar AWS (no más tracebacks
    # cada 60s) y reintenta cada este tanto (auto-heal) hasta que vuelva el token.
    nexcourt_auth_cooldown_seconds: int = 300

    # Mapa servicio lógico → nombre del service en ECS + log group de CloudWatch.
    # kong/keycloak incluidos: son infra crítica (gateway + auth).
    nexcourt_aws_services: dict = Field(default_factory=lambda: {
        svc: {"ecs": f"nexcourt-dev-{ecs}", "log_group": f"/nexcourt-dev/{lg}"}
        for svc, ecs, lg in [
            ("clubs-service",         "clubs-service",         "clubs"),
            ("reservations-service",  "reservations-service",  "reservations"),
            ("stock-service",         "stock-service",         "stock"),
            ("reports-service",       "reports-service",       "reports"),
            ("sports-service",        "sports-service",        "sports"),
            ("media-service",         "media-service",         "media"),
            ("notifications-service", "notifications-service", "notifications"),
            ("kong",                  "kong",                  "kong"),
            ("keycloak",              "keycloak",              "keycloak"),
        ]
    })

    # --- AXIS (droplet DigitalOcean, containers Docker vía SSH) ---
    # AXIS no expone Actuator: se observa por SSH + docker. Read-only.
    axis_enabled: bool = False
    axis_ssh_host: str = "axis"  # alias en ~/.ssh/config (HostName 174.138.52.161)
    axis_ssh_timeout_seconds: int = 12
    axis_poll_interval_seconds: int = 60
    # Containers a monitorear (explícito: ignora restos como contenedores sueltos).
    axis_containers: list[str] = Field(default_factory=lambda: [
        "axis-backend", "axis-frontend", "axis-front",
        "axis-nginx", "axis-keycloak", "axis-postgres", "axis-logs",
    ])

    # --- Spotify (Web API: búsqueda + control de reproducción) ---
    # El Web API es un control remoto sobre el dispositivo ACTIVO (la app de
    # escritorio abierta). Controlar la reproducción requiere cuenta Premium.
    # Auth OAuth: correr `friday-spotify-auth` UNA vez → guarda el refresh_token
    # en spotify_token_path. De ahí en más se refresca el access_token solo.
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8888/callback"
    spotify_token_path: str = str(_PROJECT_ROOT / ".spotify_token.json")

    # --- Gastos (Google Sheets vía Service Account) ---
    # Service account (cuenta robot): headless, sin OAuth ni tokens que expiran.
    # La planilla se comparte con el client_email del JSON (permiso Editor).
    google_sheets_credentials: str = ""  # path al JSON del service account
    gastos_spreadsheet_id: str = "1G_xjwkF9mJ7V4-9t9UwRE_xOiuUFPT78j9ANHbEPqP8"

    # --- Contexto del cerebro (control de tokens, Fase 1) ---
    # Ventana de historial: cuántos TURNOS de usuario recientes mantener en el
    # contexto que se manda al LLM. El brain es un singleton reusado durante toda
    # la vida del proceso, así que sin techo el input crece sin parar. 0 = sin
    # límite (todo el historial). Recortamos en bordes de turno (mensaje de
    # usuario con texto) para no orfanar function_responses.
    chat_history_window: int = 12
    # Memorias de Gonzalo inyectadas al system prompt cada turno. Acotado para no
    # inflar el prompt; ranking por relevancia (top-K real) queda para Fase 2.
    memory_context_limit: int = 30
    # Resultados de tools de TURNOS ANTERIORES que siguen en el historial se recortan
    # a este largo (chars). Sin esto, un leer_pagina (6K chars) o metricas_servicio
    # (~15K chars) se reenvía en CADA llamada durante los próximos 12 turnos. El
    # turno en curso siempre ve el resultado completo. 0 = no recortar.
    tool_result_history_chars: int = 600

    # --- Storage ---
    db_path: str = str(_PROJECT_ROOT / "friday.db")
    # Capa de CONOCIMIENTO: carpeta de archivos .md (research, intel). A diferencia
    # de la DB (métricas), son documentos: curables a mano y portables (Obsidian, git).
    knowledge_dir: str = str(_PROJECT_ROOT / "knowledge")

    # --- Research (capa de inteligencia: digest diario de novedades) ---
    # Un servicio agendado junta novedades por tema y escribe un digest markdown
    # determinista (titulares + links reales). El cerebro lo lee on-demand vía
    # `consultar_research`. enabled=False lo apaga sin tocar código. Corre antes del
    # briefing matutino (08:30) para que el resumen del día ya lo tenga listo.
    research_enabled: bool = True
    research_hour: int = 8
    research_minute: int = 0
    research_max_results_per_topic: int = 5
    # Temas a seguir. Editá la lista a gusto — es TU feed. (Como las rutinas y los
    # servicios NEXCOURT, vive en código; no se sobreescribe desde .env.)
    research_topics: list[dict] = Field(default_factory=lambda: [
        {"name": "IA & Tech", "query": "latest AI artificial intelligence breakthroughs this week"},
        {"name": "LLMs & Agentes", "query": "new LLM models AI agent frameworks release news"},
        {"name": "Backend innovador", "query": "innovative backend development techniques distributed systems 2026"},
        {"name": "Arquitectura & Tooling", "query": "new backend architecture patterns developer tools release"},
    ])

    # --- API ---
    # 127.0.0.1 por defecto: el agente abre apps y LEE ARCHIVOS sin confirmación
    # (RiskLevel.LOW) y la API no tiene auth. En 0.0.0.0, cualquiera en tu Wi-Fi
    # podría pedir leer_archivo(~/.ssh/...). Solo abrilo si sabés lo que hacés.
    api_host: str = "127.0.0.1"
    # Puerto del API + HUD. `friday --api-port` lo pisa; start.sh usa API_PORT.
    api_port: int = 8000

    # --- Voz (listener) ---
    # Carpeta con modelos de voz (Vosk, Piper, jarvis.wav) y el log del listener.
    # Vacío = default por plataforma (ver friday/voice/wake.py: _default_voices_dir).
    voices_dir: str = ""
    # Voz del catálogo de Pocket TTS (sin login) si no hay voices/jarvis.wav para
    # clonar. Escuchá las opciones en voices/samples/*.wav. Env: TTS_VOICE.
    tts_voice: str = "michael"

    # --- System collector ---
    system_poll_interval_seconds: int = 10

    # --- Proactividad (Pilar 1: canal proactivo voz + toasts) ---
    # Política de severidad = "derecho a callarse". Niveles: info < warning <
    # critical. La voz INTERRUMPE, así que se reserva a lo grave; el toast es
    # visual y silencioso. Un nivel se emite por un canal si es >= al mínimo.
    proactive_speak_min_level: str = "critical"
    proactive_toast_min_level: str = "warning"

    # --- Rituales agendados (Pilar 2: briefings proactivos) ---
    # Briefing matutino (estado del sistema, servicios, costo del día) y cierre
    # del día, redactados por el LLM con la persona de FRIDAY y dichos por voz.
    # Cron diario; hora local del proceso. enabled=False los apaga sin tocar código.
    briefing_enabled: bool = True
    briefing_morning_hour: int = 8
    briefing_morning_minute: int = 30
    briefing_evening_hour: int = 22
    briefing_evening_minute: int = 0

    # --- Analista de tendencias (Pilar 3: monitor → analista) ---
    # A diferencia del notifier (umbrales fijos en el instante), el analista mira
    # TENDENCIAS: compara la media de una ventana reciente contra un baseline y
    # avisa si hay una subida sostenida, aunque ningún umbral instantáneo se cruce.
    # Detección 100% estadística (determinista); el LLM NO decide anomalías.
    analyst_enabled: bool = True
    analyst_interval_minutes: int = 30
    analyst_recent_window_minutes: int = 60
    analyst_baseline_window_hours: int = 6
    # Subida mínima (fracción) de la media reciente sobre el baseline para avisar.
    analyst_min_rise_pct: float = 0.25
    # Puntos mínimos en cada ventana para que la comparación sea significativa
    # (evita falsos positivos cuando FRIDAY recién arrancó y hay pocos datos).
    analyst_min_points: int = 5

    # --- Notification thresholds ---
    notifier_cpu_warn: float = 70.0
    notifier_cpu_crit: float = 90.0
    notifier_ram_warn: float = 80.0
    notifier_ram_crit: float = 95.0
    notifier_disk_warn: float = 85.0
    notifier_disk_crit: float = 95.0
    # Anti-flapping: un valor que oscila alrededor del umbral (RAM 79.8 ↔ 80.3)
    # generaba "superó" / "normalizado" cada pocos minutos. Se da por normalizado
    # recién al bajar `hysteresis` puntos del umbral, y la misma alerta no se repite
    # antes de `realert_minutes` desde su normalización.
    notifier_hysteresis: float = 5.0
    notifier_realert_minutes: int = 30
    # Con billing + tope mensual de $4 en la API key, avisar a $0.50/día era ruido.
    # Subimos: un día cerca del tope mensual SÍ vale un aviso; el resto, silencio.
    notifier_gemini_cost_daily_warn: float = 2.00
    notifier_gemini_cost_daily_crit: float = 3.50

    # --- Control IR (luces LED por estado + otros dispositivos infrarrojos) ---
    # FRIDAY emite códigos IR por un emisor de red para dar feedback visual: color
    # según el estado de voz (escuchando/respondiendo/idle). El remoto solo manda
    # comandos DISCRETOS, así que cada estado es un color/preset fijo, no un fade.
    ir_enabled: bool = True
    # "mock" (default, sin hardware: testeable) | "broadlink" (RM4 Mini por LAN).
    ir_backend: str = "mock"
    # IP del Broadlink RM4 en la red local (requerida con ir_backend=broadlink).
    ir_broadlink_host: str = ""
    # JSON con los códigos IR aprendidos (gitignored: es de tu casa).
    ir_codes_path: str = ".ir_codes.json"
    # Nombre del dispositivo-tira en el registro de códigos (devices.py).
    lights_device: str = "leds"


settings = Settings()
