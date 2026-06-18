"""Tests para friday.agent.setup — integración agent + tools_registry."""

import json

import pytest

from friday.agent.setup import build_action_registry, register_agent_tools
from friday.agent.permissions import PermissionGate
from friday.core.tools_registry import ToolsRegistry


@pytest.fixture()
def wired():
    action_reg = build_action_registry()
    gate = PermissionGate(action_reg)
    tools_reg = ToolsRegistry()
    register_agent_tools(tools_reg, gate)
    return tools_reg, gate


class TestBuildActionRegistry:
    def test_has_expected_actions(self):
        reg = build_action_registry()
        assert "abrir_app" in reg
        assert "listar_procesos" in reg
        assert "leer_archivo" in reg
        assert "info_sistema" in reg
        assert "listar_directorio" in reg

    def test_rejects_unregistered(self):
        reg = build_action_registry()
        assert not reg.is_allowed("shutdown_pc")


class TestRegisterAgentTools:
    def test_registers_tools_in_registry(self, wired):
        tools_reg, _ = wired
        assert "ejecutar_accion_pc" in tools_reg
        assert "listar_acciones_disponibles" in tools_reg

    def test_listar_acciones_returns_catalog(self, wired):
        tools_reg, _ = wired
        result = tools_reg.execute("listar_acciones_disponibles", {})
        data = json.loads(result)
        names = {a["name"] for a in data}
        assert "abrir_app" in names
        assert "listar_procesos" in names

    def test_ejecutar_low_risk_runs(self, wired):
        tools_reg, _ = wired
        result = tools_reg.execute("ejecutar_accion_pc", {
            "accion": "info_sistema",
            "argumentos": "{}",
        })
        data = json.loads(result)
        assert data["status"] == "ok"

    def test_ejecutar_medium_risk_pends(self, wired):
        tools_reg, _ = wired
        result = tools_reg.execute("ejecutar_accion_pc", {
            "accion": "abrir_app",
            "argumentos": '{"nombre": "notepad"}',
        })
        data = json.loads(result)
        assert data["status"] == "pending_confirmation"

    def test_ejecutar_unknown_rejected(self, wired):
        tools_reg, _ = wired
        result = tools_reg.execute("ejecutar_accion_pc", {
            "accion": "format_c",
        })
        data = json.loads(result)
        assert data["status"] == "rejected"

    def test_ejecutar_bad_json_returns_error(self, wired):
        tools_reg, _ = wired
        result = tools_reg.execute("ejecutar_accion_pc", {
            "accion": "info_sistema",
            "argumentos": "not json{",
        })
        data = json.loads(result)
        assert data["status"] == "error"
