"""Tests para friday.storage.db — conexión y migraciones."""

import sqlite3

import pytest

from friday.storage.db import get_connection


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test.db")


class TestGetConnection:
    def test_creates_database_and_tables(self, db_path):
        conn = get_connection(db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "metrics" in tables
        assert "_meta" in tables
        conn.close()

    def test_schema_version_is_set(self, db_path):
        conn = get_connection(db_path)
        row = conn.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
        assert row is not None
        assert int(row[0]) == 1
        conn.close()

    def test_idempotent_migration(self, db_path):
        """Llamar get_connection dos veces no rompe nada."""
        conn1 = get_connection(db_path)
        conn1.close()
        conn2 = get_connection(db_path)
        row = conn2.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
        assert int(row[0]) == 1
        conn2.close()

    def test_index_exists(self, db_path):
        conn = get_connection(db_path)
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_metrics_source_name_ts" in indexes
        conn.close()
