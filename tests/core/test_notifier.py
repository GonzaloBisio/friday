"""Tests para notificaciones proactivas — Notifier y API routes."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from friday.api.main import AppState, create_app
from friday.core.notifier import Notifier, CPU_WARN, CPU_CRIT, GEMINI_COST_DAILY_WARN
from friday.models import MetricPoint
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository
from friday.storage.notification_repo import Notification, NotificationRepository


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def conn():
    c = get_connection(":memory:", check_same_thread=False)
    yield c
    c.close()


@pytest.fixture()
def repo(conn):
    return MetricsRepository(conn)


@pytest.fixture()
def notif_repo(conn):
    return NotificationRepository(conn)


@pytest.fixture()
def broadcast():
    b = MagicMock()
    async def _send(data):
        pass
    b.send_json = _send
    return b


@pytest.fixture()
def notifier(repo, notif_repo, broadcast):
    return Notifier(repo=repo, notif_repo=notif_repo, broadcast=broadcast)


# ── Notifier unit tests ──────────────────────────────────────────────────

class TestNotifierSystem:
    def test_cpu_normal_no_notification(self, notifier, repo):
        repo.save(MetricPoint(
            timestamp=datetime.now(timezone.utc), source="system",
            name="cpu_percent", value=30.0,
        ))
        notifs = notifier.run()
        assert len(notifs) == 0

    def test_cpu_warning_generates_notification(self, notifier, repo):
        repo.save(MetricPoint(
            timestamp=datetime.now(timezone.utc), source="system",
            name="cpu_percent", value=75.0,
        ))
        notifs = notifier.run()
        assert len(notifs) >= 1
        cpu_notifs = [n for n in notifs if "CPU" in n.title]
        assert len(cpu_notifs) == 1
        assert cpu_notifs[0].level == "warning"

    def test_cpu_critical_generates_notification(self, notifier, repo):
        repo.save(MetricPoint(
            timestamp=datetime.now(timezone.utc), source="system",
            name="cpu_percent", value=95.0,
        ))
        notifs = notifier.run()
        cpu_notifs = [n for n in notifs if "CPU" in n.title]
        assert len(cpu_notifs) == 1
        assert cpu_notifs[0].level == "critical"

    def test_no_duplicate_notifications(self, notifier, repo):
        """Si el estado no cambia, no se generan notificaciones repetidas."""
        repo.save(MetricPoint(
            timestamp=datetime.now(timezone.utc), source="system",
            name="cpu_percent", value=95.0,
        ))
        first = notifier.run()
        assert len(first) > 0
        # Segunda ejecución sin cambio → sin notificaciones nuevas
        second = notifier.run()
        assert len(second) == 0

    def test_recovery_notification(self, notifier, repo):
        """Si CPU baja de crítico a normal, genera notificación de recuperación."""
        now = datetime.now(timezone.utc)
        repo.save(MetricPoint(timestamp=now, source="system", name="cpu_percent", value=95.0))
        notifier.run()  # genera critical

        # Ahora baja
        repo.save(MetricPoint(timestamp=now, source="system", name="cpu_percent", value=30.0))
        notifs = notifier.run()
        recovery = [n for n in notifs if "normal" in n.title.lower()]
        assert len(recovery) >= 1

    def test_multiple_metrics_same_run(self, notifier, repo):
        """CPU y RAM ambos en warning."""
        now = datetime.now(timezone.utc)
        repo.save(MetricPoint(timestamp=now, source="system", name="cpu_percent", value=85.0))
        repo.save(MetricPoint(timestamp=now, source="system", name="ram_percent", value=90.0))
        notifs = notifier.run()
        titles = {n.title for n in notifs}
        assert any("CPU" in t for t in titles)
        assert any("RAM" in t for t in titles)


class TestNotifierGemini:
    def test_cost_below_threshold_no_notification(self, notifier, repo):
        now = datetime.now(timezone.utc)
        repo.save(MetricPoint(timestamp=now, source="gemini", name="cost_usd", value=0.10))
        notifs = notifier.run()
        cost_notifs = [n for n in notifs if "Gemini" in n.title or "Costo" in n.title]
        assert len(cost_notifs) == 0

    def test_cost_above_threshold_notification(self, notifier, repo):
        now = datetime.now(timezone.utc)
        repo.save(MetricPoint(timestamp=now, source="gemini", name="cost_usd", value=1.50))
        notifs = notifier.run()
        cost_notifs = [n for n in notifs if "Costo" in n.title]
        assert len(cost_notifs) == 1
        assert cost_notifs[0].level == "warning"


class TestNotifierNexcourt:
    def test_service_down_generates_critical(self, notifier, repo):
        now = datetime.now(timezone.utc)
        repo.save(MetricPoint(
            timestamp=now, source="nexcourt", name="status",
            value=0.0, service="clubs-service", tags={"health": "DOWN"},
        ))
        notifs = notifier.run()
        nex = [n for n in notifs if "NEXCOURT" in n.title]
        assert len(nex) == 1
        assert nex[0].level == "critical"
        assert "clubs-service" in nex[0].title

    def test_service_up_no_notification(self, notifier, repo):
        now = datetime.now(timezone.utc)
        repo.save(MetricPoint(
            timestamp=now, source="nexcourt", name="status",
            value=1.0, service="clubs-service", tags={"health": "UP"},
        ))
        notifs = notifier.run()
        nex = [n for n in notifs if "NEXCOURT" in n.title]
        assert len(nex) == 0


# ── NotificationRepository tests ──────────────────────────────────────────

class TestNotificationRepo:
    def test_save_and_list(self, notif_repo):
        n = Notification(level="warning", title="Test", message="test msg")
        nid = notif_repo.save(n)
        assert nid is not None

        active = notif_repo.list_recent()
        assert len(active) == 1
        assert active[0].level == "warning"

    def test_dismiss_single(self, notif_repo):
        nid = notif_repo.save(Notification(level="info", title="T", message="M"))
        assert notif_repo.count_active() == 1
        notif_repo.dismiss(nid)
        assert notif_repo.count_active() == 0

    def test_dismiss_all(self, notif_repo):
        for i in range(3):
            notif_repo.save(Notification(level="info", title=f"T{i}", message=f"M{i}"))
        assert notif_repo.count_active() == 3
        count = notif_repo.dismiss_all()
        assert count == 3
        assert notif_repo.count_active() == 0

    def test_list_excludes_dismissed(self, notif_repo):
        nid = notif_repo.save(Notification(level="info", title="T", message="M"))
        notif_repo.dismiss(nid)
        assert len(notif_repo.list_recent()) == 0
        assert len(notif_repo.list_recent(include_dismissed=True)) == 1


# ── API notifications route tests ────────────────────────────────────────

@pytest.fixture()
def api_state(notif_repo):
    s = AppState()
    s.notif_repo = notif_repo
    return s


@pytest.fixture()
def api_client(api_state):
    app = create_app(api_state)
    return TestClient(app)


class TestNotificationsAPI:
    def test_list_empty(self, api_client):
        resp = api_client.get("/api/notifications")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_notifications(self, api_client, notif_repo):
        notif_repo.save(Notification(level="warning", title="CPU alta", message="CPU al 85%"))
        notif_repo.save(Notification(level="critical", title="NEXCOURT caído", message="clubs-service down"))

        resp = api_client.get("/api/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["level"] == "critical"  # más reciente primero

    def test_dismiss_one(self, api_client, notif_repo):
        nid = notif_repo.save(Notification(level="info", title="T", message="M"))
        resp = api_client.post("/api/notifications/dismiss", json={"id": nid})
        assert resp.status_code == 200
        assert notif_repo.count_active() == 0

    def test_dismiss_all(self, api_client, notif_repo):
        for i in range(2):
            notif_repo.save(Notification(level="info", title=f"T{i}", message=f"M{i}"))
        resp = api_client.post("/api/notifications/dismiss", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["dismissed_count"] == 2
