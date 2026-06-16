"""FRIDAY — Entrypoint principal."""

from __future__ import annotations

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from friday.collectors.base import Collector
from friday.collectors.gemini_usage import GeminiUsageCollector
from friday.collectors.system import SystemCollector
from friday.config import settings
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _make_job(collector: Collector, repo: MetricsRepository):
    """Crea una función-job para APScheduler que ejecuta un collector y persiste."""

    def job() -> None:
        points = collector.run()
        if points:
            repo.save_many(points)
            logger.info(
                "Collector[%s] → %d puntos guardados", collector.source, len(points)
            )

    return job


def main() -> None:
    logger.info("FRIDAY starting — DB: %s", settings.db_path)

    conn = get_connection(settings.db_path)
    repo = MetricsRepository(conn)

    collectors: list[Collector] = [
        SystemCollector(),
        GeminiUsageCollector(),
    ]

    scheduler = BlockingScheduler()

    for collector in collectors:
        scheduler.add_job(
            _make_job(collector, repo),
            trigger="interval",
            seconds=collector.interval_seconds,
            id=f"collector_{collector.source}",
            name=f"Collector: {collector.source}",
            max_instances=1,
        )
        logger.info(
            "Registrado collector[%s] cada %ds",
            collector.source,
            collector.interval_seconds,
        )

    def shutdown(signum, frame):
        logger.info("Señal recibida, apagando scheduler...")
        scheduler.shutdown(wait=False)
        conn.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Scheduler arrancado — %d collectors activos", len(collectors))
    # TODO: Fase 3 — arrancar dashboard en paralelo
    scheduler.start()


if __name__ == "__main__":
    main()
