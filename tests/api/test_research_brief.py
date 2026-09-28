"""GET /api/research/brief — resumen del digest redactado por el cerebro (cacheado)."""

from fastapi.testclient import TestClient

from friday.api import routes_research
from friday.api.main import AppState, create_app
from friday.storage.knowledge_store import KnowledgeStore


class FakeBrain:
    def __init__(self):
        self.calls = 0

    def compose(self, prompt, *, model=None):
        self.calls += 1
        assert "agregadores" in prompt and "Gemini 3.8" in prompt
        return "Salió Gemini 3.8."


def test_brief_is_composed_once_and_cached(tmp_path):
    routes_research._BRIEF_CACHE.clear()
    store = KnowledgeStore(str(tmp_path))
    store.save_digest("research", "# Research\n\n- Gemini 3.8 lanzado")
    st = AppState(); st.knowledge = store; st.brain = FakeBrain()
    c = TestClient(create_app(st))
    assert c.get("/api/research/brief").json()["brief"] == "Salió Gemini 3.8."
    c.get("/api/research/brief")
    assert st.brain.calls == 1


def test_brief_without_research(tmp_path):
    st = AppState(); st.knowledge = KnowledgeStore(str(tmp_path)); st.brain = FakeBrain()
    assert TestClient(create_app(st)).get("/api/research/brief").json()["available"] is False
