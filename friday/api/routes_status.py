"""Rutas REST de status y métricas.

GET /api/status   — snapshot de signos vitales.
GET /api/metrics  — serie temporal con filtros.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["status"])


def _repo(request: Request):
    return request.app.state.friday.repo


# ── GET /api/status ──────────────────────────────────────────────────────

@router.get("/status")
def get_status(request: Request) -> JSONResponse:
    """Snapshot de signos vitales: sistema, Gemini, NEXCOURT."""
    repo = _repo(request)
    if repo is None:
        return JSONResponse(
            status_code=503,
            content={"status": "no_data", "detail": "Repo no disponible"},
        )

    now = datetime.now(timezone.utc)

    def latest(src: str, name: str) -> Any:
        p = repo.latest(src, name)
        return p.value if p else None

    def latest_service(src: str, name: str) -> dict[str, Any]:
        """Devuelve {service: value} para todos los servicios de una fuente."""
        from datetime import timedelta
        points = repo.query(source=src, name=name, start=now - timedelta(minutes=5), limit=500)
        result: dict[str, Any] = {}
        for p in points:
            if p.service and p.service not in result:
                result[p.service] = p.value
        return result

    return JSONResponse(content={
        "timestamp": now.isoformat(),
        "system": {
            "cpu_percent": latest("system", "cpu_percent"),
            "ram_percent": latest("system", "ram_percent"),
            "disk_percent": latest("system", "disk_percent"),
            "uptime_seconds": latest("system", "uptime_seconds"),
        },
        "gemini": {
            "requests": latest("gemini", "requests"),
            "tokens_in": latest("gemini", "tokens_in"),
            "tokens_out": latest("gemini", "tokens_out"),
            "cost_usd": latest("gemini", "cost_usd"),
        },
        "nexcourt": {
            "services": latest_service("nexcourt", "status"),
        },
        "services": _services_status(repo, now),
    })


def _services_status(repo, now: datetime) -> list[dict[str, Any]]:
    """Estado de servicios internos de FRIDAY (SQLite, Gemini, collectors, etc.)."""
    from friday.config import settings

    recent = now - timedelta(minutes=5)
    has_system = len(repo.query(source="system", name="cpu_percent", start=recent, limit=1)) > 0
    has_gemini = len(repo.query(source="gemini", name="requests", start=recent, limit=1)) > 0

    # NEXCOURT: mostrar "disabled" si está en modo "off"
    nexcourt_status = "disabled" if settings.nexcourt_mode == "off" else "standby"

    return [
        {"name": "SQLite", "status": "online"},
        {"name": "Gemini", "status": "online" if has_gemini else "standby"},
        {"name": "System Collector", "status": "online" if has_system else "standby"},
        {"name": "NEXCOURT Collector", "status": nexcourt_status},
        {"name": "Dashboard", "status": "online"},
    ]


# ── GET /api/metrics ─────────────────────────────────────────────────────

@router.get("/metrics")
def get_metrics(
    request: Request,
    source: str | None = Query(None, description="Fuente: system, gemini, nexcourt, productivity"),
    name: str | None = Query(None, description="Nombre de la métrica"),
    service: str | None = Query(None, description="Servicio NEXCOURT específico"),
    hours: int = Query(24, ge=1, le=720, description="Horas hacia atrás"),
    limit: int = Query(1000, ge=1, le=10000, description="Máximo de puntos"),
) -> JSONResponse:
    """Serie temporal de métricas con filtros."""
    repo = _repo(request)
    if repo is None:
        return JSONResponse(status_code=503, content={"detail": "Repo no disponible"})

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)

    points = repo.query(
        source=source,
        name=name,
        service=service,
        start=start,
        limit=limit,
    )

    return JSONResponse(content={
        "count": len(points),
        "points": [
            {
                "timestamp": p.timestamp.isoformat(),
                "source": p.source,
                "name": p.name,
                "value": p.value,
                "unit": p.unit,
                "service": p.service,
                "tags": p.tags,
            }
            for p in points
        ],
    })
