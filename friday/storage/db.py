"""Conexión SQLite y migración de esquema para FRIDAY."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_VERSION = 1

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


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Abre (o crea) la DB y aplica migraciones pendientes."""
    conn = sqlite3.connect(str(db_path))
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
            (str(_SCHEMA_VERSION),),
        )
        conn.commit()
