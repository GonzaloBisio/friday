"""Tests para friday.core.proactive — ProactiveDispatcher (Pilar 1)."""

from __future__ import annotations

import pytest

from friday.core.proactive import ProactiveDispatcher, _spoken_text
from friday.storage.notification_repo import Notification


def _notif(level: str, source: str = "system", title: str = "t", message: str = "m") -> Notification:
    return Notification(level=level, title=title, message=message, source=source)


class _FakeBroadcast:
    """Registra las llamadas a broadcast_proactive (async, como el real)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def broadcast_proactive(self, text, *, speak, level, title, message=""):
        self.calls.append({
            "text": text, "speak": speak, "level": level,
            "title": title, "message": message,
        })


# ── Política de severidad (plan, puro) ──────────────────────────────────────

class TestSeverityPolicy:
    def test_critical_speaks_and_toasts(self):
        d = ProactiveDispatcher(speak_min_level="critical", toast_min_level="warning")
        msg = d.plan(_notif("critical"))
        assert msg is not None
        assert msg.speak is True
        assert msg.toast is True

    def test_warning_toasts_but_does_not_speak(self):
        d = ProactiveDispatcher(speak_min_level="critical", toast_min_level="warning")
        msg = d.plan(_notif("warning"))
        assert msg is not None
        assert msg.speak is False
        assert msg.toast is True

    def test_info_below_both_thresholds_is_silenced(self):
        d = ProactiveDispatcher(speak_min_level="critical", toast_min_level="warning")
        assert d.plan(_notif("info")) is None

    def test_info_recovery_toasts_when_toast_min_is_info(self):
        d = ProactiveDispatcher(speak_min_level="critical", toast_min_level="info")
        msg = d.plan(_notif("info", source="nexcourt"))
        assert msg is not None
        assert msg.toast is True
        assert msg.speak is False

    def test_unknown_level_is_silenced(self):
        d = ProactiveDispatcher(speak_min_level="critical", toast_min_level="warning")
        assert d.plan(_notif("bogus")) is None


# ── Texto hablado (persona, inglés) ─────────────────────────────────────────

class TestSpokenText:
    def test_nexcourt_down_vs_recovery(self):
        down = _spoken_text(_notif("critical", source="nexcourt"))
        up = _spoken_text(_notif("info", source="nexcourt"))
        assert "went down" in down
        assert "back online" in up

    def test_gemini_cost_mentions_spend(self):
        txt = _spoken_text(_notif("warning", source="gemini"))
        assert "spend" in txt.lower()

    def test_system_critical_is_generic_english(self):
        txt = _spoken_text(_notif("critical", source="system"))
        assert txt.startswith("Sir,")
        # Nunca incrusta el detalle en español del título.
        assert "critical level" in txt


# ── Dispatch (integración con broadcast) ────────────────────────────────────

class TestDispatch:
    def test_dispatch_emits_qualifying_notifications(self):
        bc = _FakeBroadcast()
        d = ProactiveDispatcher(bc, speak_min_level="critical", toast_min_level="warning")
        emitted = d.dispatch([
            _notif("critical", source="nexcourt", title="clubs caído"),
            _notif("warning", source="system", title="CPU: 75%"),
            _notif("info", source="system", title="normalizado"),  # silenciada
        ])
        assert len(emitted) == 2
        assert len(bc.calls) == 2
        # La crítica habla; la warning no.
        crit = bc.calls[0]
        assert crit["speak"] is True
        assert crit["level"] == "critical"
        assert crit["title"] == "clubs caído"  # el detalle viaja para el toast
        assert bc.calls[1]["speak"] is False

    def test_dispatch_without_broadcast_is_safe(self):
        d = ProactiveDispatcher(None, speak_min_level="critical", toast_min_level="warning")
        # No revienta aunque no haya broadcast configurado.
        emitted = d.dispatch([_notif("critical")])
        assert len(emitted) == 1

    def test_dispatch_empty_list(self):
        bc = _FakeBroadcast()
        d = ProactiveDispatcher(bc)
        assert d.dispatch([]) == []
        assert bc.calls == []
