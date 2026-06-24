"""Tests para las tools de memoria y su inyección al prompt (Fase A)."""

from friday.core.memory_tools import register_memory_tools
from friday.core.ollama_brain import OllamaBrain
from friday.core.tools_registry import ToolsRegistry
from friday.storage.db import get_connection
from friday.storage.memory_repo import Memory, MemoryRepository


def _repo() -> MemoryRepository:
    return MemoryRepository(get_connection(":memory:"))


class TestMemoryTools:
    def test_recordar_persists(self):
        repo = _repo()
        reg = ToolsRegistry()
        register_memory_tools(reg, repo)
        out = reg.execute("recordar", {"contenido": "toma el café sin azúcar"})
        assert "anotado" in out.lower()
        assert repo.count() == 1

    def test_recordar_empty(self):
        repo = _repo()
        reg = ToolsRegistry()
        register_memory_tools(reg, repo)
        assert "qué recordar" in reg.execute("recordar", {"contenido": "  "}).lower()

    def test_olvidar_removes(self):
        repo = _repo()
        repo.remember("toma el café sin azúcar")
        reg = ToolsRegistry()
        register_memory_tools(reg, repo)
        out = reg.execute("olvidar", {"descripcion": "café"})
        assert "olvidé" in out.lower()
        assert repo.count() == 0

    def test_olvidar_no_match(self):
        repo = _repo()
        reg = ToolsRegistry()
        register_memory_tools(reg, repo)
        assert "no tenía" in reg.execute("olvidar", {"descripcion": "x"}).lower()


class _FakeMem:
    def __init__(self, items):
        self._items = items

    def all(self, limit=50):
        return self._items


class TestMemoryInjection:
    def test_injects_memory_block(self):
        brain = OllamaBrain(
            registry=None,
            memory_repo=_FakeMem([Memory(key="cafe", value="toma el café sin azúcar")]),
        )
        sys_content = brain._build_messages()[0]["content"]
        assert "remember about Gonzalo" in sys_content
        assert "toma el café sin azúcar" in sys_content

    def test_no_memory_repo_no_block(self):
        brain = OllamaBrain(registry=None)
        sys_content = brain._build_messages()[0]["content"]
        assert "remember about Gonzalo" not in sys_content

    def test_empty_memories_no_block(self):
        brain = OllamaBrain(registry=None, memory_repo=_FakeMem([]))
        sys_content = brain._build_messages()[0]["content"]
        assert "remember about Gonzalo" not in sys_content
