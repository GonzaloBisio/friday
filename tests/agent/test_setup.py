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
    def test_registers_each_action_as_first_class_tool(self, wired):
        # Aplanado: cada acción es su propia tool (ya no hay ejecutar_accion_pc).
        tools_reg, _ = wired
        assert "ejecutar_accion_pc" not in tools_reg
        for name in ("abrir_app", "cerrar_app", "registrar_gasto", "reproducir_spotify"):
            assert name in tools_reg

    def test_flat_tool_exposes_real_signature(self, wired):
        # El schema que ve el LLM tiene la firma real (nombre), no accion/argumentos.
        from friday.core.tool_schema import function_to_tool_schema
        tools_reg, _ = wired
        schema = function_to_tool_schema(tools_reg.get("abrir_app"))
        props = schema["function"]["parameters"]["properties"]
        assert "nombre" in props
        assert "argumentos" not in props
        assert schema["function"]["name"] == "abrir_app"

    def test_low_risk_runs_and_returns_bare_result(self, wired):
        # LOW ejecuta y devuelve el resultado PELADO (texto), no un wrapper JSON.
        tools_reg, _ = wired
        result = tools_reg.execute("info_sistema", {})
        assert "CPU" in result
        assert "status" not in result  # no viene envuelto en {"status": "ok", ...}

    def test_medium_risk_pends(self):
        from friday.agent.registry import ActionRegistry, RiskLevel
        action_reg = ActionRegistry()
        action_reg.register("dummy_medium", "test", RiskLevel.MEDIUM, lambda: "done", tags=("test",))
        gate = PermissionGate(action_reg)
        tools_reg = ToolsRegistry()
        register_agent_tools(tools_reg, gate)
        result = tools_reg.execute("dummy_medium", {})
        data = json.loads(result)
        assert data["status"] == "pending_confirmation"

    def test_passes_args_through_gate(self, wired):
        # registrar_gasto sin categoría → pregunta, sin tocar la planilla (no red).
        tools_reg, _ = wired
        result = tools_reg.execute("registrar_gasto", {"texto": "gasté 10 mil"})
        assert "categoría" in result.lower()

    def test_abrir_app_is_low_risk_now(self):
        from friday.agent.registry import RiskLevel
        spec = build_action_registry().get("abrir_app")
        assert spec.risk == RiskLevel.LOW
