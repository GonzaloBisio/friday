"""Tests para rutas del agente de PC."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from friday.agent.permissions import PermissionGate
from friday.agent.registry import ActionRegistry, ActionSpec, RiskLevel
from friday.api.main import AppState, create_app


def _dummy_action():
    return "ok"


@pytest.fixture()
def gate():
    reg = ActionRegistry()
    reg.register("test_low", "Low risk action", RiskLevel.LOW, _dummy_action)
    reg.register("test_med", "Medium risk action", RiskLevel.MEDIUM, _dummy_action)
    return PermissionGate(reg)


@pytest.fixture()
def state(gate):
    s = AppState()
    s.gate = gate
    return s


@pytest.fixture()
def client(state):
    app = create_app(state)
    return TestClient(app)


class TestAgentTools:
    def test_list_tools_returns_catalog(self, client):
        resp = client.get("/api/agent/tools")
        assert resp.status_code == 200
        tools = resp.json()
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert "test_low" in names
        assert "test_med" in names
        assert tools[0]["risk"] in ("low", "medium")

    def test_list_tools_no_gate_returns_empty(self, state):
        state.gate = None
        app = create_app(state)
        client = TestClient(app)
        resp = client.get("/api/agent/tools")
        assert resp.status_code == 200
        assert resp.json() == []


class TestAgentRun:
    def test_run_low_risk_executes_immediately(self, client):
        resp = client.post("/api/agent/run", json={
            "tool": "test_low",
            "args": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_run_medium_risk_returns_pending(self, client):
        resp = client.post("/api/agent/run", json={
            "tool": "test_med",
            "args": {"x": 1},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending_confirmation"
        assert "action_id" in data

    def test_run_unknown_tool_returns_rejected(self, client):
        resp = client.post("/api/agent/run", json={
            "tool": "nonexistent",
            "args": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"

    def test_run_no_gate_returns_error(self, state):
        state.gate = None
        app = create_app(state)
        client = TestClient(app)
        resp = client.post("/api/agent/run", json={
            "tool": "test_low",
            "args": {},
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"


class TestAgentConfirm:
    def test_confirm_approved_executes(self, client, gate):
        # Primero creamos una acción pendiente
        gate.request("test_med", {})
        pending = gate.pending_actions
        assert len(pending) == 1
        action_id = pending[0].action_id

        resp = client.post("/api/agent/confirm", json={
            "action_id": action_id,
            "approved": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_confirm_denied_returns_denied(self, client, gate):
        gate.request("test_med", {})
        action_id = gate.pending_actions[0].action_id

        resp = client.post("/api/agent/confirm", json={
            "action_id": action_id,
            "approved": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "denied"

    def test_confirm_unknown_id_returns_error(self, client):
        resp = client.post("/api/agent/confirm", json={
            "action_id": "nonexistent",
            "approved": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
