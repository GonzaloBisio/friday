"""Tests para friday.agent.permissions — PermissionGate."""

import pytest

from friday.agent.registry import ActionRegistry, RiskLevel
from friday.agent.permissions import PermissionGate


def _echo(**kwargs):
    return kwargs


def _failing(**kwargs):
    raise RuntimeError("boom")


@pytest.fixture()
def gate():
    reg = ActionRegistry()
    reg.register("safe_action", "acción segura", RiskLevel.LOW, _echo)
    reg.register("risky_action", "acción riesgosa", RiskLevel.MEDIUM, _echo)
    reg.register("dangerous_action", "acción peligrosa", RiskLevel.HIGH, _echo)
    reg.register("broken_action", "acción que falla", RiskLevel.LOW, _failing)
    return PermissionGate(reg)


class TestPermissionGateLow:
    def test_low_risk_executes_immediately(self, gate):
        result = gate.request("safe_action", {"x": 1})
        assert result["status"] == "ok"
        assert result["result"] == {"x": 1}

    def test_low_risk_error_returns_error(self, gate):
        result = gate.request("broken_action", {})
        assert result["status"] == "error"
        assert "boom" in result["reason"]


class TestPermissionGateMediumHigh:
    def test_medium_risk_returns_pending(self, gate):
        result = gate.request("risky_action", {"app": "notepad"})
        assert result["status"] == "pending_confirmation"
        assert "action_id" in result
        assert result["risk"] == "medium"

    def test_high_risk_returns_pending(self, gate):
        result = gate.request("dangerous_action", {"cmd": "rm"})
        assert result["status"] == "pending_confirmation"
        assert result["risk"] == "high"

    def test_confirm_approved_executes(self, gate):
        pending = gate.request("risky_action", {"data": "test"})
        action_id = pending["action_id"]
        result = gate.confirm(action_id, approved=True)
        assert result["status"] == "ok"
        assert result["result"] == {"data": "test"}

    def test_confirm_denied_rejects(self, gate):
        pending = gate.request("risky_action", {"data": "test"})
        action_id = pending["action_id"]
        result = gate.confirm(action_id, approved=False)
        assert result["status"] == "denied"

    def test_confirm_unknown_id_errors(self, gate):
        result = gate.confirm("fakeid123", approved=True)
        assert result["status"] == "error"
        assert "no hay acción pendiente" in result["reason"].lower()


class TestPermissionGateAllowlist:
    def test_unknown_action_rejected(self, gate):
        result = gate.request("format_c_drive", {})
        assert result["status"] == "rejected"
        assert "allowlist" in result["reason"]

    def test_pending_actions_list(self, gate):
        gate.request("risky_action", {"a": 1})
        gate.request("dangerous_action", {"b": 2})
        assert len(gate.pending_actions) == 2

    def test_confirmed_action_removed_from_pending(self, gate):
        pending = gate.request("risky_action", {})
        gate.confirm(pending["action_id"], approved=True)
        assert len(gate.pending_actions) == 0
