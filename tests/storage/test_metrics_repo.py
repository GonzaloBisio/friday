"""Tests para friday.storage.metrics_repo — guardar y consultar métricas."""

from datetime import datetime, timedelta, timezone

import pytest

from friday.models import MetricPoint
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository


@pytest.fixture()
def repo(tmp_path):
    conn = get_connection(str(tmp_path / "test.db"))
    yield MetricsRepository(conn)
    conn.close()


def _make_point(
    source: str = "system",
    name: str = "cpu_percent",
    value: float = 55.0,
    ts: datetime | None = None,
    service: str | None = None,
    unit: str | None = "%",
    tags: dict | None = None,
) -> MetricPoint:
    return MetricPoint(
        timestamp=ts or MetricPoint.utcnow(),
        source=source,
        name=name,
        value=value,
        service=service,
        unit=unit,
        tags=tags,
    )


class TestSave:
    def test_save_returns_id(self, repo):
        point = _make_point()
        row_id = repo.save(point)
        assert isinstance(row_id, int)
        assert row_id >= 1

    def test_save_persists_all_fields(self, repo):
        point = _make_point(
            source="gemini",
            name="tokens_out",
            value=1234.0,
            unit="tokens",
            service="brain",
            tags={"model": "gemini-2.5-pro"},
        )
        repo.save(point)
        result = repo.query(source="gemini", name="tokens_out")
        assert len(result) == 1
        p = result[0]
        assert p.source == "gemini"
        assert p.name == "tokens_out"
        assert p.value == 1234.0
        assert p.unit == "tokens"
        assert p.service == "brain"
        assert p.tags == {"model": "gemini-2.5-pro"}

    def test_save_rejects_empty_source(self, repo):
        point = _make_point(source="")
        with pytest.raises(ValueError, match="source"):
            repo.save(point)

    def test_save_rejects_empty_name(self, repo):
        point = _make_point(name="")
        with pytest.raises(ValueError, match="name"):
            repo.save(point)


class TestSaveMany:
    def test_save_many_inserts_all(self, repo):
        points = [_make_point(value=float(i)) for i in range(5)]
        count = repo.save_many(points)
        assert count == 5
        assert len(repo.query(source="system")) == 5

    def test_save_many_empty_list(self, repo):
        count = repo.save_many([])
        assert count == 0


class TestQuery:
    def test_query_empty_db(self, repo):
        result = repo.query()
        assert result == []

    def test_query_filter_by_source(self, repo):
        repo.save(_make_point(source="system", name="cpu"))
        repo.save(_make_point(source="gemini", name="tokens"))
        result = repo.query(source="system")
        assert len(result) == 1
        assert result[0].source == "system"

    def test_query_filter_by_time_range(self, repo):
        now = MetricPoint.utcnow()
        old = now - timedelta(hours=2)
        recent = now - timedelta(minutes=5)

        repo.save(_make_point(ts=old, value=1.0))
        repo.save(_make_point(ts=recent, value=2.0))
        repo.save(_make_point(ts=now, value=3.0))

        # Solo las del rango último hora
        start = now - timedelta(hours=1)
        result = repo.query(start=start)
        assert len(result) == 2
        values = {p.value for p in result}
        assert values == {2.0, 3.0}

    def test_query_filter_by_service(self, repo):
        repo.save(_make_point(source="nexcourt", service="clubs-service", name="status"))
        repo.save(_make_point(source="nexcourt", service="users-service", name="status"))
        result = repo.query(service="clubs-service")
        assert len(result) == 1
        assert result[0].service == "clubs-service"

    def test_query_respects_limit(self, repo):
        for i in range(10):
            repo.save(_make_point(value=float(i)))
        result = repo.query(limit=3)
        assert len(result) == 3

    def test_query_ordered_by_ts_desc(self, repo):
        now = MetricPoint.utcnow()
        for i in range(3):
            repo.save(_make_point(ts=now - timedelta(minutes=i), value=float(i)))
        result = repo.query()
        # El más reciente primero (value=0 tiene ts=now)
        assert result[0].value == 0.0
        assert result[-1].value == 2.0


class TestLatest:
    def test_latest_returns_most_recent(self, repo):
        now = MetricPoint.utcnow()
        repo.save(_make_point(ts=now - timedelta(minutes=5), value=10.0))
        repo.save(_make_point(ts=now, value=20.0))
        latest = repo.latest("system", "cpu_percent")
        assert latest is not None
        assert latest.value == 20.0

    def test_latest_returns_none_when_empty(self, repo):
        result = repo.latest("system", "cpu_percent")
        assert result is None

    def test_latest_scoped_to_source_and_name(self, repo):
        now = MetricPoint.utcnow()
        repo.save(_make_point(source="system", name="cpu_percent", ts=now, value=50.0))
        repo.save(_make_point(source="gemini", name="tokens_in", ts=now, value=999.0))
        result = repo.latest("gemini", "tokens_in")
        assert result is not None
        assert result.value == 999.0
        assert result.source == "gemini"


class TestTagsSerialization:
    def test_tags_roundtrip(self, repo):
        tags = {"region": "us-east-1", "status": "UP", "count": 42}
        repo.save(_make_point(tags=tags))
        result = repo.query()
        assert result[0].tags == tags

    def test_null_tags(self, repo):
        repo.save(_make_point(tags=None))
        result = repo.query()
        assert result[0].tags is None
