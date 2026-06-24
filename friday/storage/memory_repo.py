"""Repositorio de memoria de FRIDAY — hechos y preferencias que recuerda de Gonzalo.

A diferencia de reentrenar el modelo, lo que FRIDAY "aprende" vive ACÁ, en SQLite:
inspeccionable y borrable. Se inyecta al contexto del prompt en cada turno (ver
OllamaBrain._memory_block). Es la base de la capa de aprendizaje (Fase A, explícita).
"""

from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Memory:
    """Una cosa que FRIDAY recuerda de Gonzalo."""
    key: str
    value: str
    kind: str = "fact"            # 'fact' | 'preference'
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: int | None = None


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, max_len: int = 40) -> str:
    s = _SLUG_RE.sub("_", text.strip().lower()).strip("_")
    return s[:max_len] or "memo"


class MemoryRepository:
    """Acceso a la tabla `memories`. Mismo patrón conn+lock que los otros repos."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock | None = None) -> None:
        self._conn = conn
        self._lock = lock or threading.RLock()

    def remember(self, value: str, key: str | None = None, kind: str = "fact") -> Memory:
        """Guarda (o actualiza) una memoria. Upsert por `key`.

        Si `key` viene vacío, se deriva del contenido + un sufijo único → cada hecho
        nuevo se ACUMULA. Si se pasa una `key` estable (ej. "cafe"), volver a llamar
        con esa key ACTUALIZA el valor (una preferencia que evoluciona, sin duplicar).
        """
        value = value.strip()
        if key and key.strip():
            final_key = _slug(key)
        else:
            final_key = f"{_slug(value)}-{uuid.uuid4().hex[:6]}"
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """INSERT INTO memories (kind, key, value, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                     value=excluded.value, kind=excluded.kind, updated_at=excluded.updated_at""",
                (kind, final_key, value, now, now),
            )
            self._conn.commit()
        return Memory(key=final_key, value=value, kind=kind)

    def forget(self, term: str) -> int:
        """Borra las memorias cuyo `value` o `key` contengan `term`. Devuelve cuántas.

        Pensado para uso por voz: "olvidá lo del café" → borra lo que matchee "café".
        """
        like = f"%{term.strip()}%"
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memories WHERE value LIKE ? OR key LIKE ?",
                (like, like),
            )
            self._conn.commit()
            return cur.rowcount

    def all(self, limit: int = 200) -> list[Memory]:
        """Todas las memorias, más recientes primero."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, kind, key, value, created_at, updated_at
                   FROM memories ORDER BY updated_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return row[0] if row else 0

    @staticmethod
    def _row(r: tuple) -> Memory:
        id_, kind, key, value, created, updated = r
        return Memory(
            id=id_, kind=kind, key=key, value=value,
            created_at=datetime.fromisoformat(created),
            updated_at=datetime.fromisoformat(updated),
        )
