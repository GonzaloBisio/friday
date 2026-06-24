"""Acciones concretas de PC para FRIDAY."""

from __future__ import annotations

import platform
import subprocess
import urllib.parse
from pathlib import Path

import psutil


# Alias comunes → target de lanzamiento en Windows. Las URIs (spotify:, whatsapp:)
# son lo más confiable para apps de Store/Electron.
_WINDOWS_APP_TARGETS = {
    "spotify": "spotify:",
    "whatsapp": "whatsapp:",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "notepad": "notepad",
    "bloc de notas": "notepad",
    "calculadora": "calc",
    "calculator": "calc",
    "calc": "calc",
    "explorador": "explorer",
    "explorer": "explorer",
    "terminal": "wt",
    "vscode": "code",
    "code": "code",
    "visual studio code": "code",
}

# Caracteres de control de shell — se rechazan en targets sin mapear (anti-inyección).
_UNSAFE_CHARS = set('&|<>^%"\n\r')

# Alias → nombre(s) del proceso (.exe) para cerrar en Windows. taskkill
# matchea por IMAGE NAME (insensible a mayúsculas).
#
# Algunas apps son UWP/Store: el launcher (calc.exe) arranca la app real
# (CalculatorApp.exe) y se AUTOCIERRA. Por eso algunos alias tienen una
# LISTA de procesos a probar en orden — si el primero no está, prueba el
# siguiente. Sin esto, taskkill /IM calc.exe encuentra nada porque calc.exe
# ya exitó.
_WINDOWS_KILL_TARGETS: dict[str, str | list[str]] = {
    "spotify": "Spotify.exe",
    "whatsapp": "WhatsApp.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "firefox": "firefox.exe",
    "notepad": "notepad.exe",
    "bloc de notas": "notepad.exe",
    # Calculator es UWP en Win11: calc.exe es solo el launcher. El proceso
    # real es CalculatorApp.exe. Probar ambos por si acaso.
    "calculadora": ["CalculatorApp.exe", "calc.exe"],
    "calculator": ["CalculatorApp.exe", "calc.exe"],
    "calc": ["CalculatorApp.exe", "calc.exe"],
    "explorador": "explorer.exe",
    "explorer": "explorer.exe",
    "vscode": "Code.exe",
    "code": "Code.exe",
    "visual studio code": "Code.exe",
    "terminal": "WindowsTerminal.exe",
}


def abrir_app(nombre: str) -> str:
    """Abre una aplicación de Windows desde WSL (vía interop con cmd.exe).

    FRIDAY corre en WSL/Linux; las apps viven en Windows. Esta acción cruza el
    puente con `cmd.exe /c start`. Resuelve alias comunes (ej. "spotify" → la URI
    spotify:) y, si no conoce el nombre, intenta abrirlo tal cual (PATH/App Paths).

    Args:
        nombre: Nombre o alias de la app (ej. "spotify", "chrome", "notepad").

    Returns:
        Mensaje honesto: confirma si abrió, o explica por qué no pudo.
    """
    clean = (nombre or "").strip()
    if not clean:
        return "No me dijiste qué app abrir."

    target = _WINDOWS_APP_TARGETS.get(clean.lower(), clean)
    is_known = target in _WINDOWS_APP_TARGETS.values()
    if not is_known and _UNSAFE_CHARS & set(target):
        return f"Nombre de app no válido: '{nombre}'"

    try:
        # argv como lista (sin shell=True) → el target no se interpola en un shell.
        # errors="replace": cmd.exe escribe en la codepage OEM de Windows (no UTF-8);
        # sin esto, un acento en la salida (ej. warning de UNC) rompe el decode.
        result = subprocess.run(
            ["cmd.exe", "/c", "start", "", target],
            capture_output=True, text=True, errors="replace", timeout=20,
        )
    except FileNotFoundError:
        return "No encuentro cmd.exe — ¿el interop de WSL está deshabilitado?"
    except subprocess.TimeoutExpired:
        return f"Timeout abriendo '{nombre}'."

    if result.returncode == 0:
        return f"Listo, abrí '{nombre}' en Windows."
    err = (result.stderr or result.stdout or "").strip()
    return f"No pude abrir '{nombre}': {err or 'el comando falló'}"


