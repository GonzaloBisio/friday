"""Repositorio de notificaciones proactivas de FRIDAY."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Notification:
    """Una notificación generada por el sistema."""
    level: str           # "info", "warning", "critical"
    title: str
    message: str
    source: str = "system"
    dismissed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: int | None = None


class NotificationRepository:
    """Acceso a la tabla notifications.

    El lock serializa el acceso a la conexión compartida (ver
    MetricsRepository para el porqué).
    """

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock | None = None) -> None:
        self._conn = conn
        self._lock = lock or threading.RLock()

    def save(self, n: Notification) -> int:
        """Guarda una notificación y devuelve su id."""
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO notifications (level, title, message, source, dismissed, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (n.level, n.title, n.message, n.source, int(n.dismissed), n.created_at.isoformat()),
            )
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    def list_recent(self, limit: int = 20, include_dismissed: bool = False) -> list[Notification]:
        """Lista notificaciones recientes."""
        dismissed_filter = "" if include_dismissed else "WHERE dismissed = 0"
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, level, title, message, source, dismissed, created_at "
                f"FROM notifications {dismissed_filter} "
                f"ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_notif(r) for r in rows]

    def dismiss(self, notif_id: int) -> bool:
        """Marca una notificación como dismissed."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE notifications SET dismissed = 1 WHERE id = ?",
                (notif_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def dismiss_all(self) -> int:
        """Marca todas las notificaciones como dismissed."""
        with self._lock:
            cur = self._conn.execute("UPDATE notifications SET dismissed = 1 WHERE dismissed = 0")
            self._conn.commit()
            return cur.rowcount

    def count_active(self) -> int:
        """Cantidad de notificaciones sin dismiss."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE dismissed = 0"
            ).fetchone()
        return row[0] if row else 0

    @staticmethod
    def _row_to_notif(row: tuple) -> Notification:
        id_, level, title, message, source, dismissed, created_at = row
        return Notification(
            id=id_, level=level, title=title, message=message,
            source=source, dismissed=bool(dismissed),
            created_at=datetime.fromisoformat(created_at),
        )
