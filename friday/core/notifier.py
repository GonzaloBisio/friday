"""Notifier — chequea umbrales y genera notificaciones proactivas.

Se ejecuta como job del scheduler cada 60s. Evalúa:
- CPU > umbral → warning/critical
- NEXCOURT servicios caídos → critical
- Costo de Gemini diario > umbral → warning
- RAM/Disk > umbral → warning

Las notificaciones se persisten en SQLite y se emiten por WebSocket.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from friday.config import settings
from friday.storage.metrics_repo import MetricsRepository
from friday.storage.notification_repo import Notification, NotificationRepository

logger = logging.getLogger(__name__)

# ── Umbrales (configurables en .env en el futuro) ────────────────────────
CPU_WARN = 70.0
CPU_CRIT = 90.0
RAM_WARN = 80.0
RAM_CRIT = 95.0
DISK_WARN = 85.0
DISK_CRIT = 95.0
GEMINI_COST_DAILY_WARN = 0.50  # USD
GEMINI_COST_DAILY_CRIT = 2.00


class Notifier:
    """Evalúa condiciones y dispara notificaciones si se superan umbrales.

    Mantiene estado para evitar notificaciones duplicadas (solo notifica
    cuando el estado CAMBIA, no en cada chequeo).
    """

    def __init__(
        self,
        repo: MetricsRepository,
        notif_repo: NotificationRepository,
        broadcast=None,
    ) -> None:
        self._repo = repo
        self._notif_repo = notif_repo
        self._broadcast = broadcast
        self._state: dict[str, str] = {}  # key → último nivel notificado

    def run(self) -> list[Notification]:
        """Ejecuta todos los chequeos. Retorna notificaciones nuevas generadas."""
        notifications: list[Notification] = []
        notifications.extend(self._check_system())
        notifications.extend(self._check_nexcourt())
        notifications.extend(self._check_gemini_cost())
        return notifications

    # ── Chequeos ─────────────────────────────────────────────────────────

    def _check_system(self) -> list[Notification]:
        notifs: list[Notification] = []

        cpu = self._repo.latest("system", "cpu_percent")
        ram = self._repo.latest("system", "ram_percent")
        disk = self._repo.latest("system", "disk_percent")

        if cpu:
            notifs.extend(self._threshold_check(
                key="cpu", value=cpu.value,
                warn=CPU_WARN, crit=CPU_CRIT,
                unit="%", label="CPU",
            ))

        if ram:
            notifs.extend(self._threshold_check(
                key="ram", value=ram.value,
                warn=RAM_WARN, crit=RAM_CRIT,
                unit="%", label="RAM",
            ))

        if disk:
            notifs.extend(self._threshold_check(
                key="disk", value=disk.value,
                warn=DISK_WARN, crit=DISK_CRIT,
                unit="%", label="Disco",
            ))

        return notifs

    def _check_nexcourt(self) -> list[Notification]:
        """Verifica servicios NEXCOURT caídos."""
        notifs: list[Notification] = []
        now = datetime.now(timezone.utc)
        recent = now - timedelta(minutes=5)

        status_points = self._repo.query(
            source="nexcourt", name="status", start=recent, limit=100,
        )

        # Agrupar por servicio, tomar el más reciente
        latest_status: dict[str, float] = {}
        for p in status_points:
            if p.service and p.service not in latest_status:
                latest_status[p.service] = p.value

        for service, status_val in latest_status.items():
            key = f"nexcourt_{service}"
            if status_val == 0.0:
                notif = self._maybe_notify(
                    key=key, level="critical",
                    title=f"NEXCOURT: {service} caído",
                    message=f"El servicio {service} no responde. Status: DOWN",
                    source="nexcourt",
                )
                if notif:
                    notifs.append(notif)
            else:
                # Si estaba caído y volvió, notificar recuperación
                if self._state.get(key) in ("warning", "critical"):
                    self._clear_state(key)
                    notifs.append(Notification(
                        level="info",
                        title=f"NEXCOURT: {service} recuperado",
                        message=f"El servicio {service} volvió a estar UP",
                        source="nexcourt",
                    ))

        return notifs

    def _check_gemini_cost(self) -> list[Notification]:
        """Verifica costo diario de Gemini."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        cost_points = self._repo.query(
            source="gemini", name="cost_usd", start=today_start, limit=5000,
        )
        total_cost = sum(p.value for p in cost_points)

        return self._threshold_check(
            key="gemini_cost",
            value=total_cost,
            warn=GEMINI_COST_DAILY_WARN,
            crit=GEMINI_COST_DAILY_CRIT,
            unit="USD",
            label="Costo Gemini",
        )

    # ── Threshold logic ──────────────────────────────────────────────────

    def _threshold_check(
        self, key: str, value: float,
        warn: float, crit: float, unit: str, label: str,
    ) -> list[Notification]:
        """Evalúa umbrales warn/crit y genera notificación si cambió el estado."""
        if value >= crit:
            level = "critical"
        elif value >= warn:
            level = "warning"
        else:
            # Volvió a normal — notificar recuperación si antes estaba alerta
            if self._state.get(key) in ("warning", "critical"):
                self._clear_state(key)
                return [Notification(
                    level="info",
                    title=f"{label} normalizado",
                    message=f"{label} volvió a niveles normales ({value:.1f}{unit})",
                    source="system",
                )]
            return []

        notif = self._maybe_notify(
            key=key, level=level,
            title=f"{label}: {value:.1f}{unit}",
            message=f"{label} superó el umbral de {level} ({value:.1f}{unit} > {warn if level=='warning' else crit}{unit})",
            source="system",
        )
        return [notif] if notif else []

    def _maybe_notify(
        self, key: str, level: str, title: str, message: str, source: str,
    ) -> Notification | None:
        """Genera notificación solo si el nivel cambió respecto al estado anterior."""
        prev = self._state.get(key)
        if prev == level:
            return None  # sin cambios, no repetir
        self._state[key] = level

        notif = Notification(level=level, title=title, message=message, source=source)
        try:
            self._notif_repo.save(notif)
        except Exception:
            logger.exception("Error guardando notificación")

        # Broadcast via WebSocket
        if self._broadcast:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    self._broadcast.send_json({
                        "type": "notification",
                        "level": level,
                        "title": title,
                        "message": message,
                        "source": source,
                    })
                )
                loop.close()
            except Exception:
                pass

        logger.info("Notificación [%s]: %s", level.upper(), title)
        return notif

    def _clear_state(self, key: str) -> None:
        self._state.pop(key, None)
