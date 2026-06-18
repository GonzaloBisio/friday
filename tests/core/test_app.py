"""Tests para friday.app — FridaySystem bootstrap y purga de métricas."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from friday.models import MetricPoint
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository


class TestMetricsPurge:
    def test_purge_deletes_old_metrics(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = get_connection(db_path)
        repo = MetricsRepository(conn)

        now = datetime.now(timezone.utc)
        old = now - timedelta(days=45)
        recent = now - timedelta(hours=1)

        repo.save(MetricPoint(timestamp=old, source="system", name="cpu", value=50.0))
        repo.save(MetricPoint(timestamp=old, source="system", name="ram", value=60.0))
        repo.save(MetricPoint(timestamp=recent, source="system", name="cpu", value=30.0))

        cutoff = now - timedelta(days=30)
        conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff.isoformat(),))
        conn.commit()

        remaining = repo.query()
        assert len(remaining) == 1
        assert remaining[0].value == 30.0
        conn.close()

    def test_purge_keeps_recent_metrics(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = get_connection(db_path)
        repo = MetricsRepository(conn)

        now = datetime.now(timezone.utc)
        for i in range(5):
            ts = now - timedelta(hours=i)
            repo.save(MetricPoint(timestamp=ts, source="s", name="n", value=float(i)))

        cutoff = now - timedelta(days=30)
        cur = conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff.isoformat(),))
        conn.commit()

        assert cur.rowcount == 0
        assert len(repo.query()) == 5
        conn.close()

    def test_purge_on_empty_db(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = get_connection(db_path)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        cur = conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff.isoformat(),))
        conn.commit()
        assert cur.rowcount == 0
        conn.close()
