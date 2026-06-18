"""Registro de acciones de PC con allowlist y niveles de riesgo."""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RiskLevel(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ActionSpec:
    """Especificación de una acción registrada."""
    name: str
    description: str
    risk: RiskLevel
    fn: Callable[..., Any]
    tags: tuple[str, ...] = ()


class ActionRegistry:
    """Allowlist de acciones que FRIDAY puede ejecutar sobre la PC."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionSpec] = {}

    def register(
        self,
        name: str,
        description: str,
        risk: RiskLevel,
        fn: Callable[..., Any],
        tags: tuple[str, ...] = (),
    ) -> None:
        self._actions[name] = ActionSpec(
            name=name, description=description, risk=risk, fn=fn, tags=tags,
        )

    def get(self, name: str) -> ActionSpec | None:
        return self._actions.get(name)

    def is_allowed(self, name: str) -> bool:
        return name in self._actions

    @property
    def catalog(self) -> list[ActionSpec]:
        return list(self._actions.values())

    def actions_by_risk(self, risk: RiskLevel) -> list[ActionSpec]:
        return [a for a in self._actions.values() if a.risk == risk]

    def __len__(self) -> int:
        return len(self._actions)

    def __contains__(self, name: str) -> bool:
        return name in self._actions
