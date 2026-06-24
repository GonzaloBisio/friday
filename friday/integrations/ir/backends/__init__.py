"""Backends de transporte IR — un módulo por hardware.

`build_backend(settings)` elige el backend según `ir_backend`:
    "mock"      → no toca hardware; ideal mientras no tengas el emisor.
    "broadlink" → Broadlink RM4 Mini (u otro RM) por LAN.
"""

from __future__ import annotations

from friday.integrations.ir.controller import IRBackend
from friday.integrations.ir.backends.mock import MockBackend


def build_backend(backend: str, *, broadlink_host: str = "", timeout: float = 10.0) -> IRBackend:
    """Construye el backend pedido. Import perezoso de broadlink (dep opcional)."""
    name = (backend or "mock").lower()
    if name == "mock":
        return MockBackend()
    if name == "broadlink":
        from friday.integrations.ir.backends.broadlink import BroadlinkBackend

        return BroadlinkBackend(host=broadlink_host, timeout=timeout)
    raise ValueError(f"Backend IR desconocido: {backend!r} (usá 'mock' o 'broadlink')")


__all__ = ["build_backend", "MockBackend"]
