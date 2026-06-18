"""Repositorio de conversaciones — guardar y cargar historial de chat en SQLite."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence


@dataclass
class ChatMessage:
    """Un mensaje en una conversación."""
    session_id: str
    role: str           # "user", "assistant", "system"
    content: str
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: int | None = None


class ChatRepository:
    """Acceso a las tablas chat_sessions y chat_messages."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── Sesiones ─────────────────────────────────────────────────────────

    def create_session(self, title: str = "") -> str:
        """Crea una nueva sesión y devuelve su ID."""
        session_id = uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO chat_sessions (id, title, created_at) VALUES (?, ?, ?)",
            (session_id, title, now),
        )
        self._conn.commit()
        return session_id

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """Lista sesiones recientes."""
        rows = self._conn.execute(
            "SELECT id, title, created_at FROM chat_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"id": r[0], "title": r[1], "created_at": r[2]}
            for r in rows
        ]

    # ── Mensajes ─────────────────────────────────────────────────────────

    def save_message(self, msg: ChatMessage) -> int:
        """Guarda un mensaje y devuelve su id."""
        cur = self._conn.execute(
            """INSERT INTO chat_messages
               (session_id, role, content, model, tokens_in, tokens_out, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.session_id, msg.role, msg.content,
                msg.model, msg.tokens_in, msg.tokens_out,
                msg.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def save_messages(self, messages: Sequence[ChatMessage]) -> int:
        """Guarda múltiples mensajes en batch."""
        rows = [
            (m.session_id, m.role, m.content, m.model,
             m.tokens_in, m.tokens_out, m.created_at.isoformat())
            for m in messages
        ]
        self._conn.executemany(
            """INSERT INTO chat_messages
               (session_id, role, content, model, tokens_in, tokens_out, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def load_session(self, session_id: str, limit: int = 200) -> list[ChatMessage]:
        """Carga los mensajes de una sesión, ordenados por fecha."""
        rows = self._conn.execute(
            """SELECT id, session_id, role, content, model, tokens_in, tokens_out, created_at
               FROM chat_messages
               WHERE session_id = ?
               ORDER BY created_at ASC
               LIMIT ?""",
            (session_id, limit),
        ).fetchall()
        return [self._row_to_msg(r) for r in rows]

    def count_messages(self, session_id: str) -> int:
        """Cantidad de mensajes en una sesión."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row[0] if row else 0

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_msg(row: tuple) -> ChatMessage:
        id_, sid, role, content, model, tin, tout, created_at = row
        return ChatMessage(
            id=id_,
            session_id=sid,
            role=role,
            content=content,
            model=model,
            tokens_in=tin,
            tokens_out=tout,
            created_at=datetime.fromisoformat(created_at),
        )
