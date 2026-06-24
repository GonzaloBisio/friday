"""Control por infrarrojo (IR) de FRIDAY.

Capa hardware-agnóstica para emitir códigos IR y así controlar dispositivos
"tontos" (tiras LED genéricas, TV, aire) a través de un emisor IR de red.

Diseño en tres niveles para que cambiar de hardware toque UN solo lugar:

    backends/   → transporte físico (Broadlink, mock para tests)
    devices     → registro (dispositivo, comando) → código IR crudo, en JSON
    controller  → orquesta backend + registro: send(device, command), learn(...)

La capa de luces por estado (`friday.integrations.lights`) se apoya en esto.
"""

from friday.integrations.ir.controller import IRBackend, IRController, IRError
from friday.integrations.ir.devices import IRCodes

__all__ = ["IRBackend", "IRController", "IRError", "IRCodes"]
