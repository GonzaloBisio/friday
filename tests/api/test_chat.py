"""Tests para ruta de chat de la API — incluye modelo adaptativo y sesiones."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from friday.api.main import AppState, create_app
from friday.core.brain import ChatResult


@pytest.fixture()
def brain():
    b = MagicMock()
    b.chat.return_value = ChatResult(
        text="Hola, soy FRIDAY",
        model="gemini-2.5-flash",
        tokens_in=10,
        tokens_out=5,
    )
    b._model = "gemini-2.5-flash"
    b.session_id = "test-session-123"
    b._chat_repo = MagicMock()
    b._chat_repo.list_sessions.return_value = [
        {"id": "abc", "title": "", "created_at": "2026-01-01T00:00:00"},
    ]
    return b


@pytest.fixture()
def broadcast():
    b = MagicMock()
    async def _send(data):
        pass
    b.send_json = _send
    return b


@pytest.fixture()
def state(brain, broadcast):
    s = AppState()
    s.brain = brain
    s.broadcast = broadcast
    return s


@pytest.fixture()
def client(state):
    app = create_app(state)
    return TestClient(app)


class TestChatRoute:
    def test_valid_message_returns_response(self, client, brain):
        resp = client.post("/api/chat", json={"message": "Hola"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Hola, soy FRIDAY"
        assert data["model"] == "gemini-2.5-flash"
        assert data["session_id"] == "test-session-123"

    def test_model_parameter_is_passed(self, client, brain):
        resp = client.post("/api/chat", json={"message": "Hola", "model": "pro"})
        assert resp.status_code == 200
        brain.chat.assert_called_once_with("Hola", "pro")

    def test_empty_message_rejected(self, client):
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 422

    def test_no_brain_returns_fallback(self, state):
        state.brain = None
        app = create_app(state)
        client = TestClient(app)
        resp = client.post("/api/chat", json={"message": "Hola"})
        assert resp.status_code == 200
        data = resp.json()
        assert "GEMINI_API_KEY" in data["response"]
        assert data["model"] == "none"

    def test_missing_field_rejected(self, client):
        resp = client.post("/api/chat", json={})
        assert resp.status_code == 422

    def test_invalid_model_rejected(self, client):
        resp = client.post("/api/chat", json={"message": "x", "model": "invalid"})
        assert resp.status_code == 422


class TestChatSessions:
    def test_list_sessions(self, client):
        resp = client.get("/api/chat/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "abc"

    def test_switch_session(self, client, brain):
        resp = client.post("/api/chat/sessions/switch", json={"session_id": "other-session"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        brain.switch_session.assert_called_once_with("other-session")
