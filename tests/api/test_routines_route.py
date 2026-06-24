"""Tests para /api/routines y /api/routines/run."""

from __future__ import annotations

from fastapi.testclient import TestClient

from friday.api.main import AppState, create_app
from friday.core.routines import Routine, RoutineEngine, RoutineStep


class FakeGate:
    def __init__(self):
        self.calls = []

    def request(self, action, args):
        self.calls.append((action, args))
        return {"status": "ok", "action": action, "result": "done"}


def _engine():
    routines = {
        "focus": Routine(
            name="focus", description="test focus",
            steps=(RoutineStep("reproducir_spotify", {"consulta": "Tech House", "tipo": "playlist"}),),
        ),
    }
    return RoutineEngine(FakeGate(), routines)


def _client(engine):
    state = AppState()
    state.routines = engine
    return TestClient(create_app(state))


def test_list_routines():
    resp = _client(_engine()).get("/api/routines")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["routines"]) == 1
    assert data["routines"][0]["name"] == "focus"
    assert data["routines"][0]["steps"] == 1


def test_list_no_engine():
    resp = _client(None).get("/api/routines")
    assert resp.json() == {"routines": []}


def test_run_routine():
    engine = _engine()
    resp = _client(engine).post("/api/routines/run", json={"name": "focus"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["ran"] == 1
    assert engine._gate.calls[0][0] == "reproducir_spotify"


def test_run_unknown_routine():
    resp = _client(_engine()).post("/api/routines/run", json={"name": "nope"})
    assert resp.json()["status"] == "not_found"


def test_run_no_engine():
    resp = _client(None).post("/api/routines/run", json={"name": "focus"})
    assert resp.json()["status"] == "error"
