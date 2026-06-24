"""FRIDAY API — FastAPI application factory.

Provee REST + WebSocket para el dashboard y futura UI Tauri.
Se integra con FridaySystem via shared state injection.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from friday.api.routes_agent import router as agent_router
from friday.api.routes_chat import router as chat_router
from friday.api.routes_dashboard import router as dashboard_router
from friday.api.routes_gastos import router as gastos_router
from friday.api.routes_health import router as health_router
from friday.api.routes_lights import router as lights_router
from friday.api.routes_nexcourt import router as nexcourt_router
from friday.api.routes_notifications import router as notifications_router
from friday.api.routes_proactive import router as proactive_router
from friday.api.routes_research import router as research_router
from friday.api.routes_routines import router as routines_router
from friday.api.routes_status import router as status_router
from friday.api.routes_voice import router as voice_router
from friday.api.ws import router as ws_router


class AppState:
    """Estado compartido que la API recibe de FridaySystem.

    Lo injectamos como dependency en los route handlers.
    """

    def __init__(self) -> None:
        self.repo: Any = None              # MetricsRepository
        self.brain: Any = None             # FridayBrain | None
        self.gate: Any = None              # PermissionGate | None
        self.broadcast: Any = None         # WebSocketBroadcast | None
        self.notif_repo: Any = None        # NotificationRepository | None
        self.routines: Any = None          # RoutineEngine | None
        self.nexcourt_collector: Any = None  # CloudWatchCollector | NexcourtCollector | None
        self.knowledge: Any = None         # KnowledgeStore | None
        self.research_service: Any = None  # ResearchService | None


def create_app(state: AppState | None = None) -> FastAPI:
    """Crea la app FastAPI con todos los routers montados."""
    app = FastAPI(
        title="FRIDAY API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    # CORS abierto para desarrollo local (Tauri + dashboard)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Guardamos el estado en app.state para acceso desde routes
    if state is not None:
        app.state.friday = state
    else:
        app.state.friday = AppState()

    # Routers
    app.include_router(status_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(agent_router, prefix="/api/agent")
    app.include_router(notifications_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(lights_router, prefix="/api")
    app.include_router(nexcourt_router, prefix="/api")
    app.include_router(proactive_router, prefix="/api")
    app.include_router(research_router, prefix="/api")
    app.include_router(routines_router, prefix="/api")
    app.include_router(gastos_router, prefix="/api")
    app.include_router(voice_router, prefix="/api")
    app.include_router(ws_router)
    # Dashboard JARVIS (Pilar 4) en la raíz: http://127.0.0.1:8000/
    app.include_router(dashboard_router)

    return app
