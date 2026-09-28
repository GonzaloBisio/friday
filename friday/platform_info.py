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


def mac_memory_used_pct() -> float | None:
    """% de RAM en uso según macOS (100 − kern.memorystatus_level). None si no aplica.

    psutil.virtual_memory().percent en macOS cuenta caché/comprimida como "usada":
    marca ~80% en una Mac tranquila (medido: psutil 82.8% vs sistema 64%) y
    disparaba alertas de RAM en loop. memorystatus_level es el "% libre" que usa el
    propio kernel para la presión de memoria (lo que muestra Monitor de Actividad).
    Lectura directa por sysctlbyname (ctypes): sin subprocess, barato cada 10 s.
    """
    if PLATFORM != MACOS:
        return None
    try:
        import ctypes
        import ctypes.util
        libc = ctypes.CDLL(ctypes.util.find_library("c"))
        val = ctypes.c_int(0)
        size = ctypes.c_size_t(ctypes.sizeof(val))
        if libc.sysctlbyname(b"kern.memorystatus_level", ctypes.byref(val),
                             ctypes.byref(size), None, ctypes.c_size_t(0)) != 0:
            return None
        return float(max(0, min(100, 100 - val.value)))
    except Exception:  # noqa: BLE001
        return None
