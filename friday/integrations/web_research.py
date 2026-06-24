"""Capacidad de investigación web para FRIDAY — búsqueda real + lectura de páginas.

A diferencia de `buscar_en_google` (que solo ABRE el navegador para Gonzalo), estas
tools traen el TEXTO de vuelta al modelo, para que pueda resumir, comparar y
recomendar sobre data REAL — en vez de inventar.

- `buscar_web`: DuckDuckGo (sin API key), devuelve título + resumen + URL.
- `leer_pagina`: baja la página y extrae el contenido principal (trafilatura),
  descartando menús/ads. Trunca el resultado para no inflar el contexto del LLM
  local que corre en CPU.

Seguridad (anti-SSRF): solo `http/https`, y se bloquean hosts que resuelven a IPs
privadas/loopback — así FRIDAY no sondea servicios internos (NEXCOURT/AXIS, la API
local) sin querer. Se re-chequea el host final por si hubo redirect.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse

import httpx
import trafilatura
from ddgs import DDGS

_TIMEOUT = 15.0
# Techo de caracteres del texto extraído → controla la latencia del LLM en CPU.
_MAX_CHARS = 6000
_USER_AGENT = "Mozilla/5.0 (FRIDAY personal assistant)"


def _es_host_privado(host: str) -> bool:
    """True si el host resuelve a una IP privada/loopback/reservada (anti-SSRF)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False  # no resuelve → que falle el fetch normal, no acá
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return True
    return False


def _url_segura(url: str) -> tuple[bool, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "solo puedo leer URLs http/https."
    if not parsed.hostname:
        return False, "la URL no tiene un host válido."
    if _es_host_privado(parsed.hostname):
        return False, "no leo direcciones internas/privadas."
    return True, ""


def buscar_web_items(consulta: str, cantidad: int = 5) -> list[dict]:
    """Resultados de búsqueda CRUDOS y estructurados: [{title, url, body}].

    Es la base de `buscar_web` (que formatea esto a texto para el LLM) y la usa el
    research collector, que necesita los campos por separado para armar markdown con
    links limpios. PROPAGA la excepción si DDG falla: cada caller decide su fallback
    (buscar_web lo envuelve en un mensaje; el collector saltea ese tema).

    Args:
        consulta: Qué buscar.
        cantidad: Cuántos resultados traer (1-10). Default 5.

    Returns:
        Lista de dicts con title/url/body. Vacía si la consulta viene vacía.
    """
    consulta = (consulta or "").strip()
    if not consulta:
        return []
    cantidad = max(1, min(10, cantidad))
    resultados = DDGS().text(consulta, max_results=cantidad)  # puede lanzar
    items = []
    for r in resultados or []:
        items.append({
            "title": r.get("title") or "(sin título)",
            "url": r.get("href") or r.get("url") or r.get("link") or "",
            "body": (r.get("body") or r.get("snippet") or "").strip(),
        })
    return items


def buscar_web(consulta: str, cantidad: int = 5) -> str:
    """Busca en la web y devuelve los primeros resultados (título, resumen y URL).

    A diferencia de buscar_en_google (que abre el navegador para vos), esto trae
    los resultados como texto para que FRIDAY pueda razonar sobre ellos: comparar,
    resumir o recomendar. Después podés pedirle que lea una de las URLs con leer_pagina.

    Args:
        consulta: Qué buscar.
        cantidad: Cuántos resultados traer (1-10). Default 5.

    Returns:
        Texto con los resultados numerados, o un mensaje si no hubo.
    """
    if not (consulta or "").strip():
        return "No me dijiste qué buscar."

    try:
        items = buscar_web_items(consulta, cantidad)
    except Exception as exc:  # ddgs scrapea → puede romper si DDG cambia algo
        return f"No pude buscar en la web ahora: {exc}"
    if not items:
        return f"No encontré resultados para '{consulta}'."

    lineas = []
    for i, it in enumerate(items, 1):
        lineas.append(f"{i}. {it['title']}\n   {it['url']}\n   {it['body']}")
    return "\n".join(lineas)


def leer_pagina(url: str) -> str:
    """Baja una página web y devuelve su contenido principal en texto limpio.

    Usa trafilatura para quedarse con el artículo (sin menús/ads) y trunca el
    resultado para no inflar el contexto del modelo local. Útil para que FRIDAY
    lea una noticia/artículo y después lo discuta o resuma.

    Args:
        url: URL http/https a leer.

    Returns:
        El texto principal de la página (posiblemente truncado), o un error honesto.
    """
    url = (url or "").strip()
    if not url:
        return "No me dijiste qué página leer."
    ok, motivo = _url_segura(url)
    if not ok:
        return f"No puedo leer esa URL: {motivo}"

    try:
        resp = httpx.get(
            url,
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )
    except httpx.HTTPError as exc:
        return f"No pude acceder a la página: {exc}"
    if resp.status_code != 200:
        return f"La página devolvió {resp.status_code}."

    # Re-chequeo anti-SSRF: si redirigió a un host interno, no leemos.
    final_host = resp.url.host
    if final_host and _es_host_privado(final_host):
        return "La página redirigió a una dirección interna; no la leo."

    texto = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
    if not texto:
        return "No pude extraer contenido legible de esa página."
    texto = texto.strip()
    if len(texto) > _MAX_CHARS:
        texto = texto[:_MAX_CHARS] + "\n[...truncado...]"
    return texto
