"""Tests para friday.core.hud — FRIDAY abre paneles en el HUD (modo EDITH)."""

import pytest

from friday.core.hud import HudBridge, hud_bridge, register_hud_tools, youtube_id
from friday.core.tools_registry import ToolsRegistry


class FakeBroadcast:
    def __init__(self, hud_clients=1):
        self.sent = []
        self.hud_clients = hud_clients

    def emit(self, payload):
        self.sent.append(payload)


@pytest.fixture
def bridge(monkeypatch):
    fb = FakeBroadcast()
    monkeypatch.setattr(hud_bridge, "broadcast", fb)
    return fb


def test_mapped_tool_opens_focus_card_with_reason():
    b = HudBridge(); fb = FakeBroadcast(); b.broadcast = fb
    b.set_context("Which processes use the most memory?")
    b.tool_result("listar_procesos", {"top": 5}, "PID=1  python  CPU=0%  MEM=700MB")
    ev = fb.sent[-1]
    assert ev["type"] == "hud" and ev["mode"] == "card" and ev["panel"] == "procesos"
    assert ev["reason"] == "Which processes use the most memory?"
    assert "MEM=700MB" in ev["data"]


def test_unmapped_tool_opens_nothing():
    b = HudBridge(); fb = FakeBroadcast(); b.broadcast = fb
    b.tool_result("recordar", {}, "Anotado")
    assert fb.sent == []


def test_research_opens_big_window():
    b = HudBridge(); fb = FakeBroadcast(); b.broadcast = fb
    b.tool_result("consultar_research", {}, "# Research")
    assert fb.sent[-1]["mode"] == "stage"


@pytest.mark.parametrize("url,vid", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?t=3", "dQw4w9WgXcQ"),
    ("https://example.com/video", None),
])
def test_youtube_id(url, vid):
    assert youtube_id(url) == vid


def _tool():
    reg = ToolsRegistry(); register_hud_tools(reg)
    return reg.get("mostrar_en_hud")


def test_mostrar_video_emits_stage_with_id(bridge):
    out = _tool()(panel="video", motivo="Lanzamiento", url="https://youtu.be/dQw4w9WgXcQ")
    assert "Listo" in out
    assert bridge.sent[-1]["mode"] == "stage" and bridge.sent[-1]["video_id"] == "dQw4w9WgXcQ"


def test_mostrar_rejects_bad_video_and_unknown_panel(bridge):
    assert "YouTube" in _tool()(panel="video", url="https://example.com")
    assert "desconocido" in _tool()(panel="nada")
    assert bridge.sent == []


def test_mostrar_without_hud_says_so(monkeypatch):
    monkeypatch.setattr(hud_bridge, "broadcast", FakeBroadcast(hud_clients=0))
    assert "no está abierto" in _tool()(panel="intel")
