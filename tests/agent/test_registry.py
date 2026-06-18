"""Tests para friday.agent.registry — ActionRegistry y allowlist."""

import pytest

from friday.agent.registry import ActionRegistry, RiskLevel


def _noop(**kwargs):
    return "ok"


@pytest.fixture()
def registry():
    reg = ActionRegistry()
    reg.register("test_low", "acción de prueba low", RiskLevel.LOW, _noop)
    reg.register("test_medium", "acción de prueba medium", RiskLevel.MEDIUM, _noop)
    reg.register("test_high", "acción de prueba high", RiskLevel.HIGH, _noop)
    return reg


class TestActionRegistry:
    def test_register_and_get(self, registry):
        spec = registry.get("test_low")
        assert spec is not None
        assert spec.name == "test_low"
        assert spec.risk == RiskLevel.LOW

    def test_is_allowed_registered(self, registry):
        assert registry.is_allowed("test_low")
        assert registry.is_allowed("test_medium")

    def test_is_not_allowed_unregistered(self, registry):
        assert not registry.is_allowed("borrar_todo")
        assert not registry.is_allowed("format_c")

    def test_get_unknown_returns_none(self, registry):
        assert registry.get("inexistente") is None

    def test_catalog_returns_all(self, registry):
        assert len(registry.catalog) == 3

    def test_actions_by_risk(self, registry):
        low = registry.actions_by_risk(RiskLevel.LOW)
        assert len(low) == 1
        assert low[0].name == "test_low"

    def test_contains(self, registry):
        assert "test_low" in registry
        assert "malware" not in registry

    def test_len(self, registry):
        assert len(registry) == 3
