"""Autorización OAuth de Spotify (one-time) → obtiene y guarda el refresh_token.

Uso: `friday-spotify-auth`. Abre el navegador, autorizás, y el refresh_token
queda en `.spotify_token.json`. Solo hace falta una vez (salvo que revoques el
acceso desde tu cuenta de Spotify).

El callback (http://127.0.0.1:8888/callback) lo atiende un mini servidor HTTP
acá en WSL. Funciona porque WSL2 espeja localhost: el navegador de Windows que
pega a 127.0.0.1:8888 llega a este listener. (Mismo motivo por el que todo el
puente WSL↔Windows usa 127.0.0.1 y no "localhost".)
"""

from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

from friday.agent.actions.pc_actions import abrir_url
from friday.config import settings
from friday.integrations.spotify import SCOPES, _TOKEN_URL, basic_auth_header

_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None

    def do_GET(self) -> None:  # noqa: N802 (firma de BaseHTTPRequestHandler)
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        _CallbackHandler.code = (params.get("code") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = "FRIDAY: autorización recibida. Ya podés cerrar esta pestaña."
        self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())

    def log_message(self, *args) -> None:  # silenciar el log del server
        pass


def main() -> None:
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise SystemExit("Faltan SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET en el .env")

    redirect = settings.spotify_redirect_uri
    parsed = urllib.parse.urlparse(redirect)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 8888

    auth_url = _AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": SCOPES,
    })

    print("Abriendo el navegador para autorizar Spotify...")
    print(abrir_url(auth_url))
    print(f"\nSi no se abrió solo, entrá manualmente a:\n{auth_url}\n")

    # Bloquea hasta recibir el callback con el code.
    server = HTTPServer((host, port), _CallbackHandler)
    print(f"Esperando la autorización en {redirect} ...")
    server.handle_request()

    code = _CallbackHandler.code
    if not code:
        raise SystemExit("No recibí el code de autorización. Reintentá.")

    resp = httpx.post(
        _TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect,
        },
        headers={"Authorization": basic_auth_header()},
        timeout=15.0,
    )
    if resp.status_code != 200:
        raise SystemExit(f"Falló el intercambio de token ({resp.status_code}): {resp.text}")

    refresh = resp.json().get("refresh_token")
    if not refresh:
        raise SystemExit("Spotify no devolvió refresh_token. Revisá los scopes.")

    path = Path(settings.spotify_token_path)
    path.write_text(json.dumps({"refresh_token": refresh}), encoding="utf-8")
    print(f"\n✅ Listo. refresh_token guardado en {path}")
    print("Ya podés pedirle a FRIDAY que reproduzca música.")


if __name__ == "__main__":
    main()
