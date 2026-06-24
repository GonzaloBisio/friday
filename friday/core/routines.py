"""RoutineEngine — Pilar 5 del salero proactivo: rutinas compuestas.

Una rutina es una secuencia NOMBRADA de acciones que FRIDAY ejecuta de un saque
("modo focus" → poné Tech House y bajá el volumen). El usuario la dispara por voz
o CLI — el humano está en el loop, así que es segura y reversible. (Las reglas
if-this-then-that AUTOMÁTICAS, que disparan acciones ante un evento sin humano,
son otra historia más delicada y quedan para un corte futuro con frenos propios.)

El motor reusa el PermissionGate: cada paso es un gate.request(action, args), así
que respeta el riesgo de cada acción igual que cuando la llama el LLM (LOW corre,
MEDIUM/HIGH queda pendiente). Best-effort: ejecuta todos los pasos y reporta el
resultado de cada uno; un paso que falle NO aborta el resto (querés tu música
aunque el ajuste de volumen falle).

Las rutinas DEFAULT son un punto de partida sensato — editalas acá; es TU asistente.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutineStep:
    action: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Routine:
    name: str
    description: str
    steps: tuple[RoutineStep, ...]


# Rutinas built-in. Solo usan acciones LOW (reversibles, sin confirmación) para que
# corran fluido por voz. Ajustá los pasos a tu gusto.
DEFAULT_ROUTINES: dict[str, Routine] = {
    "focus": Routine(
        name="focus",
        description="Modo concentración: Tech House a volumen medio.",
        steps=(
            RoutineStep("reproducir_spotify", {"consulta": "Tech House", "tipo": "playlist"}),
            RoutineStep("ajustar_volumen", {"porcentaje": 60}),
        ),
    ),
    "winddown": Routine(
        name="winddown",
        description="Bajar un cambio: Lo-Fi a volumen bajo.",
        steps=(
            RoutineStep("reproducir_spotify", {"consulta": "Lo-Fi Beats", "tipo": "playlist"}),
            RoutineStep("ajustar_volumen", {"porcentaje": 35}),
        ),
    ),
    "pausa": Routine(
        name="pausa",
        description="Pausar la música.",
        steps=(RoutineStep("pausar_spotify", {}),),
    ),
}


class RoutineEngine:
    """Ejecuta rutinas (secuencias de acciones) a través del PermissionGate."""

    def __init__(self, gate, routines: dict[str, Routine] | None = None) -> None:
        self._gate = gate
        self._routines = routines if routines is not None else dict(DEFAULT_ROUTINES)

    def list_routines(self) -> list[Routine]:
        return list(self._routines.values())

    def run(self, name: str) -> dict[str, Any]:
        """Ejecuta una rutina por nombre. Best-effort: corre todos los pasos.

        Devuelve un resumen con el estado de cada paso. Un paso fallido o pendiente
        NO corta los siguientes — el resultado lo refleja para que el caller (o el
        LLM) lo cuente con precisión.
        """
        routine = self._routines.get(name)
        if routine is None:
            return {"status": "not_found", "name": name,
                    "available": sorted(self._routines)}

        results = []
        ok = 0
        for step in routine.steps:
            res = self._gate.request(step.action, dict(step.args))
            status = res.get("status") if isinstance(res, dict) else "unknown"
            if status == "ok":
                ok += 1
            else:
                logger.info("Rutina %s: paso %s → %s", name, step.action, status)
            results.append({"action": step.action, "status": status})

        return {
            "status": "ok" if ok == len(routine.steps) else "partial",
            "name": name,
            "ran": ok,
            "total": len(routine.steps),
            "steps": results,
        }


def register_routine_tools(tools_reg, engine: RoutineEngine) -> None:
    """Expone las rutinas como tools del LLM (invocables por voz)."""

    def ejecutar_rutina(nombre: str) -> str:
        """Ejecuta una rutina compuesta por su nombre (ej. 'focus', 'winddown', 'pausa').

        Usá esto cuando Gonzalo pida un modo o rutina ('modo focus', 'a concentrarse',
        'bajemos un cambio'). Cada rutina dispara una secuencia de acciones de una.

        Args:
            nombre: El nombre de la rutina a ejecutar.

        Returns:
            Un resumen de qué pasos se ejecutaron.
        """
        result = engine.run((nombre or "").strip().lower())
        if result["status"] == "not_found":
            disponibles = ", ".join(result["available"]) or "ninguna"
            return f"No tengo una rutina '{nombre}'. Disponibles: {disponibles}."
        return f"Rutina '{result['name']}': {result['ran']}/{result['total']} pasos OK."

    def listar_rutinas() -> str:
        """Lista las rutinas disponibles que FRIDAY puede ejecutar."""
        routines = engine.list_routines()
        if not routines:
            return "No hay rutinas configuradas."
        return "; ".join(f"{r.name} ({r.description})" for r in routines)

    tools_reg.register(ejecutar_rutina)
    tools_reg.register(listar_rutinas)
