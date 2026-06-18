"""Registro de tools que FRIDAY expone a Gemini vía function calling."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from friday.models import MetricPoint
from friday.storage.metrics_repo import MetricsRepository


class ToolsRegistry:
    """Registro centralizado de funciones que Gemini puede invocar."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}

    def register(self, fn: Callable) -> Callable:
        self._tools[fn.__name__] = fn
        return fn

    @property
    def names(self) -> list[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> Callable | None:
        return self._tools.get(name)

    def execute(self, name: str, args: dict[str, Any]) -> Any:
        fn = self._tools.get(name)
        if fn is None:
            raise KeyError(f"Tool '{name}' no registrada")
        return fn(**args)

    def as_callable_list(self) -> list[Callable]:
        """Retorna las funciones para pasar como tools al SDK de Gemini."""
        return list(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def build_registry(repo: MetricsRepository) -> ToolsRegistry:
    """Construye un ToolsRegistry con las tools estándar de lectura."""
    reg = ToolsRegistry()

    def consultar_metricas(
        source: str,
        name: str | None = None,
        horas: int = 24,
        limit: int = 50,
    ) -> str:
        """Consulta métricas almacenadas en FRIDAY.

        Args:
            source: Fuente de métricas — "system", "gemini", "nexcourt" o "productivity".
            name: Nombre específico de la métrica (ej. "cpu_percent", "cost_usd"). Si es None, trae todas las de esa fuente.
            horas: Ventana de tiempo hacia atrás en horas. Default 24.
            limit: Cantidad máxima de puntos a retornar. Default 50.

        Returns:
            JSON con las métricas encontradas.
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=horas)
        points = repo.query(source=source, name=name, start=start, limit=limit)
        return _points_to_json(points)

    def resumen_costos(horas: int = 24) -> str:
        """Resume el costo acumulado de uso de Gemini en un período.

        Args:
            horas: Ventana de tiempo hacia atrás en horas. Default 24.

        Returns:
            JSON con el resumen de costos (total USD, requests, tokens).
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=horas)
        cost_points = repo.query(source="gemini", name="cost_usd", start=start, limit=5000)
        req_points = repo.query(source="gemini", name="requests", start=start, limit=5000)
        tokens_in = repo.query(source="gemini", name="tokens_in", start=start, limit=5000)
        tokens_out = repo.query(source="gemini", name="tokens_out", start=start, limit=5000)

        total_cost = sum(p.value for p in cost_points)
        total_requests = sum(p.value for p in req_points)
        total_in = sum(p.value for p in tokens_in)
        total_out = sum(p.value for p in tokens_out)

        return json.dumps({
            "periodo_horas": horas,
            "costo_total_usd": round(total_cost, 6),
            "requests_totales": int(total_requests),
            "tokens_in_totales": int(total_in),
            "tokens_out_totales": int(total_out),
        })

    reg.register(consultar_metricas)
    reg.register(resumen_costos)
    return reg


def _points_to_json(points: list[MetricPoint]) -> str:
    rows = [
        {
            "timestamp": p.timestamp.isoformat(),
            "source": p.source,
            "name": p.name,
            "value": p.value,
            "unit": p.unit,
            "service": p.service,
        }
        for p in points
    ]
    return json.dumps(rows, ensure_ascii=False)
