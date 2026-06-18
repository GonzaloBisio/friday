"""Tests para rutas de status y métricas de la API."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from friday.api.main import AppState, create_app
from friday.models import MetricPoint


def _make_point(source, name, value, service=None, hours_ago=0):
    ts = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    return MetricPoint(
        timestamp=ts,
        source=source, name=name, value=value,
        service=service, unit="test",
    )


@pytest.fixture()
def repo():
    r = MagicMock()
    r.latest.return_value = None
    r.query.return_value = []
    return r


@pytest.fixture()
def state(repo):
    s = AppState()
    s.repo = repo
    return s


@pytest.fixture()
def client(state):
    app = create_app(state)
    return TestClient(app)


class TestStatusRoute:
    def test_returns_200_with_structure(self, client, repo):
        repo.latest.return_value = _make_point("system", "cpu_percent", 42.0)
        repo.query.return_value = []

        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data
        assert data["system"]["cpu_percent"] == 42.0
        assert "gemini" in data
        assert "nexcourt" in data
        assert "services" in data

    def test_no_repo_returns_503(self, state):
        state.repo = None
        app = create_app(state)
        client = TestClient(app)
        resp = client.get("/api/status")
        assert resp.status_code == 503

    def test_null_metrics_return_none(self, client, repo):
        repo.latest.return_value = None
        repo.query.return_value = []

        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["system"]["cpu_percent"] is None
        assert data["gemini"]["cost_usd"] is None


class TestMetricsRoute:
    def test_returns_200_with_filters(self, client, repo):
        p1 = _make_point("system", "cpu_percent", 10.0)
        p2 = _make_point("system", "cpu_percent", 20.0)
        repo.query.return_value = [p1, p2]

        resp = client.get("/api/metrics?source=system&name=cpu_percent&hours=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["points"]) == 2

    def test_no_repo_returns_503(self, state):
        state.repo = None
        app = create_app(state)
        client = TestClient(app)
        resp = client.get("/api/metrics")
        assert resp.status_code == 503

    def test_empty_metrics_returns_empty_list(self, client, repo):
        repo.query.return_value = []
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["points"] == []

    def test_default_params(self, client, repo):
        repo.query.return_value = []
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        # Verifica que llamó con los defaults
        repo.query.assert_called_once()
        call_kwargs = repo.query.call_args.kwargs
        assert call_kwargs["limit"] == 1000
