"""Ruta REST de autoobservabilidad (Pilar 6).

GET /api/health — signos vitales de FRIDAY (éxito de tools, fallbacks, latencia).
Lo consume el dashboard JARVIS para mostrar la "salud" del asistente en vivo.
"""

from __future__ import annotations

from fastapi import APIRouter

from friday.core.health import health_tracker

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health() -> dict:
    """Snapshot de salud de la sesión actual."""
    return health_tracker.snapshot()
