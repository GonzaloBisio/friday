"""Interfaz base para todos los collectors de FRIDAY."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from friday.models import MetricPoint

logger = logging.getLogger(__name__)


class Collector(ABC):
    """Un collector recolecta métricas de una fuente y devuelve MetricPoints."""

    @property
    @abstractmethod
    def source(self) -> str:
        """Identificador de la fuente: 'system', 'gemini', 'nexcourt', 'productivity'."""

    @property
    def interval_seconds(self) -> int:
        """Intervalo de polling en segundos. Override en subclases si necesario."""
        return 10

    @abstractmethod
    def collect(self) -> list[MetricPoint]:
        """Ejecuta la recolección y devuelve una lista de MetricPoints.

        No debe lanzar excepciones — si la fuente no está disponible,
        retornar lista vacía o métricas de estado (ej. status=0).
        """

    def run(self) -> list[MetricPoint]:
        """Wrapper seguro alrededor de collect(). Captura excepciones inesperadas."""
        try:
            points = self.collect()
            logger.debug("Collector[%s] recolectó %d puntos", self.source, len(points))
            return points
        except Exception:
            logger.exception("Collector[%s] falló inesperadamente", self.source)
            return []
