"""Luces por estado — traduce el estado de FRIDAY a un color de la tira LED.

Es la capa fina encima del control IR: el resto del sistema solo llama
`get_lights().set_state("listening")` y acá se resuelve el color y se dispara
el código IR correspondiente.

Decisiones de diseño:

- **Fire-and-forget y a prueba de balas**: el envío corre en un thread daemon y
  traga TODA excepción. Las luces son feedback cosmético; jamás deben frenar ni
  romper el loop de voz si el emisor está caído o el código no fue aprendido.
- **Dedupe por estado**: si el estado no cambió, no reenvía. Evita spamear IR.
- **Limitación honesta del IR**: el remoto solo manda comandos discretos, así que
  cada estado mapea a UN color/preset fijo del remoto — no hay transiciones
  suaves arbitrarias. "thinking" usa el preset que aprendas como `processing`
  (podés mapearlo al modo fade del remoto); si no lo aprendiste, ese estado
  simplemente no hace nada.
"""

from __future__ import annotations

import logging
import threading

from friday.config import settings
from friday.integrations.ir.backends import build_backend
from friday.integrations.ir.controller import IRController, IRError
from friday.integrations.ir.devices import IRCodes

_log = logging.getLogger(__name__)

# Estado de voz → comando IR (nombre del botón que aprendiste para la tira).
# Cambiá el color de un estado tocando UNA línea. Los nombres son los comandos
# que después aprendés con `friday-ir-learn leds <comando>`.
STATE_TO_COMMAND: dict[str, str] = {
    "idle": "warm_white",     # en reposo: blanco cálido
    "listening": "celeste",   # escuchándote: celeste
    "thinking": "processing",  # procesando: preset (ej. fade) — opcional
    "responding": "amber",    # respondiendo: ámbar/dorado (bien JARVIS)
    "off": "off",             # apagada
}


class Lights:
    """Aplica estados de voz a la tira LED vía un IRController."""

    def __init__(self, controller: IRController, device: str, enabled: bool = True) -> None:
        self._controller = controller
        self._device = device
        self._enabled = enabled
        self._lock = threading.Lock()
        self._state: str | None = None

    @property
    def state(self) -> str | None:
        return self._state

    def set_state(self, state: str) -> None:
        """Pide cambiar de estado. No bloquea: despacha a un thread daemon."""
        if not self._enabled:
            return
        if state not in STATE_TO_COMMAND:
            _log.debug("Estado de luz desconocido: %s", state)
            return
        threading.Thread(target=self._apply, args=(state,), daemon=True).start()

    def _apply(self, state: str) -> None:
        with self._lock:
            if state == self._state:
                return
            command = STATE_TO_COMMAND[state]
            try:
                self._controller.send(self._device, command)
                self._state = state
            except IRError as exc:
                # Código no aprendido o emisor caído: degradamos en silencio.
                _log.debug("Luz %s/%s no aplicada: %s", self._device, command, exc)
            except Exception as exc:  # nunca propagar al loop de voz
                _log.warning("Error inesperado en luces: %s", exc)


def build_lights() -> Lights:
    """Arma la cadena completa (backend + registro + controller + luces) desde settings."""
    backend = build_backend(
        settings.ir_backend,
        broadlink_host=settings.ir_broadlink_host,
    )
    codes = IRCodes(settings.ir_codes_path)
    controller = IRController(backend, codes)
    return Lights(controller, device=settings.lights_device, enabled=settings.ir_enabled)


_lights: Lights | None = None


def get_lights() -> Lights:
    """Singleton perezoso — evita conectar al hardware en tiempo de import."""
    global _lights
    if _lights is None:
        _lights = build_lights()
    return _lights
