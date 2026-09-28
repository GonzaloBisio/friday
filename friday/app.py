"""FRIDAY — Bootstrap unificado del sistema completo.

Por defecto levanta todo junto: API (FastAPI) + Dashboard (Streamlit) + Scheduler.
Modos alternativos:
  python -m friday.app --cli         → Solo CLI interactivo
  python -m friday.app --no-dashboard → API + Scheduler, sin dashboard
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import threading
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from friday.agent.permissions import PermissionGate
from friday.agent.setup import build_action_registry, register_agent_tools
from friday.api.main import AppState, create_app
from friday.api.ws import WebSocketBroadcast
from friday.collectors.axis import AxisCollector
from friday.collectors.cloudwatch import CloudWatchCollector
from friday.collectors.gemini_usage import GeminiUsageCollector
from friday.collectors.nexcourt import NexcourtCollector
from friday.collectors.system import SystemCollector
from friday.config import settings
from friday.core.analyst import TrendAnalyzer
from friday.core.brain_factory import build_brain
from friday.core.briefing import BriefingService
from friday.core.health import register_health_tools
from friday.core.hud import hud_bridge, register_hud_tools
from friday.core.activity import activity_log
from friday.core.memory_tools import register_memory_tools
from friday.core.notifier import Notifier
from friday.core.proactive import ProactiveDispatcher
from friday.core.research import ResearchService, ResearchTopic, register_research_tools
from friday.core.routines import RoutineEngine, register_routine_tools
from friday.core.tools_registry import build_registry
from friday.storage.chat_repo import ChatRepository
from friday.storage.db import get_connection
from friday.storage.knowledge_store import KnowledgeStore
from friday.storage.memory_repo import MemoryRepository
from friday.storage.metrics_repo import MetricsRepository
from friday.storage.notification_repo import NotificationRepository

# Log a consola Y a archivo (friday.log) para poder debuggear lo que pasa
# cuando FRIDAY se lanza en background desde el listener (stdout se pierde).
# Tail:  tail -f friday.log   (en la raíz del repo)
_LOG_FILE = Path(__file__).resolve().parent.parent / "friday.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

_RETENTION_DAYS = 30


class FridaySystem:
    """Orquesta todos los subsistemas de FRIDAY."""

    def __init__(self) -> None:
        logger.info("Inicializando FRIDAY — DB: %s", settings.db_path)

        self.conn = get_connection(settings.db_path, check_same_thread=False)
        # Lock compartido por todos los repos que usan esta conexión: serializa
        # el acceso desde los threads de APScheduler. check_same_thread=False
        # permite usar la conn desde otros threads, pero NO la hace safe para
        # uso concurrente — dos executemany+commit solapados revientan con
        # InterfaceError. Un solo lock para los tres repos asegura que tampoco
        # se pisen entre ellos.
        self._db_lock = threading.RLock()
        self.repo = MetricsRepository(self.conn, lock=self._db_lock)
        self.chat_repo = ChatRepository(self.conn, lock=self._db_lock)
        self.notif_repo = NotificationRepository(self.conn, lock=self._db_lock)
        self.memory_repo = MemoryRepository(self.conn, lock=self._db_lock)

        self.tools_registry = build_registry(self.repo)

        action_registry = build_action_registry()
        self.gate = PermissionGate(action_registry)
        register_agent_tools(self.tools_registry, self.gate)
        # Memoria (Fase A): tools recordar/olvidar. La inyección al prompt va por el brain.
        register_memory_tools(self.tools_registry, self.memory_repo)
        # Pilar 5: rutinas compuestas (modo focus, etc.). Reusan el gate, así que
        # cada paso respeta el riesgo de su acción. Invocables por voz vía el LLM.
        self.routines = RoutineEngine(self.gate)
        register_routine_tools(self.tools_registry, self.routines)
        # Pilar 6: tool de autoobservabilidad — FRIDAY reporta su propia salud.
        register_health_tools(self.tools_registry)
        # Capa de conocimiento: research diario en archivos .md (KnowledgeStore) +
        # servicio agendado que junta novedades por tema. La tool consultar_research
        # deja que el cerebro lo lea y sintetice on-demand.
        self.knowledge = KnowledgeStore(settings.knowledge_dir)
        topics = [ResearchTopic(**t) for t in settings.research_topics]
        self.research = ResearchService(self.knowledge, topics)
        register_research_tools(self.tools_registry, self.knowledge)

        # WebSocket broadcast (compartido entre collectors, notifier y API)
        self.broadcast = WebSocketBroadcast()
        # HUD en vivo: cada evento de tool va al feed (sin polling) y las tools con
        # panel abren la tarjeta de foco (modo EDITH). Ver friday/core/hud.py.
        hud_bridge.broadcast = self.broadcast
        activity_log.subscribe(lambda ev: self.broadcast.emit({"type": "tool", **ev}))
        register_hud_tools(self.tools_registry)

        self.notifier = Notifier(
            repo=self.repo,
            notif_repo=self.notif_repo,
            broadcast=self.broadcast,
        )
        # Pilar 1: convierte las notificaciones en eventos proactivos (voz/toast)
        # según la política de severidad, y los empuja al cliente de voz por WS.
        self.proactive = ProactiveDispatcher(broadcast=self.broadcast)
        # Pilar 3: analista de tendencias. Reusa el dispatcher (misma cañería) y
        # persiste sus insights en el mismo repo de notificaciones del dashboard.
        self.analyst = TrendAnalyzer(
            repo=self.repo, dispatcher=self.proactive, notif_repo=self.notif_repo,
        )

        # Elige Ollama (local) o Gemini según settings.llm_provider.
        self.brain = build_brain(
            registry=self.tools_registry,
            chat_repo=self.chat_repo,
            session_id=self.chat_repo.create_session(),
            memory_repo=self.memory_repo,
        )

        # Pilar 2: rituales agendados. Usa compose() one-shot del brain (no toca
        # el historial de chat) y emite por el mismo canal proactivo del Pilar 1.
        self.briefing = BriefingService(
            repo=self.repo, brain=self.brain, broadcast=self.broadcast,
        )

        self.scheduler = BackgroundScheduler()
        self._register_collectors()
        self._register_maintenance()
        self._register_notifier()
        self._register_briefings()
        self._register_analyst()
        self._register_research()

        self._api_thread: threading.Thread | None = None
        self._api_port: int = 8000

    def _register_collectors(self) -> None:
        collectors = [
            SystemCollector(),
            GeminiUsageCollector(),
        ]

        # NEXCOURT: en AWS (cloudwatch) o en hosts locales (direct/kong).
        # Guardamos la referencia para que la API pueda chequear/resetear el auth
        # (botón de re-login cuando el token AWS vence).
        # Modo "off" (default): no registrar collector para evitar polling cada 30s.
        self.nexcourt_collector = None
        if settings.nexcourt_mode == "cloudwatch":
            self.nexcourt_collector = CloudWatchCollector()
            collectors.append(self.nexcourt_collector)
            logger.info("NEXCOURT collector: CloudWatch")
        elif settings.nexcourt_mode in ("direct", "kong"):
            if settings.nexcourt_services or settings.nexcourt_services_config:
                self.nexcourt_collector = NexcourtCollector()
                collectors.append(self.nexcourt_collector)
                logger.info("NEXCOURT collector: %s", settings.nexcourt_mode)
        elif settings.nexcourt_mode == "off":
            logger.info("NEXCOURT desactivado (nexcourt_mode='off')")

        # AXIS: containers Docker en el droplet, vía SSH.
        if settings.axis_enabled:
            collectors.append(AxisCollector())

        from datetime import datetime
        for c in collectors:
            self.scheduler.add_job(
                self._make_job(c),
                trigger="interval",
                seconds=c.interval_seconds,
                id=f"collector_{c.source}",
                max_instances=1,
                # Primer poll INMEDIATO: sin esto el dashboard muestra todo
                # "offline" hasta el primer intervalo (hasta 60s).
                next_run_time=datetime.now(),
            )
            logger.info("Collector[%s] cada %ds", c.source, c.interval_seconds)

    def _register_maintenance(self) -> None:
        self.scheduler.add_job(
            self._purge_old_metrics,
            trigger="interval",
            hours=6,
            id="maintenance_purge",
            max_instances=1,
        )

    def _register_notifier(self) -> None:
        self.scheduler.add_job(
            self._run_notifier_and_dispatch,
            trigger="interval",
            seconds=60,
            id="notifier_check",
            max_instances=1,
        )
        logger.info("Notifier chequea cada 60s")

    def _run_notifier_and_dispatch(self) -> None:
        """Corre los chequeos y empuja los que califiquen al canal proactivo."""
        notifs = self.notifier.run()
        if notifs:
            self.proactive.dispatch(notifs)

    def _register_analyst(self) -> None:
        """Analista de tendencias (Pilar 3): corre cada N minutos."""
        if not settings.analyst_enabled:
            logger.info("Analista desactivado (analyst_enabled=False)")
            return
        self.scheduler.add_job(
            self.analyst.run,
            trigger="interval",
            minutes=settings.analyst_interval_minutes,
            id="analyst_trends",
            max_instances=1,
        )
        logger.info("Analista de tendencias cada %d min", settings.analyst_interval_minutes)

    def _register_research(self) -> None:
        """Research diario (capa de inteligencia): junta novedades y escribe el digest."""
        if not settings.research_enabled:
            logger.info("Research desactivado (research_enabled=False)")
            return
        self.scheduler.add_job(
            self.research.run,
            trigger="cron",
            hour=settings.research_hour,
            minute=settings.research_minute,
            id="research_digest",
            max_instances=1,
        )
        logger.info(
            "Research: digest diario %02d:%02d (%d temas)",
            settings.research_hour, settings.research_minute, len(settings.research_topics),
        )

    def _register_briefings(self) -> None:
        """Rituales diarios (Pilar 2): briefing matutino y cierre del día."""
        if not settings.briefing_enabled:
            logger.info("Briefings desactivados (briefing_enabled=False)")
            return
        self.scheduler.add_job(
            lambda: self.briefing.run("morning"),
            trigger="cron",
            hour=settings.briefing_morning_hour,
            minute=settings.briefing_morning_minute,
            id="briefing_morning",
            max_instances=1,
        )
        self.scheduler.add_job(
            lambda: self.briefing.run("evening"),
            trigger="cron",
            hour=settings.briefing_evening_hour,
            minute=settings.briefing_evening_minute,
            id="briefing_evening",
            max_instances=1,
        )
        logger.info(
            "Briefings: matutino %02d:%02d, cierre %02d:%02d",
            settings.briefing_morning_hour, settings.briefing_morning_minute,
            settings.briefing_evening_hour, settings.briefing_evening_minute,
        )

    def _make_job(self, collector):
        broadcast = self.broadcast

        def job():
            points = collector.run()
            if points:
                self.repo.save_many(points)
                # Emitir métricas nuevas por WebSocket en un thread aparte
                _schedule_broadcast(broadcast, points)
        return job

    def _purge_old_metrics(self) -> None:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
        with self._db_lock:
            cur = self.conn.execute(
                "DELETE FROM metrics WHERE ts < ?", (cutoff.isoformat(),)
            )
            self.conn.commit()
        if cur.rowcount > 0:
            logger.info("Purgados %d puntos anteriores a %d días", cur.rowcount, _RETENTION_DAYS)

    def start_scheduler(self) -> None:
        self.scheduler.start()
        logger.info("Scheduler arrancado — collectors activos")

    def start_api(self, port: int = 8000) -> None:
        """Arranca el servidor FastAPI en un thread aparte."""
        self._api_port = port

        state = AppState()
        state.repo = self.repo
        state.brain = self.brain
        state.gate = self.gate
        state.broadcast = self.broadcast
        state.notif_repo = self.notif_repo
        state.routines = self.routines
        state.nexcourt_collector = self.nexcourt_collector
        state.knowledge = self.knowledge
        state.research_service = self.research

        app = create_app(state)

        def run_api():
            import uvicorn
            # 127.0.0.1 por defecto (ver settings.api_host): la API no tiene auth.
            uvicorn.run(app, host=settings.api_host, port=port, log_level="info")

        self._api_thread = threading.Thread(target=run_api, daemon=True, name="friday-api")
        self._api_thread.start()
        logger.info("FastAPI escuchando en http://%s:%d", settings.api_host, port)

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
        with self._db_lock:
            self.conn.close()
        logger.info("FRIDAY apagado")

    def run_cli(self) -> None:
        if not self.brain:
            print("Error: GEMINI_API_KEY no configurada en .env")
            print("El scheduler está corriendo pero el chat no está disponible.")
            print("Configurá la key y reiniciá.")
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                pass
            return

        print("\n" + "=" * 55)
        print("  FRIDAY — Sistema activo")
        print("=" * 55)
        print(f"  Modelo: {settings.gemini_model_fast}")
        print(f"  Tools: {', '.join(self.tools_registry.names)}")
        print(f"  DB: {settings.db_path}")
        print("=" * 55)
        print("  Escribí tu mensaje (Ctrl+C para salir)")
        print("  /reset  → limpiar conversación")
        print("  /tools  → listar tools disponibles")
        print("=" * 55)

        try:
            while True:
                try:
                    user_input = input("\nVos > ").strip()
                except EOFError:
                    break

                if not user_input:
                    continue
                if user_input.lower() in ("/quit", "/exit", "/q"):
                    break
                if user_input.lower() == "/reset":
                    self.brain.reset()
                    print("[Conversación reseteada]")
                    continue
                if user_input.lower() == "/tools":
                    for name in self.tools_registry.names:
                        print(f"  • {name}")
                    continue

                response = self.brain.chat(user_input)
                print(f"\nFRIDAY > {response}")
        except KeyboardInterrupt:
            pass

        print("\nChau!")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _schedule_broadcast(broadcast: WebSocketBroadcast, points) -> None:
    """Programa el broadcast de métricas en un thread aparte (non-blocking)."""
    import asyncio

    async def _broadcast():
        for p in points:
            await broadcast.broadcast_metric(
                source=p.source,
                name=p.name,
                value=p.value,
                unit=p.unit,
                service=p.service,
            )
        # Emitir también estado de servicios si hay métricas de NEXCOURT
        for p in points:
            if p.source == "nexcourt" and p.name == "status":
                status_str = "online" if p.value == 1.0 else "offline"
                await broadcast.broadcast_service_state(
                    service=p.service or "unknown", status=status_str
                )

    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_broadcast())
        loop.close()
    except Exception:
        pass


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FRIDAY — Asistente personal")
    parser.add_argument("--cli", action="store_true", help="Modo CLI interactivo (sin API ni dashboard)")
    parser.add_argument("--streamlit", action="store_true",
                        help="Además del HUD, lanza el dashboard Streamlit legacy (:8510)")
    # Compat: el HUD lo sirve la propia API, así que --no-dashboard ya no hace falta.
    parser.add_argument("--no-dashboard", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--api-port", type=int, default=settings.api_port,
                        help="Puerto del API + HUD (default: settings.api_port = 8000)")
    parser.add_argument("--dashboard-port", type=int, default=8510, help="Puerto del Streamlit legacy (default: 8510)")
    args = parser.parse_args()

    system = FridaySystem()
    system.start_scheduler()

    if args.cli:
        # Solo CLI, sin API ni dashboard
        try:
            system.run_cli()
        finally:
            system.stop()
        return

    # Modo unificado: la API sirve TODO, incluido el HUD (Command Center) en la raíz.
    # La voz Jarvis corre en el listener (friday/voice/wake.py), en el mismo host.
    system.start_api(port=args.api_port)
    logger.info("HUD (Command Center) en http://localhost:%d/", args.api_port)
    logger.info("API/Docs en http://localhost:%d/docs", args.api_port)

    try:
        if args.streamlit:
            # Dashboard Streamlit legacy (opt-in). El HUD nuevo NO lo necesita;
            # queda solo para quien todavía quiera las vistas viejas.
            dashboard_path = Path(__file__).parent / "dashboard" / "app.py"
            logger.info("Streamlit legacy en http://localhost:%d", args.dashboard_port)
            proc = subprocess.Popen([
                sys.executable, "-m", "streamlit", "run",
                str(dashboard_path),
                "--server.port", str(args.dashboard_port),
                "--server.headless", "true",
            ])
            try:
                proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
        else:
            logger.info("Ctrl+C para detener.")
            threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        system.stop()


if __name__ == "__main__":
    main()
