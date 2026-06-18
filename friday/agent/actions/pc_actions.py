"""Acciones concretas de PC para FRIDAY."""

from __future__ import annotations

import os
import subprocess
import platform
from pathlib import Path

import psutil


def abrir_app(nombre: str) -> str:
    """Abre una aplicación por nombre en Windows.

    Args:
        nombre: Nombre del ejecutable o app (ej. "notepad", "calculator", "explorer").

    Returns:
        Mensaje confirmando la apertura.
    """
    try:
        subprocess.Popen(nombre, shell=True)
        return f"Aplicación '{nombre}' abierta"
    except Exception as exc:
        return f"No pude abrir '{nombre}': {exc}"


def listar_procesos(top: int = 15) -> str:
    """Lista los procesos que más CPU o memoria consumen.

    Args:
        top: Cantidad de procesos a mostrar. Default 15.

    Returns:
        Tabla de procesos con PID, nombre, CPU% y memoria MB.
    """
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            mem_mb = (info["memory_info"].rss / 1024 / 1024) if info["memory_info"] else 0
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu": info["cpu_percent"] or 0,
                "mem_mb": round(mem_mb, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    procs.sort(key=lambda x: x["mem_mb"], reverse=True)
    lines = [f"PID={p['pid']}  {p['name']:<30}  CPU={p['cpu']:.1f}%  MEM={p['mem_mb']:.0f}MB"
             for p in procs[:top]]
    return "\n".join(lines) if lines else "No se encontraron procesos"


def leer_archivo(ruta: str, max_lineas: int = 100) -> str:
    """Lee el contenido de un archivo de texto.

    Args:
        ruta: Ruta absoluta al archivo.
        max_lineas: Máximo de líneas a leer. Default 100.

    Returns:
        Contenido del archivo o mensaje de error.
    """
    path = Path(ruta)
    if not path.exists():
        return f"Archivo no encontrado: {ruta}"
    if not path.is_file():
        return f"No es un archivo: {ruta}"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        truncated = lines[:max_lineas]
        result = "\n".join(truncated)
        if len(lines) > max_lineas:
            result += f"\n... ({len(lines) - max_lineas} líneas más)"
        return result
    except Exception as exc:
        return f"Error leyendo {ruta}: {exc}"


def info_sistema() -> str:
    """Retorna información detallada del sistema operativo y hardware.

    Returns:
        Resumen del sistema: OS, CPU, RAM, disco, uptime, red.
    """
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot = psutil.boot_time()
    uptime_s = psutil.time.time() - boot
    uptime_h = uptime_s / 3600

    net = psutil.net_io_counters()
    sent_gb = net.bytes_sent / (1024 ** 3)
    recv_gb = net.bytes_recv / (1024 ** 3)

    lines = [
        f"OS: {platform.system()} {platform.release()} ({platform.version()})",
        f"CPU: {psutil.cpu_count(logical=False)} cores / {psutil.cpu_count()} threads — {psutil.cpu_percent(interval=0.5)}% uso",
        f"RAM: {mem.used / (1024**3):.1f} GB / {mem.total / (1024**3):.1f} GB ({mem.percent}%)",
        f"Disco: {disk.used / (1024**3):.0f} GB / {disk.total / (1024**3):.0f} GB ({disk.percent}%)",
        f"Uptime: {uptime_h:.1f} horas",
        f"Red: ↑ {sent_gb:.2f} GB  ↓ {recv_gb:.2f} GB",
    ]
    return "\n".join(lines)


def listar_directorio(ruta: str = ".") -> str:
    """Lista el contenido de un directorio.

    Args:
        ruta: Ruta del directorio. Default es el directorio actual.

    Returns:
        Lista de archivos y carpetas con tamaño.
    """
    path = Path(ruta)
    if not path.exists():
        return f"Directorio no encontrado: {ruta}"
    if not path.is_dir():
        return f"No es un directorio: {ruta}"

    entries = []
    try:
        for item in sorted(path.iterdir()):
            kind = "DIR " if item.is_dir() else "FILE"
            try:
                size = item.stat().st_size if item.is_file() else 0
                size_str = _format_size(size) if size else ""
            except OSError:
                size_str = ""
            entries.append(f"  {kind}  {item.name:<40}  {size_str}")
    except PermissionError:
        return f"Sin permisos para leer {ruta}"

    header = f"Contenido de {path.resolve()}:"
    return header + "\n" + "\n".join(entries) if entries else f"{ruta} está vacío"


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