def cerrar_app(nombre: str) -> str:
    """Cierra una aplicación de Windows desde WSL (vía interop con cmd.exe).

    Usa `taskkill /IM <proceso>.exe` — mata por nombre de imagen. Resuelve
    alias comunes (ej. "spotify" → Spotify.exe). Si no conoce el nombre,
    intenta cerrarlo tal cual (asumiendo que es un .exe).

    Algunos alias mapean a una LISTA de procesos (apps UWP: el launcher
    se autocierra, el proceso real tiene otro nombre). Se prueba cada uno
    hasta que uno mata algo.

    Args:
        nombre: Nombre o alias de la app (ej. "spotify", "chrome", "notepad").

    Returns:
        Mensaje honesto: confirma si cerró, o explica por qué no pudo.
    """
    clean = (nombre or "").strip()
    if not clean:
        return "No me dijiste qué app cerrar."

    target = _WINDOWS_KILL_TARGETS.get(clean.lower())
    if target is None:
        # Fallback: asumir que es un .exe. Sanitizar anti-inyección.
        candidate = clean.lower().removesuffix(".exe") + ".exe"
        if _UNSAFE_CHARS & set(candidate):
            return f"Nombre de app no válido: '{nombre}'"
        target = candidate

    # Normalizar a lista: un solo nombre o varios (UWP launcher vs app real).
    proc_names = target if isinstance(target, list) else [target]

    last_out = ""
    for proc in proc_names:
        try:
            result = subprocess.run(
                ["cmd.exe", "/c", "taskkill", "/IM", proc, "/F"],
                capture_output=True, text=True, errors="replace", timeout=20,
            )
        except FileNotFoundError:
            return "No encuentro cmd.exe — ¿el interop de WSL está deshabilitado?"
        except subprocess.TimeoutExpired:
            return f"Timeout cerrando '{nombre}'."

        if result.returncode == 0:
            return f"Listo, cerré '{nombre}' en Windows."

        out = (result.stdout or result.stderr or "").strip().lower()
        last_out = (result.stdout or result.stderr or "").strip()
        # "no running task" / "not found" = este proc no está corriendo.
        # Probar el siguiente de la lista (puede ser un UWP con otro nombre).
        if "no running task" in out or "not found" in out:
            continue
        # Otro error (access denied, etc.) = error real, no reintentes.
        return f"No pude cerrar '{nombre}': {last_out or 'el comando falló'}"

    # Ningún proceso de la lista estaba corriendo.
    return f"'{nombre}' no estaba abierta."


# Esquemas permitidos para abrir_url. http/https → navegador; spotify: → app.
# Cerramos la lista a propósito: nada de file:, javascript:, etc.
_ALLOWED_URL_SCHEMES = ("http://", "https://", "spotify:")


def abrir_url(url: str) -> str:
    """Abre una URL en el navegador (o app) por defecto de Windows, desde WSL.

    Usa PowerShell `Start-Process` en vez del bridge `cmd.exe start` por una razón
    concreta: `cmd.exe` interpreta el `&` de los query params como separador de
    comandos y PARTE la URL. `Start-Process` la recibe como un argumento entero.
    Además respeta los handlers de protocolo de Windows: `http/https` abre el
    navegador, `spotify:` abre la app de Spotify.

    Args:
        url: URL a abrir. Debe empezar con http://, https:// o spotify:.

    Returns:
        Mensaje honesto: confirma si abrió, o explica por qué no pudo.
    """
    clean = (url or "").strip()
    if not clean:
        return "No me dijiste qué URL abrir."
    if not clean.lower().startswith(_ALLOWED_URL_SCHEMES):
        return f"URL no válida (esperaba http/https/spotify): '{url}'"
    # Saltos de línea → inyección en el -Command de PowerShell. Se rechazan.
    if "\n" in clean or "\r" in clean:
        return f"URL no válida: '{url}'"

    # La URL viaja dentro de un string single-quoted de PowerShell. Una comilla
    # simple literal se escapa duplicándola ('') — así no se puede romper el quote.
    safe = clean.replace("'", "''")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             f"Start-Process '{safe}'"],
            capture_output=True, text=True, errors="replace", timeout=20,
        )
    except FileNotFoundError:
        return "No encuentro powershell.exe — ¿el interop de WSL está deshabilitado?"
    except subprocess.TimeoutExpired:
        return f"Timeout abriendo '{url}'."

    if result.returncode == 0:
        return f"Listo, abrí '{clean}'."
    err = (result.stderr or result.stdout or "").strip()
    return f"No pude abrir '{url}': {err or 'el comando falló'}"


def buscar_en_google(consulta: str) -> str:
    """Abre una búsqueda de Google en el navegador por defecto.

    Construye la URL de búsqueda codificando la consulta (quote_plus), así
    cualquier caracter especial queda percent-encoded y no rompe nada.

    Args:
        consulta: Texto a buscar (ej. "clima Córdoba", "documentación FastAPI").

    Returns:
        Mensaje honesto: confirma la búsqueda o explica por qué no pudo.
    """
    clean = (consulta or "").strip()
    if not clean:
        return "No me dijiste qué buscar."
    url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(clean)
    result = abrir_url(url)
    # abrir_url confirma con "Listo, ..." al abrir bien; si no, propaga el error.
    return f"Buscando '{clean}' en Google." if result.startswith("Listo") else result


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
