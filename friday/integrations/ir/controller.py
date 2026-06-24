"""Orquestador IR — une un backend de transporte con el registro de códigos.

El controller NO sabe de hardware ni de archivos: delega el transporte al
`IRBackend` y la persistencia de códigos al `IRCodes`. Así un test usa el
MockBackend + un registro en memoria, y producción usa Broadlink + JSON, sin
tocar esta clase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from friday.integrations.ir.devices import IRCodes


class IRError(Exception):
    """Error de control IR (sin código, backend caído, aprendizaje fallido)."""


class IRBackend(ABC):
    """Transporte IR. Maneja códigos como strings hex (independiente del hardware)."""

    @abstractmethod
    def send(self, code: str) -> None:
        """Emite un código IR crudo (hex). Lanza IRError si no se pudo."""

    @abstractmethod
    def learn(self, timeout: float = 30.0) -> str:
        """Entra en modo aprendizaje y devuelve el código (hex) capturado.

        Bloquea hasta que el usuario apunta el remoto físico y aprieta un botón,
        o hasta `timeout`. Lanza IRError si no llegó ningún código.
        """

    def available(self) -> bool:
        """True si el backend puede operar (hardware alcanzable)."""
        return True


class IRController:
    """API de alto nivel: `send(device, command)` y `learn(device, command)`."""

    def __init__(self, backend: IRBackend, codes: IRCodes) -> None:
        self._backend = backend
        self._codes = codes

    def send(self, device: str, command: str) -> None:
        """Busca el código de (device, command) y lo emite por el backend."""
        code = self._codes.get(device, command)
        if code is None:
            raise IRError(
                f"No hay código IR para {device}/{command}. "
                f"Aprendelo con `friday-ir-learn {device} {command}`."
            )
        self._backend.send(code)

    def learn(self, device: str, command: str, timeout: float = 30.0) -> str:
        """Aprende un código del remoto físico y lo guarda en el registro."""
        code = self._backend.learn(timeout=timeout)
        self._codes.set(device, command, code)
        return code

    def has(self, device: str, command: str) -> bool:
        return self._codes.has(device, command)

    def commands(self, device: str) -> list[str]:
        return self._codes.commands(device)

    def devices(self) -> list[str]:
        return self._codes.devices()
