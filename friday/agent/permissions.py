"""Gate de permisos para acciones de PC."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from friday.agent.registry import ActionRegistry, ActionSpec, RiskLevel

logger = logging.getLogger(__name__)


@dataclass
class PendingAction:
    """Acción medium/high esperando confirmación del usuario."""
    action_id: str
    spec: ActionSpec
    args: dict[str, Any]


class PermissionGate:
    """Controla la ejecución de acciones según su nivel de riesgo.

    - LOW: se ejecuta automáticamente.
    - MEDIUM/HIGH: queda pendiente hasta que el usuario confirme.
    """

    def __init__(self, registry: ActionRegistry) -> None:
        self._registry = registry
        self._pending: dict[str, PendingAction] = {}

    def request(self, action_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Solicita ejecutar una acción. Retorna resultado o estado pendiente."""
        spec = self._registry.get(action_name)
        if spec is None:
            return {"status": "rejected", "reason": f"Acción '{action_name}' no está en la allowlist"}

        if spec.risk == RiskLevel.LOW:
            return self._execute(spec, args)

        action_id = uuid.uuid4().hex[:12]
        self._pending[action_id] = PendingAction(
            action_id=action_id, spec=spec, args=args,
        )
        logger.info("Acción %s (risk=%s) pendiente: %s", action_name, spec.risk.value, action_id)
        return {
            "status": "pending_confirmation",
            "action_id": action_id,
            "action": action_name,
            "risk": spec.risk.value,
            "description": spec.description,
            "args": args,
        }

    def confirm(self, action_id: str, approved: bool) -> dict[str, Any]:
        """Confirma o rechaza una acción pendiente."""
        pending = self._pending.pop(action_id, None)
        if pending is None:
            return {"status": "error", "reason": f"No hay acción pendiente con id '{action_id}'"}

        if not approved:
            logger.info("Acción %s rechazada por el usuario", pending.spec.name)
            return {"status": "denied", "action": pending.spec.name}

        return self._execute(pending.spec, pending.args)

    @property
    def pending_actions(self) -> list[PendingAction]:
        return list(self._pending.values())

    def _execute(self, spec: ActionSpec, args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = spec.fn(**args)
            logger.info("Acción %s ejecutada OK", spec.name)
            return {"status": "ok", "action": spec.name, "result": result}
        except Exception as exc:
            logger.error("Error ejecutando %s: %s", spec.name, exc)
            return {"status": "error", "action": spec.name, "reason": str(exc)}
