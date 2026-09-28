"""Puente al HUD — FRIDAY abre paneles en el Command Center (modo EDITH/JARVIS).

Dos mecanismos, ambos emiten `{"type": "hud", "action": "open", ...}` por /ws/live:

1. **Automático**: cada tool con panel asociado (TOOL_PANELS) abre, al terminar OK, la
   *tarjeta de foco* con su resultado y el motivo (lo último que dijo Gonzalo).
2. **A pedido del modelo**: la tool `mostrar_en_hud(panel, motivo, url)` para mostrar algo
   por iniciativa propia — incluida la *ventana grande* (mode="stage": video, INTEL).

El HUD decide cómo dibujar cada `panel` (ver friday/dashboard_web/index.html: PANELS).
Best-effort: sin HUD conectado no pasa nada; ningún error acá puede romper una tool.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any

logger = logging.getLogger(__name__)

# tool → (panel, título, modo). "card" = tarjeta de foco; "stage" = ventana grande.
TOOL_PANELS: dict[str, tuple[str, str, str]] = {
    "listar_procesos": ("procesos", "Procesos · top memoria", "card"),
    "info_sistema": ("host", "Host · sistema", "card"),
    "estado_sistemas": ("infra", "Infra · servicios", "card"),
    "metricas_servicio": ("metricas", "Métricas del servicio", "card"),
    "consultar_metricas": ("metricas", "Métricas", "card"),
    "resumen_costos": ("costos", "Costo de Gemini", "card"),
    "ver_gastos": ("gastos", "Gastos del mes", "card"),
    "registrar_gasto": ("gastos", "Gasto registrado", "card"),
    "buscar_web": ("web", "Resultados web", "card"),
    "leer_pagina": ("pagina", "Página", "card"),
    "consultar_research": ("intel", "INTEL · digest de hoy", "stage"),
    "reproducir_spotify": ("musica", "Now playing", "card"),
    "estado_de_friday": ("salud", "Salud de FRIDAY", "card"),
}

# Paneles que acepta mostrar_en_hud (y su modo). Los de vista cambian de pestaña.
SHOWABLE: dict[str, str] = {
    "video": "stage", "imagen": "stage", "intel": "stage",
    "procesos": "card", "host": "card", "infra": "card", "costos": "card",
    "gastos": "card", "salud": "card",
    "vista_ops": "view", "vista_control": "view", "vista_intel": "view",
}

_YT = re.compile(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{6,20})")
_RESULT_LIMIT = 6000


def youtube_id(url: str) -> str | None:
    m = _YT.search(url or "")
    return m.group(1) if m else None


class HudBridge:
    """Emite eventos de panel al HUD. Singleton de proceso (como activity_log)."""

    def __init__(self) -> None:
        self.broadcast: Any = None  # WebSocketBroadcast, lo setea FridaySystem
        self._reason = ""
        self._lock = threading.Lock()

    def set_context(self, user_message: str) -> None:
        """Lo último que pidió Gonzalo: es el "por qué" que muestra cada panel."""
        with self._lock:
            self._reason = (user_message or "").strip()[:200]

    @property
    def hud_connected(self) -> bool:
        return bool(self.broadcast) and getattr(self.broadcast, "hud_clients", 0) > 0

    def emit(self, payload: dict) -> None:
        if self.broadcast is None:
            return
        try:
            self.broadcast.emit(payload)
        except Exception:  # noqa: BLE001
            logger.exception("HUD emit falló")

    def tool_result(self, name: str, args: dict, result: Any) -> None:
        """Hook de los cerebros: si la tool tiene panel, abrir la tarjeta de foco."""
        spec = TOOL_PANELS.get(name)
        if spec is None:
            return
        panel, title, mode = spec
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        with self._lock:
            reason = self._reason
        self.emit({
            "type": "hud", "action": "open", "mode": mode, "panel": panel, "title": title,
            "tool": name, "args": args or {}, "reason": reason, "data": text[:_RESULT_LIMIT],
        })


hud_bridge = HudBridge()


def register_hud_tools(tools_reg) -> None:
    """Registra `mostrar_en_hud` (lectura/visual: sin riesgo, va directo al registry)."""

    def mostrar_en_hud(panel: str, motivo: str = "", url: str = "") -> str:
        """Muestra algo en el HUD (Command Center): un panel, una vista o un video.

        Usalo cuando mostrar sea más útil que decir (comparaciones, un video, el digest),
        aunque Gonzalo no lo haya pedido. Los datos de tools como listar_procesos o
        estado_sistemas ya se muestran solos: no hace falta llamarla para eso.

        Args:
            panel: "video" (url de YouTube), "imagen" (url), "intel", "procesos", "host",
                "infra", "costos", "gastos", "salud", "vista_ops", "vista_control" o "vista_intel".
            motivo: Una frase corta de por qué lo mostrás.
            url: Requerida para "video" (YouTube) e "imagen".

        Returns:
            Confirmación, o por qué no se pudo mostrar.
        """
        panel = (panel or "").strip().lower()
        mode = SHOWABLE.get(panel)
        if mode is None:
            return f"Panel desconocido: '{panel}'. Opciones: {', '.join(sorted(SHOWABLE))}."
        payload = {"type": "hud", "action": "open", "mode": mode, "panel": panel,
                   "title": motivo or panel, "reason": motivo, "tool": "mostrar_en_hud"}
        if panel == "video":
            vid = youtube_id(url)
            if vid is None:
                return "Para 'video' necesito una URL de YouTube válida."
            payload["video_id"] = vid
        elif panel == "imagen":
            if not (url or "").lower().startswith(("http://", "https://")):
                return "Para 'imagen' necesito una URL http(s)."
            payload["url"] = url
        if not hud_bridge.hud_connected:
            return "El HUD no está abierto. Puedo abrirlo con abrir_dashboard."
        hud_bridge.emit(payload)
        return "Listo, lo muestro en el HUD."

    tools_reg.register(mostrar_en_hud)
