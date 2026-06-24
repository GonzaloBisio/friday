"""Integración con Spotify Web API — búsqueda y control de reproducción.

El Web API funciona como **control remoto**: las órdenes de play/pause se aplican
sobre el DISPOSITIVO ACTIVO de Spotify (típicamente la app de escritorio abierta).
Controlar la reproducción requiere cuenta **Premium**; la búsqueda no.

Auth: OAuth Authorization Code flow. El `refresh_token` (de larga vida) se obtiene
UNA vez con `friday-spotify-auth` y se guarda en `.spotify_token.json` (gitignored).
De ahí en más, esta integración refresca el `access_token` sola, cacheándolo en
memoria hasta poco antes de su expiración.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx

from friday.config import settings

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"
_TIMEOUT = 15.0

# Scopes mínimos: leer el estado del player + controlar la reproducción.
SCOPES = "user-read-playback-state user-modify-playback-state"

# Tipos de búsqueda soportados. playlist/album/artist se reproducen como
# "context"; track como lista de uris (la API los trata distinto).
_TIPOS = ("playlist", "track", "album", "artist")

# Cache del access_token en memoria → evita refrescar en cada llamada.
_access_cache: dict[str, object] = {"token": "", "expires_at": 0.0}


class SpotifyError(Exception):
    """Error de la integración con Spotify (auth, red o API)."""


def basic_auth_header() -> str:
    """Header Basic con client_id:client_secret en base64 (para /api/token)."""
    raw = f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _load_refresh_token() -> str:
    path = Path(settings.spotify_token_path)
    if not path.exists():
        raise SpotifyError(
            "Spotify no está autorizado todavía. Corré `friday-spotify-auth` una vez."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SpotifyError(f"no pude leer el token guardado: {exc}") from exc
    token = data.get("refresh_token")
    if not token:
        raise SpotifyError("el archivo de token no tiene refresh_token.")
    return token


def _get_access_token() -> str:
    now = time.time()
    if _access_cache["token"] and now < float(_access_cache["expires_at"]):
        return str(_access_cache["token"])

    refresh = _load_refresh_token()
    try:
        resp = httpx.post(
            _TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": refresh},
            headers={"Authorization": basic_auth_header()},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise SpotifyError(f"no pude contactar a Spotify: {exc}") from exc
    if resp.status_code != 200:
        raise SpotifyError(f"no pude refrescar el token ({resp.status_code}).")

    payload = resp.json()
    _access_cache["token"] = payload["access_token"]
    # Margen de 60s antes del expiry real para no usar uno casi vencido.
    _access_cache["expires_at"] = now + payload.get("expires_in", 3600) - 60
    return str(_access_cache["token"])


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_access_token()}"}


def _active_device_id() -> str | None:
    """ID del dispositivo de Spotify activo (o el único disponible)."""
    try:
        resp = httpx.get(
            f"{_API_BASE}/me/player/devices", headers=_auth_headers(), timeout=_TIMEOUT
        )
    except httpx.HTTPError as exc:
        raise SpotifyError(f"no pude listar dispositivos: {exc}") from exc
    if resp.status_code != 200:
        return None
    devices = resp.json().get("devices", [])
    active = next((d for d in devices if d.get("is_active")), None)
    if active:
        return active["id"]
    # Sin ninguno "activo": si hay uno solo, usémoslo igual.
    return devices[0]["id"] if devices else None


def _buscar_primero(consulta: str, tipo: str) -> dict | None:
    try:
        resp = httpx.get(
            f"{_API_BASE}/search",
            params={"q": consulta, "type": tipo, "limit": 1},
            headers=_auth_headers(),
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise SpotifyError(f"la búsqueda falló: {exc}") from exc
    if resp.status_code != 200:
        raise SpotifyError(f"la búsqueda falló ({resp.status_code}).")
    items = resp.json().get(f"{tipo}s", {}).get("items", [])
    # Spotify a veces devuelve items None en playlists → filtrarlos.
    items = [i for i in items if i]
    return items[0] if items else None


def _buscar_con_fallback(consulta: str, tipo: str) -> tuple[dict | None, str]:
    """Busca el `tipo` pedido; si no hay resultado, prueba los otros tipos.

    Resuelve el caso real del log: pedir "rock'n'roll train" (una canción) la
    inferencia del LLM puede mandarla como playlist y no encontrar nada. Probamos
    en orden de utilidad. Devuelve (item, tipo_que_matcheó) para que la confirmación
    hablada sea HONESTA (no decir "playlist" cuando en realidad sonó un track).
    """
    orden = [tipo] + [t for t in ("track", "playlist", "album", "artist") if t != tipo]
    for t in orden:
        item = _buscar_primero(consulta, t)
        if item is not None:
            return item, t
    return None, tipo


def _play(item: dict, device_id: str, tipo: str) -> None:
    # track → uris; playlist/album/artist → context_uri.
    body = {"uris": [item["uri"]]} if tipo == "track" else {"context_uri": item["uri"]}
    try:
        resp = httpx.put(
            f"{_API_BASE}/me/player/play",
            params={"device_id": device_id},
            json=body,
            headers=_auth_headers(),
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise SpotifyError(f"no pude mandar el play: {exc}") from exc
    if resp.status_code == 403:
        raise SpotifyError("Spotify requiere cuenta Premium para controlar la reproducción.")
    if resp.status_code not in (200, 204):
        raise SpotifyError(f"el play falló ({resp.status_code}).")


def reproducir_spotify(consulta: str, tipo: str = "playlist") -> str:
    """Busca en Spotify y reproduce el primer resultado en el dispositivo activo.

    Args:
        consulta: Qué buscar (ej. "Tech House", "Bohemian Rhapsody").
        tipo: "playlist" (default), "track", "album" o "artist".

    Returns:
        Mensaje honesto: qué se puso a sonar, o por qué no se pudo.
    """
    consulta = (consulta or "").strip()
    if not consulta:
        return "No me dijiste qué reproducir."
    tipo = (tipo or "playlist").strip().lower()
    if tipo not in _TIPOS:
        tipo = "playlist"

    try:
        item, matched = _buscar_con_fallback(consulta, tipo)
        if item is None:
            return f"No encontré nada para '{consulta}' en Spotify."
        device_id = _active_device_id()
        if device_id is None:
            return (
                "No hay ningún dispositivo de Spotify activo. "
                "Abrí la app de Spotify y volvé a pedírmelo."
            )
        _play(item, device_id, matched)
    except SpotifyError as exc:
        return f"No pude reproducir en Spotify: {exc}"
    return f"Reproduciendo {matched} '{item['name']}' en Spotify."


def pausar_spotify() -> str:
    """Pausa la reproducción actual de Spotify.

    Returns:
        Mensaje honesto del resultado.
    """
    try:
        resp = httpx.put(
            f"{_API_BASE}/me/player/pause", headers=_auth_headers(), timeout=_TIMEOUT
        )
    except (SpotifyError, httpx.HTTPError) as exc:
        return f"No pude pausar Spotify: {exc}"
    if resp.status_code == 404:
        return "No hay reproducción activa para pausar."
    if resp.status_code not in (200, 204):
        return f"No pude pausar Spotify ({resp.status_code})."
    return "Pausado."


def siguiente_cancion() -> str:
    """Pasa a la siguiente canción en Spotify.

    Returns:
        Mensaje honesto del resultado.
    """
    try:
        resp = httpx.post(
            f"{_API_BASE}/me/player/next", headers=_auth_headers(), timeout=_TIMEOUT
        )
    except (SpotifyError, httpx.HTTPError) as exc:
        return f"No pude pasar de canción: {exc}"
    if resp.status_code == 404:
        return "No hay reproducción activa."
    if resp.status_code not in (200, 204):
        return f"No pude pasar de canción ({resp.status_code})."
    return "Siguiente."


def ajustar_volumen(porcentaje: int) -> str:
    """Ajusta el volumen de Spotify (0-100) en el dispositivo activo.

    Args:
        porcentaje: Volumen objetivo, 0 a 100. Se recorta a ese rango.

    Returns:
        Mensaje honesto del resultado.
    """
    try:
        pct = max(0, min(100, int(porcentaje)))
    except (TypeError, ValueError):
        return "Decime un volumen entre 0 y 100."
    try:
        resp = httpx.put(
            f"{_API_BASE}/me/player/volume",
            params={"volume_percent": pct},
            headers=_auth_headers(),
            timeout=_TIMEOUT,
        )
    except (SpotifyError, httpx.HTTPError) as exc:
        return f"No pude ajustar el volumen: {exc}"
    if resp.status_code == 403:
        return "Spotify requiere Premium para ajustar el volumen."
    if resp.status_code == 404:
        return "No hay dispositivo activo. Abrí Spotify primero."
    if resp.status_code not in (200, 204):
        return f"No pude ajustar el volumen ({resp.status_code})."
    return f"Volumen al {pct}%."
