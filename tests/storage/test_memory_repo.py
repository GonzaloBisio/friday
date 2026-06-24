"""Tests para friday.storage.memory_repo — memoria de FRIDAY (Fase A)."""

from friday.storage.db import get_connection
from friday.storage.memory_repo import MemoryRepository


def _repo() -> MemoryRepository:
    conn = get_connection(":memory:")  # el migrate crea la tabla memories (v4)
    return MemoryRepository(conn)


class TestRemember:
    def test_saves_and_lists(self):
        repo = _repo()
        repo.remember("toma el café sin azúcar")
        items = repo.all()
        assert len(items) == 1
        assert items[0].value == "toma el café sin azúcar"

    def test_explicit_key_upserts(self):
        repo = _repo()
        repo.remember("café con leche", key="cafe")
        repo.remember("café sin azúcar", key="cafe")  # misma key → actualiza
        items = repo.all()
        assert len(items) == 1
        assert items[0].value == "café sin azúcar"

    def test_auto_key_accumulates(self):
        repo = _repo()
        repo.remember("dato uno")
        repo.remember("dato dos")
        assert repo.count() == 2

    def test_empty_value_still_stored_trimmed(self):
        repo = _repo()
        m = repo.remember("  algo  ")
        assert m.value == "algo"


class TestForget:
    def test_forgets_by_value_substring(self):
        repo = _repo()
        repo.remember("toma el café sin azúcar")
        repo.remember("juega al tenis")
        n = repo.forget("café")
        assert n == 1
        assert repo.count() == 1

    def test_forget_no_match_returns_zero(self):
        repo = _repo()
        repo.remember("algo")
        assert repo.forget("nada que ver") == 0
        assert repo.count() == 1
