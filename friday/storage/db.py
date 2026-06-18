"""Conexión SQLite y migración de esquema para FRIDAY."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_VERSION = 3

_CREATE_METRICS = """
CREATE TABLE IF NOT EXISTS metrics (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,   -- ISO-8601 UTC
    source  TEXT    NOT NULL,
    service TEXT,
    name    TEXT    NOT NULL,
    value   REAL    NOT NULL,
    unit    TEXT,
    tags_json TEXT
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_metrics_source_name_ts
ON metrics (source, name, ts);
"""

_CREATE_META = """
CREATE TABLE IF NOT EXISTS _meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_CREATE_CHAT_SESSIONS = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

_CREATE_CHAT_MESSAGES = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id),
    role       TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content    TEXT NOT NULL,
    model      TEXT,
    tokens_in  INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

_CREATE_CHAT_INDEX = """
CREATE INDEX IF NOT EXISTS idx_chat_messages_session
ON chat_messages (session_id, created_at);
"""

_CREATE_NOTIFICATIONS = """
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    level      TEXT NOT NULL CHECK(level IN ('info', 'warning', 'critical')),
    title      TEXT NOT NULL,
    message    TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'system',
    dismissed  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

_CREATE_NOTIFICATIONS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_notifications_created
ON notifications (created_at DESC);
"""


def get_connection(db_path: str | Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Abre (o crea) la DB y aplica migraciones pendientes."""
    conn = sqlite3.connect(str(db_path), check_same_thread=check_same_thread)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Aplica migraciones incrementales basadas en schema_version."""
    conn.execute(_CREATE_META)
    conn.commit()

    row = conn.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
    current = int(row[0]) if row else 0

    if current < 1:
        conn.execute(_CREATE_METRICS)
        conn.execute(_CREATE_INDEX)
        conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('schema_version', ?)",
            (str(1),),
        )
        conn.commit()

    if current < 2:
        conn.execute(_CREATE_CHAT_SESSIONS)
        conn.execute(_CREATE_CHAT_MESSAGES)
        conn.execute(_CREATE_CHAT_INDEX)
        conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('schema_version', ?)",
            (str(2),),
        )
        conn.commit()

    if current < 3:
        conn.execute(_CREATE_NOTIFICATIONS)
        conn.execute(_CREATE_NOTIFICATIONS_INDEX)
        conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('schema_version', ?)",
            (str(3),),
        )
        conn.commit()
