"""BriefingService — Pilar 2 del salero proactivo: rituales agendados.

A diferencia de las ALERTAS (Pilar 1), que son plantillas deterministas porque
viven en el camino crítico "algo se rompió", los briefings son proactividad
PREDECIBLE y bienvenida (buen día / cierre del día). Acá el LLM SÍ aporta:
redacta el resumen con la persona de FRIDAY a partir de datos crudos.

Disciplina clave (la misma regla de oro de todo el sistema): el LLM es el
"nice to have", NUNCA el piso. Si Gemini/Ollama fallan, hay una plantilla
determinista que garantiza que el ritual igual ocurra. Un briefing nunca se cae.

El texto se emite por el canal proactivo (Pilar 1) con speak=True: el cliente
de voz lo dice y muestra el toast. Si hay una conversación activa, el cliente
cede la voz (muestra el toast igual) — esa coordinación vive en el listener (friday/voice/wake.py).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Títulos del toast según el ritual. El cuerpo (message) es el mismo texto hablado.
_TITLES = {
    "morning": "FRIDAY — Buenos días",
    "evening": "FRIDAY — Cierre del día",
}


class BriefingService:
    """Junta el estado del sistema, lo hace redactar por el LLM y lo emite por voz.

    Separación testeable: `gather()` (lee métricas, sin red LLM), `compose_text()`
    (LLM con fallback a plantilla, decisión pura sobre el resultado) y `_emit()`
    (el I/O del WebSocket). `run()` orquesta los tres.
    """

    def __init__(self, repo, brain, broadcast) -> None:
        self._repo = repo
        self._brain = brain
        self._broadcast = broadcast

    # ── Orquestación ──────────────────────────────────────────────────────

    def run(self, kind: str) -> str:
        """Junta datos, redacta el briefing y lo empuja al canal proactivo."""
        data = self.gather()
        text = self.compose_text(kind, data)
        self._emit(kind, text)
        return text

    # ── Recolección de datos (sin LLM) ────────────────────────────────────

    def gather(self) -> dict:
        """Estado actual: sistema (CPU/RAM/disco), servicios caídos, costo del día."""
        return {
            "cpu": self._latest("system", "cpu_percent"),
            "ram": self._latest("system", "ram_percent"),
            "disk": self._latest("system", "disk_percent"),
            "services_down": self._services_down(),
            "gemini_cost_today": self._gemini_cost_today(),
        }

    def _latest(self, source: str, name: str) -> float | None:
        point = self._repo.latest(source, name)
        return point.value if point else None

    def _services_down(self) -> list[str]:
        """Servicios NEXCOURT reportados como DOWN en los últimos 5 minutos."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(minutes=5)
        try:
            points = self._repo.query(
                source="nexcourt", name="status", start=recent, limit=200,
            )
        except Exception:
            logger.exception("Briefing: error leyendo estado NEXCOURT")
            return []
        # Tomar el estado más reciente por servicio (los puntos vienen desc).
        latest: dict[str, float] = {}
        for p in points:
            if p.service and p.service not in latest:
                latest[p.service] = p.value
        return sorted(s for s, v in latest.items() if v == 0.0)

    def _gemini_cost_today(self) -> float:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            points = self._repo.query(
                source="gemini", name="cost_usd", start=today_start, limit=5000,
            )
        except Exception:
            logger.exception("Briefing: error leyendo costo Gemini")
            return 0.0
        return sum(p.value for p in points)

    # ── Composición (LLM con piso de plantilla) ───────────────────────────

    def compose_text(self, kind: str, data: dict) -> str:
        """Redacta el briefing con el LLM; cae a plantilla determinista si falla."""
        prompt = self._build_prompt(kind, data)
        try:
            text = (self._brain.compose(prompt) or "").strip()
            if text and text != "(sin respuesta)":
                return text
            logger.warning("Briefing: LLM devolvió vacío; uso plantilla.")
        except Exception:
            # 429, Ollama caído, lo que sea: el ritual NO se cae, hay piso.
            logger.warning("Briefing: LLM falló; uso plantilla determinista.", exc_info=True)
        return self._fallback_text(kind, data)

    def _build_prompt(self, kind: str, data: dict) -> str:
        facts = self._facts_block(data)
        when = "morning briefing" if kind == "morning" else "end-of-day wind-down"
        tone = (
            "Wish him a good morning and set up his day."
            if kind == "morning"
            else "Help him wind down; note anything still needing attention tomorrow."
        )
        return (
            f"This is Gonzalo's {when}. Here is the current state of his systems:\n"
            f"{facts}\n\n"
            f"Give him a brief spoken briefing in your voice (address him as 'sir'). "
            f"{tone} Flag anything that needs attention; if all is healthy, say so "
            f"with a light touch. One or two short sentences, no lists."
        )

    def _facts_block(self, data: dict) -> str:
        lines = [
            f"- CPU: {self._pct(data['cpu'])}",
            f"- RAM: {self._pct(data['ram'])}",
            f"- Disk: {self._pct(data['disk'])}",
        ]
        down = data["services_down"]
        lines.append(
            f"- Services DOWN: {', '.join(down)}" if down else "- Services: all up"
        )
        lines.append(f"- Gemini cost today: ${data['gemini_cost_today']:.2f}")
        return "\n".join(lines)

    def _fallback_text(self, kind: str, data: dict) -> str:
        """Plantilla determinista — el piso garantizado si el LLM no responde."""
        greeting = "Good morning, sir." if kind == "morning" else "Winding down, sir."
        down = data["services_down"]
        if down:
            services = f"Heads up: {', '.join(down)} {'is' if len(down) == 1 else 'are'} down."
        else:
            services = "All services are up."
        return (
            f"{greeting} CPU {self._pct(data['cpu'])}, RAM {self._pct(data['ram'])}, "
            f"disk {self._pct(data['disk'])}. {services} "
            f"Gemini cost today is ${data['gemini_cost_today']:.2f}."
        )

    @staticmethod
    def _pct(value: float | None) -> str:
        return f"{value:.0f}%" if value is not None else "n/a"

    # ── Emisión por el canal proactivo ────────────────────────────────────

    def _emit(self, kind: str, text: str) -> None:
        """Empuja el briefing por WebSocket (voz + toast). Best-effort.

        Async desde un thread del scheduler: event-loop efímero, igual patrón que
        el notifier. El briefing siempre habla (speak=True) —es un ritual
        bienvenido—; el cliente decide ceder la voz si hay charla activa.
        """
        if not self._broadcast:
            return
        title = _TITLES.get(kind, "FRIDAY")
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                self._broadcast.broadcast_proactive(
                    text=text, speak=True, level="info", title=title, message=text,
                )
            )
            loop.close()
        except Exception:
            logger.exception("Briefing: error emitiendo por WebSocket")
