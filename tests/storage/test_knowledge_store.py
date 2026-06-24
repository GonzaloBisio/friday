"""Tests para KnowledgeStore — la capa de conocimiento en archivos markdown."""

from datetime import date

import pytest

from friday.storage.knowledge_store import KnowledgeStore


@pytest.fixture()
def store(tmp_path):
    return KnowledgeStore(tmp_path)


def test_save_y_latest(store):
    store.save_digest("research", "# Hola\n\ntexto", date=date(2026, 6, 24))
    note = store.latest("research")
    assert note is not None
    assert note.name == "2026-06-24"
    assert note.title == "Hola"  # toma el primer heading
    assert note.category == "research"


def test_latest_devuelve_el_mas_reciente(store):
    store.save_digest("research", "# viejo", date=date(2026, 6, 20))
    store.save_digest("research", "# nuevo", date=date(2026, 6, 24))
    assert store.latest("research").name == "2026-06-24"


def test_save_mismo_dia_pisa(store):
    store.save_digest("research", "# v1", date=date(2026, 6, 24))
    store.save_digest("research", "# v2", date=date(2026, 6, 24))
    assert len(store.list("research")) == 1
    assert store.read("research", "2026-06-24") == "# v2"


def test_list_orden_y_limite(store):
    for d in (20, 21, 22):
        store.save_digest("research", f"# d{d}", date=date(2026, 6, d))
    names = [n.name for n in store.list("research", limit=2)]
    assert names == ["2026-06-22", "2026-06-21"]


def test_read_inexistente_es_none(store):
    assert store.read("research", "2099-01-01") is None


def test_latest_categoria_vacia_es_none(store):
    assert store.latest("research") is None


def test_read_rechaza_nombre_inseguro(store):
    # Anti path-traversal: un nombre con separadores no debe leer nada.
    store.save_digest("research", "# ok", date=date(2026, 6, 24))
    assert store.read("research", "../research/2026-06-24") is None


def test_categoria_invalida_lanza(store):
    with pytest.raises(ValueError):
        store.save_digest("../evil", "x")
