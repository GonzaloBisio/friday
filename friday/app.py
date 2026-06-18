"""FRIDAY — Bootstrap unificado del sistema completo.

Levanta scheduler (background thread) + brain + agent + todos los collectors.
Modos de uso:
  python -m friday.app              → CLI interactivo
  python -m friday.app --dashboard  → Lanza Streamlit dashboard + scheduler
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
from friday.collectors.gemini_usage import GeminiUsageCollector
from friday.collectors.nexcourt import NexcourtCollector
from friday.collectors.system import SystemCollector
from friday.config import settings
from friday.core.brain import FridayBrain
from friday.core.tools_registry import build_registry
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository

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

        self.tools_registry = build_registry(self.repo)

        action_registry = build_action_registry()
        self.gate = PermissionGate(action_registry)
        register_agent_tools(self.tools_registry, self.gate)

        self.brain = FridayBrain(registry=self.tools_registry) if settings.gemini_api_key else None

        self.scheduler = BackgroundScheduler()
        self._register_collectors()
        self._register_maintenance()

    def _register_collectors(self) -> None:
        collectors = [
            SystemCollector(),
            GeminiUsageCollector(),
        ]

        if settings.nexcourt_services:
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

    def _make_job(self, collector):
        def job():
            points = collector.run()
            if points:
                self.repo.save_many(points)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="FRIDAY — Asistente personal")
    parser.add_argument("--dashboard", action="store_true", help="Lanzar Streamlit dashboard")
    parser.add_argument("--port", type=int, default=8510, help="Puerto del dashboard (default: 8510)")
    args = parser.parse_args()

    system = FridaySystem()
    system.start_scheduler()

    try:
        if args.dashboard:
            dashboard_path = Path(__file__).parent / "dashboard" / "app.py"
            logger.info("Lanzando dashboard en puerto %d", args.port)
            proc = subprocess.Popen([
                sys.executable, "-m", "streamlit", "run",
                str(dashboard_path),
                "--server.port", str(args.port),
                "--server.headless", "true",
            ])
            try:
                proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
        else:
            system.run_cli()
    finally:
        system.stop()


if __name__ == "__main__":
    main()
