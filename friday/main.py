"""FRIDAY — Entrypoint principal."""

import logging

from friday.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("FRIDAY starting — DB: %s", settings.db_path)
    # TODO: Fase 2 — arrancar scheduler + collectors
    # TODO: Fase 3 — arrancar dashboard


if __name__ == "__main__":
    main()
