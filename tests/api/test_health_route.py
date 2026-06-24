"""Tests para GET /api/health — snapshot de autoobservabilidad (Pilar 6)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from friday.api.main import AppState, create_app
from friday.core.health import health_tracker


@pytest.fixture()
def client():
    return TestClient(create_app(AppState()))


def test_health_endpoint_returns_snapshot(client):
    health_tracker.reset()
    health_tracker.record_tool(success=True)
    health_tracker.record_tool(success=False)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_calls"] == 2
    assert data["tool_success_rate"] == 0.5
    assert "avg_latency_ms" in data
