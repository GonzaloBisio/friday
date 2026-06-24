"""Tests para ResearchService — la capa de inteligencia (digest diario)."""

from datetime import date

import pytest

from friday.core.research import ResearchService, ResearchTopic, register_research_tools
from friday.storage.knowledge_store import KnowledgeStore


def _items(*titles):
    return [{"title": t, "url": f"https://x/{t}", "body": f"body {t}"} for t in titles]


@pytest.fixture()
def store(tmp_path):
    return KnowledgeStore(tmp_path)


# ── gather: best-effort, un tema que falla no corta el resto ────────────────

def test_gather_un_tema_que_falla_queda_vacio(store):
    def search(query, n):
        if "boom" in query:
            raise RuntimeError("DDG cayó")
        return _items("a", "b")

    topics = [
        ResearchTopic("OK", "ai news"),
        ResearchTopic("Roto", "boom"),
    ]
    svc = ResearchService(store, topics, search=search)
    gathered = svc.gather()
    assert len(gathered) == 2
    assert len(gathered[0][1]) == 2
    assert gathered[1][1] == []  # el tema roto no rompe el resto


# ── compose: markdown determinista, sin LLM ─────────────────────────────────

def test_compose_arma_markdown_con_links(store):
    svc = ResearchService(store, [], search=lambda q, n: [])
    gathered = [(ResearchTopic("IA", "q"), _items("Titulo Uno"))]
    md = svc.compose(gathered, date=date(2026, 6, 24))
    assert "# Research — 2026-06-24" in md
    assert "## IA" in md
    assert "[Titulo Uno](https://x/Titulo Uno)" in md
    assert "1 novedades en 1 temas" in md


def test_compose_tema_sin_resultados(store):
    svc = ResearchService(store, [], search=lambda q, n: [])
    md = svc.compose([(ResearchTopic("Vacío", "q"), [])], date=date(2026, 6, 24))
    assert "_Sin resultados ahora._" in md


# ── run: orquesta y persiste ────────────────────────────────────────────────

def test_run_escribe_el_digest(store):
    topics = [ResearchTopic("IA", "ai")]
    svc = ResearchService(store, topics, search=lambda q, n: _items("Noticia"))
    svc.run(date=date(2026, 6, 24))
    note = store.latest("research")
    assert note is not None
    content = store.read("research", "2026-06-24")
    assert "Noticia" in content


# ── tool de lectura: el cerebro lee el digest on-demand ─────────────────────

def test_consultar_research_sin_data():
    class FakeReg:
        def __init__(self): self.fns = {}
        def register(self, fn): self.fns[fn.__name__] = fn

    store_vacio = KnowledgeStore("/tmp/friday-test-noexiste-xyz")
    reg = FakeReg()
    register_research_tools(reg, store_vacio)
    out = reg.fns["consultar_research"]()
    assert "Todavía no junté research" in out


def test_consultar_research_devuelve_digest(store):
    ResearchService(store, [ResearchTopic("IA", "ai")],
                    search=lambda q, n: _items("Hot")).run(date=date(2026, 6, 24))

    class FakeReg:
        def __init__(self): self.fns = {}
        def register(self, fn): self.fns[fn.__name__] = fn

    reg = FakeReg()
    register_research_tools(reg, store)
    out = reg.fns["consultar_research"]()
    assert "Hot" in out
