"""Detección de plataforma — un solo lugar para las diferencias de SO.

FRIDAY corre nativo en macOS (Apple Silicon): voz y backend en el mismo host.
Linux queda con soporte parcial (sin abrir/cerrar apps). Hasta 2026-09 corría en
Windows + WSL; ese código se retiró (ver historial de git si hiciera falta).

`FRIDAY_PLATFORM` (env) fuerza un valor: útil en tests o setups raros.
"""

from __future__ import annotations

import os
import sys

MACOS = "macos"
LINUX = "linux"


def detect_platform() -> str:
    """'macos' | 'linux'."""
    forced = os.environ.get("FRIDAY_PLATFORM", "").strip().lower()
    if forced:
        return forced
    return MACOS if sys.platform == "darwin" else LINUX


PLATFORM = detect_platform()


def disk_path(plat: str | None = None) -> str:
    """Volumen a medir para 'uso de disco'.

    En macOS (APFS) "/" es el volumen de sistema SELLADO (~10GB, siempre igual);
    los datos del usuario viven en /System/Volumes/Data.
    """
    if (plat or PLATFORM) == MACOS and os.path.isdir("/System/Volumes/Data"):
        return "/System/Volumes/Data"
    return "/"
