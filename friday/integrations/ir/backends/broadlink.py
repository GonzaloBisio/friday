"""Backend IR sobre Broadlink RM4 Mini (u otro RM) por LAN.

Requiere la dependencia opcional `broadlink` (pip install broadlink) y la IP del
emisor en tu red (`ir_broadlink_host`). Conectamos por IP explícita en vez de
discovery por broadcast: más predecible (el broadcast UDP falla en redes con
aislamiento de clientes, VPNs o VMs) y el TCP/UDP directo a la IP siempre anda.

Códigos como hex string: el RM entrega/espera bytes crudos; acá los serializamos
a hex para guardarlos en el registro JSON y reconstruirlos al enviar.
"""

from __future__ import annotations

import time

from friday.integrations.ir.controller import IRBackend, IRError


class BroadlinkBackend(IRBackend):
    def __init__(self, host: str, timeout: float = 10.0) -> None:
        if not host:
            raise IRError("Falta ir_broadlink_host (IP del RM4 en la LAN).")
        self._host = host
        self._timeout = timeout
        self._device = None  # se conecta perezosamente en el primer uso

    def _dev(self):
        """Conecta y autentica una vez; reusa el handle en llamadas siguientes."""
        if self._device is not None:
            return self._device
        try:
            import broadlink
        except ImportError as exc:  # dep opcional no instalada
            raise IRError(
                "Falta la librería 'broadlink'. Instalá: pip install broadlink"
            ) from exc
        try:
            dev = broadlink.hello(self._host, timeout=int(self._timeout))
            dev.auth()
        except Exception as exc:  # red caída, IP equivocada, device dormido
            raise IRError(f"No pude conectar al Broadlink en {self._host}: {exc}") from exc
        self._device = dev
        return dev

    def send(self, code: str) -> None:
        dev = self._dev()
        try:
            dev.send_data(bytes.fromhex(code))
        except Exception as exc:
            self._device = None  # forzar reconexión la próxima
            raise IRError(f"Fallo enviando código IR: {exc}") from exc

    def learn(self, timeout: float = 30.0) -> str:
        dev = self._dev()
        try:
            dev.enter_learning()
        except Exception as exc:
            raise IRError(f"No pude entrar en modo aprendizaje: {exc}") from exc

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(1.0)
            try:
                packet = dev.check_data()  # lanza mientras no haya código
            except Exception:
                continue
            if packet:
                return packet.hex()
        raise IRError("No se capturó ningún código IR (timeout). ¿Apuntaste el remoto?")

    def available(self) -> bool:
        try:
            self._dev()
            return True
        except IRError:
            return False
