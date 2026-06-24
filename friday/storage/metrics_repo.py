"""Repositorio de métricas — guardar y consultar MetricPoints en SQLite."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from typing import Sequence

from friday.models import MetricPoint


class MetricsRepository:
    """Acceso a la tabla `metrics` de SQLite.

    La conexión se comparte entre varios collectors que corren en threads
    distintos (APScheduler). sqlite3 con ``check_same_thread=False`` permite
    usar la conexión desde otros threads, pero **no es safe para uso
    concurrente**: dos ``executemany``+``commit`` solapados revientan con
    ``InterfaceError: bad parameter or other API misuse``. El lock serializa
    el acceso (un thread a la vez sobre la conexión). En producción se pasa
    un lock **compartido** entre todos los repos que usan la misma conexión.
    """

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock | None = None) -> None:
        self._conn = conn
        self._lock = lock or threading.RLock()

    # ---- Escritura ----

    def save(self, point: MetricPoint) -> int:
        """Inserta un MetricPoint y devuelve su id."""
        if not point.source:
            raise ValueError("MetricPoint.source no puede estar vacío")
        if not point.name:
            raise ValueError("MetricPoint.name no puede estar vacío")

        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO metrics (ts, source, service, name, value, unit, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    point.timestamp.isoformat(),
                    point.source,
                    point.service,
                    point.name,
                    point.value,
                    point.unit,
                    point.tags_json(),
                ),
            )
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    def save_many(self, points: Sequence[MetricPoint]) -> int:
        """Inserta múltiples puntos en una sola transacción. Devuelve la cantidad insertada."""
        rows = [
            (
                p.timestamp.isoformat(),
                p.source,
                p.service,
                p.name,
                p.value,
                p.unit,
                p.tags_json(),
            )
            for p in points
        ]
        # Lock cubre executemany + commit juntos: si se suelta entre los dos,
        # otro thread puede intercalar su escritura y corromper la conexión.
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO metrics (ts, source, service, name, value, unit, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            self._conn.commit()
            return len(rows)

    # ---- Lectura ----

    def query(
        self,
        source: str | None = None,
        name: str | None = None,
        service: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[MetricPoint]:
        """Consulta métricas con filtros opcionales, ordenadas por timestamp desc."""
        clauses: list[str] = []
        params: list[object] = []

        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if name is not None:
            clauses.append("name = ?")
            params.append(name)
        if service is not None:
            clauses.append("service = ?")
            params.append(service)
        if start is not None:
            clauses.append("ts >= ?")
            params.append(start.isoformat())
        if end is not None:
            clauses.append("ts <= ?")
            params.append(end.isoformat())

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT ts, source, service, name, value, unit, tags_json FROM metrics WHERE {where} ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_point(r) for r in rows]

    def latest(self, source: str, name: str) -> MetricPoint | None:
        """Devuelve el punto más reciente para un source+name, o None."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT ts, source, service, name, value, unit, tags_json
                FROM metrics
                WHERE source = ? AND name = ?
                ORDER BY ts DESC LIMIT 1
                """,
                (source, name),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_point(row)

    # ---- Helpers ----

    @staticmethod
    def _row_to_point(row: tuple) -> MetricPoint:
        ts_str, source, service, name, value, unit, tags_json = row
        return MetricPoint(
            timestamp=datetime.fromisoformat(ts_str),
            source=source,
            service=service,
            name=name,
            value=value,
            unit=unit,
            tags=MetricPoint.tags_from_json(tags_json),
        )
