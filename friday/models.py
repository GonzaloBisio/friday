"""Modelos de dominio de FRIDAY."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class MetricPoint:
    """Un punto de métrica normalizado (append-only)."""

    timestamp: datetime
    source: str          # "nexcourt" | "gemini" | "system" | "productivity"
    name: str            # ej. "cpu_percent", "tokens_out", "errors_last_hour"
    value: float
    service: str | None = None   # ej. "nexcourt-clubs-service"
    unit: str | None = None      # "%", "ms", "tokens", "usd", "count"
    tags: dict | None = field(default=None)

    def tags_json(self) -> str | None:
        """Serializa tags a JSON string para almacenamiento."""
        if self.tags is None:
            return None
        return json.dumps(self.tags, ensure_ascii=False)

    @staticmethod
    def tags_from_json(raw: str | None) -> dict | None:
        """Deserializa tags desde JSON string."""
        if raw is None:
            return None
        return json.loads(raw)

    @staticmethod
    def utcnow() -> datetime:
        """Timestamp UTC aware para usar como default."""
        return datetime.now(timezone.utc)
