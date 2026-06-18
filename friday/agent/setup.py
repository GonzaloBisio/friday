"""Configuración del agente de PC — registra acciones y conecta con tools_registry."""

from __future__ import annotations

import json

from friday.agent.actions.pc_actions import (
    abrir_app,
    info_sistema,
    leer_archivo,
    listar_directorio,
    listar_procesos,
)
from friday.agent.permissions import PermissionGate
from friday.agent.registry import ActionRegistry, RiskLevel
from friday.core.tools_registry import ToolsRegistry


def build_action_registry() -> ActionRegistry:
    """Registra todas las acciones de PC en la allowlist."""
    reg = ActionRegistry()

    reg.register("abrir_app", "Abre una aplicación por nombre", RiskLevel.MEDIUM, abrir_app, tags=("pc",))
    reg.register("listar_procesos", "Lista procesos top por memoria/CPU", RiskLevel.LOW, listar_procesos, tags=("pc",))
    reg.register("leer_archivo", "Lee un archivo de texto", RiskLevel.LOW, leer_archivo, tags=("pc",))
    reg.register("info_sistema", "Info detallada del sistema", RiskLevel.LOW, info_sistema, tags=("pc",))
    reg.register("listar_directorio", "Lista contenido de un directorio", RiskLevel.LOW, listar_directorio, tags=("pc",))

    return reg


def register_agent_tools(tools_reg: ToolsRegistry, gate: PermissionGate) -> None:
    """Registra las acciones de PC como tools de Gemini, pasando por el gate de permisos."""

    def ejecutar_accion_pc(accion: str, argumentos: str = "{}") -> str:
        """Ejecuta una acción sobre la PC de Gonzalo.

        Args:
            accion: Nombre de la acción. Opciones: abrir_app, listar_procesos, leer_archivo, info_sistema, listar_directorio.
            argumentos: JSON string con los argumentos de la acción. Ej: {"nombre": "notepad"} para abrir_app.

        Returns:
            Resultado de la acción o estado de confirmación pendiente.
        """
        try:
            args = json.loads(argumentos) if argumentos else {}
        except json.JSONDecodeError:
            return json.dumps({"status": "error", "reason": "argumentos no es JSON válido"})

        result = gate.request(accion, args)
        return json.dumps(result, ensure_ascii=False, default=str)

    def listar_acciones_disponibles() -> str:
        """Lista todas las acciones de PC disponibles con su nivel de riesgo.

        Returns:
            JSON con el catálogo de acciones permitidas.
        """
        catalog = gate._registry.catalog
        actions = [
            {"name": a.name, "description": a.description, "risk": a.risk.value}
            for a in catalog
        ]
        return json.dumps(actions, ensure_ascii=False)

    tools_reg.register(ejecutar_accion_pc)
    tools_reg.register(listar_acciones_disponibles)
