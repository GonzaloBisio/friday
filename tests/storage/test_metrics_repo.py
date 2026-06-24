"""Tests para friday.storage.metrics_repo — guardar y consultar métricas."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from friday.models import MetricPoint
from friday.storage.chat_repo import ChatMessage, ChatRepository
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


# ── Concurrencia (fix del InterfaceError en producción) ────────────────────
# Reproduce el bug real: APScheduler dispara varios collectors a la vez sobre
# la MISMA conexión (check_same_thread=False). Sin lock, dos executemany+commit
# solapados revientan con sqlite3.InterfaceError. El lock compartido lo serializa.


@pytest.fixture()
def shared_conn(tmp_path):
    """Conexión como en producción: check_same_thread=False + WAL."""
    conn = get_connection(str(tmp_path / "shared.db"), check_same_thread=False)
    yield conn
    conn.close()


class TestConcurrency:
    def test_concurrent_save_many_no_interface_error(self, shared_conn):
        """N threads haciendo save_many a la vez sobre la misma conexión."""
        lock = threading.RLock()
        repo = MetricsRepository(shared_conn, lock=lock)
        n_threads = 8
        per_thread = 50
        errors: list[Exception] = []

        def worker(tid: int) -> None:
            try:
                for i in range(per_thread):
                    pts = [_make_point(
                        source=f"src_{tid}",
                        name=f"m_{i}",
                        value=float(i),
                    )]
                    repo.save_many(pts)
            except Exception as exc:  # noqa: BLE001 — queremos cazar TODO
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            list(pool.map(worker, range(n_threads)))

        assert errors == [], f"Hubo errores de concurrencia: {errors}"
        # Todos los puntos se guardaron.
        assert len(repo.query(limit=10000)) == n_threads * per_thread

    def test_concurrent_save_and_query_no_error(self, shared_conn):
        """Escritores + lectores concurrentes (el dashboard lee mientras los
        collectors escriben) — sin el lock, la conexión se corrompe."""
        lock = threading.RLock()
        repo = MetricsRepository(shared_conn, lock=lock)
        # Sembrar algo de datos para que las lecturas no estén vacías.
        repo.save_many([_make_point(value=0.0)])
        errors: list[Exception] = []
        stop = threading.Event()

        def writer() -> None:
            i = 0
            try:
                while not stop.is_set():
                    repo.save_many([_make_point(value=float(i))])
                    i += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(50):
                    repo.query(limit=100)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        # Dejar correr un rato y parar.
        threading.Event().wait(0.2)
        stop.set()
        for t in threads:
            t.join(timeout=5)

        assert errors == [], f"Errores: {errors}"

    def test_shared_lock_serializes_across_repos(self, shared_conn):
        """El lock es COMPARTIDO entre metrics y chat repo (como los cablea
        app.py) — sin eso, un collector y un mensaje de chat se pisan."""
        lock = threading.RLock()
        metrics = MetricsRepository(shared_conn, lock=lock)
        chat = ChatRepository(shared_conn, lock=lock)
        # Sembrar una sesión de chat.
        sid = chat.create_session("test")
        errors: list[Exception] = []

        def metric_writer() -> None:
            try:
                for i in range(30):
                    metrics.save_many([_make_point(value=float(i))])
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def chat_writer() -> None:
            try:
                for i in range(30):
                    chat.save_message(ChatMessage(
                        session_id=sid, role="user", content=f"msg {i}",
                    ))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=metric_writer)
        t2 = threading.Thread(target=chat_writer)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert errors == [], f"Errores cross-repo: {errors}"
        assert len(metrics.query(limit=10000)) == 30
        assert chat.count_messages(sid) == 30

    def test_lock_can_be_none_for_single_thread_compat(self, tmp_path):
        """Sin lock explícito, el repo crea uno propio — retrocompatible con
        los tests existentes que no pasan lock."""
        conn = get_connection(str(tmp_path / "st.db"))
        repo = MetricsRepository(conn)  # lock=None → crea su propio RLock
        repo.save(_make_point())
        assert len(repo.query()) == 1
        conn.close()
