"""Rutas de etapas de voz en vivo y control del listener."""

from fastapi.testclient import TestClient

from friday.api.main import AppState, create_app


class FakeBroadcast:
    def __init__(self):
        self.sent = []
        self.active_connections = 0

    def emit(self, payload):
        self.sent.append(payload)


def _client():
    st = AppState(); st.broadcast = FakeBroadcast()
    return TestClient(create_app(st)), st.broadcast


def test_voice_event_is_rebroadcast():
    c, fb = _client()
    r = c.post("/api/voice/event", json={"stage": "thinking", "text": "hola", "who": "you"})
    assert r.status_code == 200
    assert fb.sent[-1] == {"type": "voice", "stage": "thinking", "text": "hola", "who": "you"}


def test_unknown_stage_rejected():
    c, fb = _client()
    assert c.post("/api/voice/event", json={"stage": "bailando"}).status_code == 400
    assert fb.sent == []


def test_voice_control_roundtrip():
    c, fb = _client()
    r = c.post("/api/voice/control", json={"voice": "george", "end_silence": 1.0})
    assert r.json()["voice"] == "george"
    assert fb.sent[-1]["type"] == "voice_control" and fb.sent[-1]["end_silence"] == 1.0
    assert c.get("/api/voice/control").json()["voice"] == "george"
    assert c.post("/api/voice/control", json={"voice": "nadie"}).status_code == 400
    c.post("/api/voice/control", json={"voice": "michael", "end_silence": 0.8})  # restaurar


def test_pending_actions_empty_without_gate():
    c, _ = _client()
    assert c.get("/api/agent/pending").json() == []
