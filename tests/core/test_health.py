"""Tests para friday.core.health — HealthTracker (Pilar 6: autoobservabilidad)."""

from __future__ import annotations

import pytest

from friday.core.health import HealthTracker, health_tracker, register_health_tools


@pytest.fixture(autouse=True)
def _reset_singleton():
    """El tracker es un singleton de proceso: limpiarlo antes de cada test."""
    health_tracker.reset()
    yield


# ── Tracker ─────────────────────────────────────────────────────────────────

class TestTracker:
    def test_success_rate(self):
        t = HealthTracker()
        for _ in range(9):
            t.record_tool(success=True)
        t.record_tool(success=False)
        snap = t.snapshot()
        assert snap["tool_calls"] == 10
        assert snap["tool_ok"] == 9
        assert snap["tool_errors"] == 1
        assert snap["tool_success_rate"] == 0.9

    def test_empty_snapshot_is_healthy(self):
        snap = HealthTracker().snapshot()
        assert snap["tool_success_rate"] == 1.0  # sin datos = sano, no 0
        assert snap["avg_latency_ms"] == 0.0
        assert snap["chat_count"] == 0

    def test_fallbacks_counted(self):
        t = HealthTracker()
        t.record_fallback()
        t.record_fallback()
        assert t.snapshot()["ollama_fallbacks"] == 2

    def test_latency_average(self):
        t = HealthTracker()
        t.record_latency(100.0)
        t.record_latency(300.0)
        snap = t.snapshot()
        assert snap["chat_count"] == 2
        assert snap["avg_latency_ms"] == 200.0

    def test_reset(self):
        t = HealthTracker()
        t.record_tool(success=True)
        t.record_fallback()
        t.reset()
        snap = t.snapshot()
        assert snap["tool_calls"] == 0
        assert snap["ollama_fallbacks"] == 0


# ── Integración con activity_log (el punto único de conteo) ─────────────────

class TestActivityLogFeeds:
    def test_terminal_events_count_running_does_not(self):
        from friday.core.activity import ToolActivityLog

        log = ToolActivityLog()
        log.record("abrir_app", "running")   # NO cuenta (intermedio)
        log.record("abrir_app", "ok")        # cuenta ok
        log.record("cerrar_app", "error")    # cuenta error
        snap = health_tracker.snapshot()
        assert snap["tool_calls"] == 2
        assert snap["tool_ok"] == 1
        assert snap["tool_errors"] == 1


# ── Tool del LLM ────────────────────────────────────────────────────────────

class TestHealthTool:
    def _tool(self):
        captured = {}

        class Reg:
            def register(self, fn):
                captured[fn.__name__] = fn

        register_health_tools(Reg())
        return captured["estado_de_friday"]

    def test_reports_when_idle(self):
        assert "arranco" in self._tool()().lower()

    def test_reports_vitals_when_active(self):
        health_tracker.record_tool(success=True)
        health_tracker.record_latency(1200.0)
        out = self._tool()()
        assert "100%" in out
        assert "1200" in out
