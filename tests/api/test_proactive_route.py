"""Tests para POST /api/proactive/test — disparo de prueba del canal proactivo."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from friday.api.main import AppState, create_app


@pytest.fixture()
def broadcast():
    b = MagicMock()
    b.broadcast_proactive = AsyncMock()
    b.active_connections = 1
    return b


@pytest.fixture()
def client(broadcast):
    state = AppState()
    state.broadcast = broadcast
    return TestClient(create_app(state))


def test_default_payload_speaks(client, broadcast):
    resp = client.post("/api/proactive/test", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    broadcast.broadcast_proactive.assert_awaited_once()
    kwargs = broadcast.broadcast_proactive.await_args.kwargs
    assert kwargs["speak"] is True
    assert kwargs["level"] == "info"
    assert kwargs["message"]  # cae a text cuando message viene vacío


def test_custom_payload_is_forwarded(client, broadcast):
    resp = client.post("/api/proactive/test", json={
        "text": "Custom alert, sir.", "speak": False, "level": "warning",
        "title": "Custom", "message": "body",
    })
    assert resp.status_code == 200
    kwargs = broadcast.broadcast_proactive.await_args.kwargs
    assert kwargs["text"] == "Custom alert, sir."
    assert kwargs["speak"] is False
    assert kwargs["level"] == "warning"
    assert kwargs["message"] == "body"


def test_no_broadcast_returns_error():
    client = TestClient(create_app(AppState()))  # broadcast = None
    resp = client.post("/api/proactive/test", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"
