"""Tests para /api/nexcourt/auth y /api/nexcourt/login."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from friday.api.main import AppState, create_app


def _client(collector):
    state = AppState()
    state.nexcourt_collector = collector
    return TestClient(create_app(state))


def test_auth_reports_needs_login():
    col = MagicMock()
    col.needs_login = True
    resp = _client(col).get("/api/nexcourt/auth")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["needs_login"] is True


def test_auth_no_collector():
    resp = _client(None).get("/api/nexcourt/auth")
    assert resp.json() == {"available": False, "needs_login": False}


def test_login_spawns_command_and_resets():
    col = MagicMock()
    with patch("friday.api.routes_nexcourt.subprocess.Popen") as popen:
        resp = _client(col).post("/api/nexcourt/login")
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"
    popen.assert_called_once()           # lanzó el comando de login
    col.reset_auth.assert_called_once()  # y reseteó el cooldown del collector


def test_login_handles_spawn_failure():
    col = MagicMock()
    with patch("friday.api.routes_nexcourt.subprocess.Popen", side_effect=FileNotFoundError("no aws")):
        resp = _client(col).post("/api/nexcourt/login")
    assert resp.json()["status"] == "error"
    col.reset_auth.assert_not_called()
