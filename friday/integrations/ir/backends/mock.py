"""Backend IR de mentira — no toca hardware.

Registra los códigos "emitidos" en `self.sent` para que los tests verifiquen
qué se mandó, y `learn()` devuelve un código sintético. Es el backend por
defecto: con él, toda la cadena (estados de voz → luces) funciona y se testea
SIN el emisor físico. Cuando llegue el Broadlink, se cambia `ir_backend` y listo.
"""

from __future__ import annotations

import logging

from friday.integrations.ir.controller import IRBackend

_log = logging.getLogger(__name__)


class MockBackend(IRBackend):
    def __init__(self) -> None:
        self.sent: list[str] = []
        self._learn_counter = 0

    def send(self, code: str) -> None:
        self.sent.append(code)
        _log.debug("MockBackend.send(%s)", code)

    def learn(self, timeout: float = 30.0) -> str:
        self._learn_counter += 1
        code = f"mock-code-{self._learn_counter:04x}"
        _log.debug("MockBackend.learn() -> %s", code)
        return code

    def available(self) -> bool:
        return True
