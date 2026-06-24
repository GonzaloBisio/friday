"""Tests para GET / — el dashboard JARVIS (Pilar 4)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from friday.api.main import AppState, create_app


def test_root_serves_command_center():
    client = TestClient(create_app(AppState()))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "FRIDAY" in body
    assert "COMMAND CENTER" in body
    # Confirma que es el HUD vivo, no un placeholder: trae la lógica de WS y los endpoints.
    assert "/ws/live" in body
    assert "/api/health" in body


def test_index_file_exists():
    index = Path("friday/dashboard_web/index.html")
    assert index.exists(), "el index.html del dashboard debe existir en el repo"
