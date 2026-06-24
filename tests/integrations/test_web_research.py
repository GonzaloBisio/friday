"""Tests para friday.integrations.web_research — búsqueda y lectura web.

Todo mockeado: ni red ni scraping real. Se patchea DDGS, httpx.get y
trafilatura.extract del módulo.
"""

from unittest.mock import MagicMock, patch

from friday.integrations import web_research
from friday.integrations.web_research import buscar_web, leer_pagina


def _http(status=200, text="", final_url="https://example.com/a"):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.url = MagicMock()
    m.url.host = final_url.split("//")[-1].split("/")[0]
    return m


class TestBuscarWeb:
    def test_formats_results(self):
        fake = MagicMock()
        fake.text.return_value = [
            {"title": "Noticia 1", "href": "https://a.com", "body": "resumen uno"},
            {"title": "Noticia 2", "href": "https://b.com", "body": "resumen dos"},
        ]
        with patch.object(web_research, "DDGS", return_value=fake):
            result = buscar_web("noticias IA", cantidad=2)
        assert "Noticia 1" in result and "https://a.com" in result and "resumen uno" in result
        assert "Noticia 2" in result
        # cantidad se pasa como max_results
        assert fake.text.call_args.kwargs["max_results"] == 2

    def test_clamps_cantidad(self):
        fake = MagicMock()
        fake.text.return_value = []
        with patch.object(web_research, "DDGS", return_value=fake):
            buscar_web("x", cantidad=999)
        assert fake.text.call_args.kwargs["max_results"] == 10

    def test_no_results(self):
        fake = MagicMock()
        fake.text.return_value = []
        with patch.object(web_research, "DDGS", return_value=fake):
            assert "no encontré" in buscar_web("nada de nada").lower()

    def test_search_error_is_honest(self):
        fake = MagicMock()
        fake.text.side_effect = RuntimeError("DDG cambió el HTML")
        with patch.object(web_research, "DDGS", return_value=fake):
            assert "no pude buscar" in buscar_web("x").lower()

    def test_empty_query(self):
        assert "qué buscar" in buscar_web("  ").lower()


class TestLeerPagina:
    def test_extracts_main_content(self):
        with patch.object(web_research.httpx, "get", return_value=_http(text="<html>...</html>")), \
             patch.object(web_research.trafilatura, "extract", return_value="El cuerpo del artículo."):
            result = leer_pagina("https://example.com/articulo")
        assert result == "El cuerpo del artículo."

    def test_truncates_long_content(self):
        largo = "x" * 10_000
        with patch.object(web_research.httpx, "get", return_value=_http(text="<html></html>")), \
             patch.object(web_research.trafilatura, "extract", return_value=largo):
            result = leer_pagina("https://example.com")
        assert "[...truncado...]" in result
        assert len(result) < len(largo) + 50

    def test_rejects_non_http_scheme(self):
        with patch.object(web_research.httpx, "get") as get:
            result = leer_pagina("file:///etc/passwd")
        assert "no puedo leer" in result.lower()
        get.assert_not_called()

    def test_rejects_private_host(self):
        # localhost resuelve a loopback → bloqueado (anti-SSRF). Sin mocks: es real.
        with patch.object(web_research.httpx, "get") as get:
            result = leer_pagina("http://localhost:8000/admin")
        assert "internas" in result.lower() or "privad" in result.lower()
        get.assert_not_called()

    def test_redirect_to_internal_blocked(self):
        # 200 OK pero la URL final es interna → no se lee.
        resp = _http(text="<html></html>", final_url="https://127.0.0.1/x")
        with patch.object(web_research.httpx, "get", return_value=resp):
            result = leer_pagina("https://example.com/redir")
        assert "interna" in result.lower()

    def test_non_200(self):
        with patch.object(web_research.httpx, "get", return_value=_http(status=404)):
            assert "404" in leer_pagina("https://example.com/nope")

    def test_no_extractable_content(self):
        with patch.object(web_research.httpx, "get", return_value=_http(text="<html></html>")), \
             patch.object(web_research.trafilatura, "extract", return_value=None):
            assert "no pude extraer" in leer_pagina("https://example.com").lower()

    def test_empty_url(self):
        assert "qué página" in leer_pagina("  ").lower()
