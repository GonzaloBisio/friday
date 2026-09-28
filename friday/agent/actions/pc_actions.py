"""Acciones concretas de PC para FRIDAY (macOS; Linux parcial)."""

from __future__ import annotations

import platform
import subprocess
import urllib.parse
from pathlib import Path

import psutil

from friday import platform_info

# Esquemas permitidos para abrir_url. http/https → navegador; spotify: → app.
# Cerramos la lista a propósito: nada de file:, javascript:, etc.
_ALLOWED_URL_SCHEMES = ("http://", "https://", "spotify:")

# Alias hablados → nombre de la app en macOS (lo que entiende `open -a`).
# Lo no mapeado se pasa tal cual (argv, sin shell → sin inyección).
_MAC_APP_TARGETS = {
    "spotify": "Spotify",
    "whatsapp": "WhatsApp",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "firefox": "Firefox",
    "safari": "Safari",
    "notepad": "TextEdit",
    "bloc de notas": "TextEdit",
    "textedit": "TextEdit",
    "calculadora": "Calculator",
    "calculator": "Calculator",
    "calc": "Calculator",
    "explorador": "Finder",
    "explorer": "Finder",
    "finder": "Finder",
    "terminal": "Terminal",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "intellij": "IntelliJ IDEA",
    "slack": "Slack",
}

# AppleScript con el nombre por argv (no interpolado): "is running" NO lanza la
# app (a diferencia de `tell application X to quit`, que la abriría para cerrarla).
_MAC_QUIT_SCRIPT = (
    "on run argv\n"
    "  set appName to item 1 of argv\n"
    "  if application appName is running then\n"
    "    tell application appName to quit\n"
    "    return \"ok\"\n"
    "  end if\n"
    "  return \"not_running\"\n"
    "end run"
)


# ── API pública (lo que ve el LLM) ──────────────────────────────────────────
# La primera línea del docstring es la descripción que recibe el modelo
# (tool_schema) → corta y precisa. Todo subprocess va con argv en lista (sin shell).

def abrir_app(nombre: str) -> str:
    """Abre una aplicación en la Mac de Gonzalo.

    Args:
        nombre: Nombre o alias de la app (ej. "spotify", "chrome", "notepad").

    Returns:
        Mensaje honesto: confirma si abrió, o explica por qué no pudo.
    """
    app = _mac_app_name(nombre)
    if app is None:
        return "No me dijiste qué app abrir."
    if platform_info.PLATFORM != platform_info.MACOS:
        return _unsupported("abrir apps")
    result = _run(["open", "-a", app], f"abriendo '{nombre}'")
    if isinstance(result, str):
        return result
    if result.returncode == 0:
        return f"Listo, abrí '{nombre}'."
    err = (result.stderr or result.stdout or "").strip()
    return f"No pude abrir '{nombre}': {err or 'el comando falló'}"


def cerrar_app(nombre: str) -> str:
    """Cierra una aplicación abierta en la Mac de Gonzalo.

    Cierre prolijo (como Cmd+Q) vía AppleScript; si la app no estaba abierta, lo
    dice en vez de abrirla.

    Args:
        nombre: Nombre o alias de la app (ej. "spotify", "chrome", "notepad").

    Returns:
        Mensaje honesto: confirma si cerró, o explica por qué no pudo.
    """
    app = _mac_app_name(nombre)
    if app is None:
        return "No me dijiste qué app cerrar."
    if platform_info.PLATFORM != platform_info.MACOS:
        return _unsupported("cerrar apps")
    result = _run(["osascript", "-e", _MAC_QUIT_SCRIPT, app], f"cerrando '{nombre}'")
    if isinstance(result, str):
        return result
    out = (result.stdout or "").strip()
    if result.returncode == 0 and out == "ok":
        return f"Listo, cerré '{nombre}'."
    if result.returncode == 0 and out == "not_running":
        return f"'{nombre}' no estaba abierta."
    err = (result.stderr or out or "").strip()
    return f"No pude cerrar '{nombre}': {err or 'el comando falló'}"


def abrir_url(url: str) -> str:
    """Abre una URL en el navegador (o app) por defecto.

    `open` (macOS) / `xdg-open` (Linux) reciben la URL como UN argumento: el `&`
    de los query params no se parte. Respetan los handlers de protocolo:
    `spotify:` abre la app de Spotify.

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
    if "\n" in clean or "\r" in clean:
        return f"URL no válida: '{url}'"

    opener = "open" if platform_info.PLATFORM == platform_info.MACOS else "xdg-open"
    result = _run([opener, clean], f"abriendo '{url}'")
    if isinstance(result, str):
        return result
    if result.returncode == 0:
        return f"Listo, abrí '{clean}'."
    err = (result.stderr or result.stdout or "").strip()
    return f"No pude abrir '{url}': {err or 'el comando falló'}"


def _mac_app_name(nombre: str) -> str | None:
    clean = (nombre or "").strip()
    if not clean:
        return None
    return _MAC_APP_TARGETS.get(clean.lower(), clean)


def _run(argv: list[str], what: str) -> "subprocess.CompletedProcess[str] | str":
    """subprocess.run con timeout; devuelve un mensaje (str) si no pudo ejecutar."""
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, errors="replace", timeout=20,
        )
    except FileNotFoundError:
        return f"No encuentro `{argv[0]}` en esta máquina."
    except subprocess.TimeoutExpired:
        return f"Timeout {what}."


def _unsupported(what: str) -> str:
    return f"Todavía no sé {what} en esta plataforma ({platform_info.PLATFORM})."


def abrir_dashboard() -> str:
    """Abre el Command Center (HUD / dashboard / panel) de FRIDAY en el navegador.

    Es la UI propia de FRIDAY (métricas, alertas, actividad), servida por su API
    local. Usar esto —no abrir_app— cuando Gonzalo pide "el dashboard", "el HUD",
    "el panel" o "el command center".

    Returns:
        Mensaje honesto: confirma si abrió, o explica por qué no pudo.
    """
    from friday.config import settings
    result = abrir_url(f"http://127.0.0.1:{settings.api_port}/")
    return "Listo, abrí el Command Center." if result.startswith("Listo") else result


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
    disk = psutil.disk_usage(platform_info.disk_path())
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
