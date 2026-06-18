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
from friday.collectors.gemini_usage import GeminiUsageCollector
from friday.collectors.nexcourt import NexcourtCollector
from friday.collectors.system import SystemCollector
from friday.config import settings
from friday.core.brain import FridayBrain
from friday.core.notifier import Notifier
from friday.core.tools_registry import build_registry
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository
from friday.storage.chat_repo import ChatRepository
from friday.storage.notification_repo import NotificationRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_RETENTION_DAYS = 30


class FridaySystem:
    """Orquesta todos los subsistemas de FRIDAY."""

    def __init__(self) -> None:
        logger.info("Inicializando FRIDAY — DB: %s", settings.db_path)

        self.conn = get_connection(settings.db_path)
        self.repo = MetricsRepository(self.conn)
        self.chat_repo = ChatRepository(self.conn)
        self.notif_repo = NotificationRepository(self.conn)

        self.tools_registry = build_registry(self.repo)

        action_registry = build_action_registry()
        self.gate = PermissionGate(action_registry)
        register_agent_tools(self.tools_registry, self.gate)

        # WebSocket broadcast (compartido entre collectors, notifier y API)
        self.broadcast = WebSocketBroadcast()

        self.notifier = Notifier(
            repo=self.repo,
            notif_repo=self.notif_repo,
            broadcast=self.broadcast,
        )

        self.brain = (
            FridayBrain(
                registry=self.tools_registry,
                chat_repo=self.chat_repo,
                session_id=self.chat_repo.create_session(),
            )
            if settings.gemini_api_key
            else None
        )

        self.scheduler = BackgroundScheduler()
        self._register_collectors()
        self._register_maintenance()
        self._register_notifier()

        self._api_thread: threading.Thread | None = None
        self._api_port: int = 8000

    def _register_collectors(self) -> None:
        collectors = [
            SystemCollector(),
            GeminiUsageCollector(),
        ]

        if settings.nexcourt_services or settings.nexcourt_services_config:
            collectors.append(NexcourtCollector())

        for c in collectors:
            self.scheduler.add_job(
                self._make_job(c),
                trigger="interval",
                seconds=c.interval_seconds,
                id=f"collector_{c.source}",
                max_instances=1,
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
            self.notifier.run,
            trigger="interval",
            seconds=60,
            id="notifier_check",
            max_instances=1,
        )
        logger.info("Notifier chequea cada 60s")

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

        app = create_app(state)

        def run_api():
            import uvicorn
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

        self._api_thread = threading.Thread(target=run_api, daemon=True, name="friday-api")
        self._api_thread.start()
        logger.info("FastAPI escuchando en http://0.0.0.0:%d", port)

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
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
    import concurrent.futures

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
    parser.add_argument("--no-dashboard", action="store_true", help="No lanzar dashboard (solo API)")
    parser.add_argument("--api-port", type=int, default=8000, help="Puerto del API (default: 8000)")
    parser.add_argument("--dashboard-port", type=int, default=8510, help="Puerto del dashboard (default: 8510)")
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

    # Modo unificado: API siempre activa
    system.start_api(port=args.api_port)

    try:
        if not args.no_dashboard:
            dashboard_path = Path(__file__).parent / "dashboard" / "app.py"
            logger.info("Dashboard en http://localhost:%d", args.dashboard_port)
            logger.info("API en http://localhost:%d", args.api_port)
            logger.info("Docs en http://localhost:%d/docs", args.api_port)
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
            logger.info("API en http://localhost:%d | Ctrl+C para detener", args.api_port)
            threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        system.stop()


if __name__ == "__main__":
    main()
