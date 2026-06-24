"""Factory que elige el cerebro de FRIDAY según la configuración.

`settings.llm_provider` decide:
- "ollama" (default): cerebro local, sin costo. No requiere API key.
- "gemini": requiere GEMINI_API_KEY; si falta, retorna None.

Los imports de cada cerebro son perezosos para no cargar el SDK de
Gemini cuando se usa Ollama (y viceversa).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from friday.config import settings
from friday.core.llm_base import Brain

if TYPE_CHECKING:
    from friday.core.tools_registry import ToolsRegistry
    from friday.storage.chat_repo import ChatRepository

logger = logging.getLogger(__name__)


def build_brain(
    registry: "ToolsRegistry",
    *,
    chat_repo: "ChatRepository | None" = None,
    session_id: str | None = None,
    memory_repo: object | None = None,
) -> Brain | None:
    """Construye el cerebro activo según settings.llm_provider."""
    provider = (settings.llm_provider or "ollama").lower()

    if provider == "gemini":
        if not settings.gemini_api_key:
            logger.warning(
                "llm_provider=gemini pero falta GEMINI_API_KEY; FRIDAY queda sin cerebro."
            )
            return None
        from friday.core.brain import FridayBrain

        logger.info("Cerebro: Gemini (%s)", settings.gemini_model_fast)
        return FridayBrain(
            registry=registry, chat_repo=chat_repo, session_id=session_id,
            memory_repo=memory_repo,
        )

    if provider != "ollama":
        logger.warning("llm_provider desconocido '%s'; usando ollama.", provider)

    from friday.core.ollama_brain import OllamaBrain

    logger.info("Cerebro: Ollama local (%s)", settings.ollama_model)
    return OllamaBrain(
        registry=registry, chat_repo=chat_repo, session_id=session_id,
        memory_repo=memory_repo,
    )
