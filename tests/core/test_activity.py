"""Tests para friday.core.activity — registro en vivo de actividad de tools (#3)."""

from friday.core.activity import ToolActivityLog, format_args


class TestToolActivityLog:
    def test_records_and_returns_recent(self):
        log = ToolActivityLog()
        log.record("abrir_app", "running", "nombre=spotify")
        log.record("abrir_app", "ok", "Listo")
        events = log.recent()
        assert len(events) == 2
        assert events[0]["tool"] == "abrir_app"
        assert events[0]["status"] == "running"
        assert events[1]["status"] == "ok"
        assert all("ts" in e and "id" in e for e in events)

    def test_ids_are_monotonic(self):
        log = ToolActivityLog()
        log.record("a", "ok")
        log.record("b", "ok")
        ids = [e["id"] for e in log.recent()]
        assert ids == sorted(ids)
        assert len(set(ids)) == 2

    def test_ring_buffer_caps_size(self):
        log = ToolActivityLog(maxlen=3)
        for i in range(10):
            log.record(f"t{i}", "ok")
        events = log.recent(100)
        assert len(events) == 3
        # Quedan los últimos.
        assert [e["tool"] for e in events] == ["t7", "t8", "t9"]

    def test_recent_n_limits(self):
        log = ToolActivityLog()
        for i in range(20):
            log.record(f"t{i}", "ok")
        assert len(log.recent(5)) == 5

    def test_detail_is_truncated(self):
        log = ToolActivityLog()
        log.record("x", "ok", "y" * 500)
        assert len(log.recent()[0]["detail"]) <= 161  # límite + "…"

    def test_clear_resets(self):
        log = ToolActivityLog()
        log.record("a", "ok")
        log.clear()
        assert log.recent() == []


class TestFormatArgs:
    def test_empty(self):
        assert format_args({}) == ""

    def test_formats_kv(self):
        assert format_args({"nombre": "spotify", "vol": 70}) == "nombre=spotify, vol=70"
