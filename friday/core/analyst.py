"""TrendAnalyzer — Pilar 3 del salero proactivo: de monitor a analista.

El notifier mira umbrales fijos en el INSTANTE (CPU > 90% ahora). El analista
mira TENDENCIAS en el TIEMPO: compara la media de una ventana reciente contra
un baseline más largo y avisa si hay una subida sostenida —aunque ningún umbral
instantáneo se haya cruzado—. Es la diferencia entre un termómetro y un médico
que ve que la fiebre viene subiendo.

Regla de oro (la misma de todo el sistema): la estadística DETECTA, el LLM no.
La detección es media-reciente-vs-baseline, determinista y barata. Nada de
pedirle a un modelo que "mire los números y decida si hay anomalía".

Reusa la cañería del Pilar 1: produce Notification(source="analyst") y las
despacha por el mismo ProactiveDispatcher, con la disciplina anti-spam del
notifier (solo avisa cuando el insight es NUEVO, no en cada corrida).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean

from friday.config import settings
from friday.storage.notification_repo import Notification

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Signal:
    """Una serie a vigilar. `floor` evita avisar sobre ruido en valores bajos
    (una RAM que sube de 5% a 8% no importa; de 55% a 75% sí)."""

    source: str
    name: str
    label: str
    unit: str
    floor: float


# Señales del primer corte: las que tienen datos fluyendo siempre (el system
# collector corre cada 10s, local, sin depender de AWS/credenciales).
_SIGNALS = [
    Signal("system", "ram_percent", "RAM", "%", 50.0),
    Signal("system", "cpu_percent", "CPU", "%", 40.0),
    Signal("system", "disk_percent", "Disk", "%", 60.0),
]


class TrendAnalyzer:
    """Detecta subidas sostenidas comparando ventana reciente vs baseline."""

    def __init__(self, repo, dispatcher=None, notif_repo=None) -> None:
        self._repo = repo
        self._dispatcher = dispatcher
        self._notif_repo = notif_repo
        # Anti-spam: signal → último estado emitido ("up"). Igual que el notifier:
        # solo se avisa en el CAMBIO, no en cada corrida cada 30 min.
        self._state: dict[str, str] = {}

    # ── Orquestación ──────────────────────────────────────────────────────

    def run(self) -> list[Notification]:
        """Analiza, persiste y despacha los insights nuevos. Para el scheduler."""
        notifs = self.analyze()
        for n in notifs:
            if self._notif_repo:
                try:
                    self._notif_repo.save(n)
                except Exception:
                    logger.exception("Analyst: error guardando insight")
        if notifs and self._dispatcher:
            self._dispatcher.dispatch(notifs)
        return notifs

    # ── Detección (pura, sin red ni I/O salvo el repo) ────────────────────

    def analyze(self) -> list[Notification]:
        """Recorre las señales y devuelve insights de tendencia NUEVOS."""
        out: list[Notification] = []
        for sig in _SIGNALS:
            notif = self._detect(sig)
            if notif:
                out.append(notif)
        return out

    def _detect(self, sig: Signal) -> Notification | None:
        now = datetime.now(timezone.utc)
        recent_start = now - timedelta(minutes=settings.analyst_recent_window_minutes)
        baseline_start = now - timedelta(hours=settings.analyst_baseline_window_hours)

        recent = self._values(sig, start=recent_start, end=now)
        baseline = self._values(sig, start=baseline_start, end=recent_start)

        min_pts = settings.analyst_min_points
        if len(recent) < min_pts or len(baseline) < min_pts:
            return None  # datos insuficientes (p.ej. FRIDAY recién arrancó)

        recent_avg = mean(recent)
        baseline_avg = mean(baseline)

        # Por debajo del piso de relevancia: no es una tendencia que importe.
        if recent_avg < sig.floor:
            self._clear(sig.name)
            return None

        rise = (recent_avg - baseline_avg) / baseline_avg if baseline_avg else 0.0
        if rise < settings.analyst_min_rise_pct:
            self._clear(sig.name)
            return None

        # Subida sostenida detectada. Anti-spam: solo si es nueva.
        if self._state.get(sig.name) == "up":
            return None
        self._state[sig.name] = "up"

        pct = round(rise * 100)
        return Notification(
            level="warning",
            title=f"{sig.label} en alza sostenida",
            message=(
                f"{sig.label} viene subiendo: promedio reciente "
                f"{recent_avg:.0f}{sig.unit} vs {baseline_avg:.0f}{sig.unit} de base "
                f"(+{pct}%)."
            ),
            source="analyst",
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def _values(self, sig: Signal, *, start: datetime, end: datetime) -> list[float]:
        try:
            points = self._repo.query(
                source=sig.source, name=sig.name, start=start, end=end, limit=5000,
            )
        except Exception:
            logger.exception("Analyst: error consultando %s/%s", sig.source, sig.name)
            return []
        return [p.value for p in points]

    def _clear(self, name: str) -> None:
        self._state.pop(name, None)
