"""Tests para friday.core.briefing — BriefingService (Pilar 2: rituales)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from friday.core.briefing import BriefingService
from friday.models import MetricPoint
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def conn():
    c = get_connection(":memory:", check_same_thread=False)
    yield c
    c.close()


@pytest.fixture()
def repo(conn):
    return MetricsRepository(conn)


@pytest.fixture()
def broadcast():
    b = MagicMock()
    async def _send(**kwargs):
        pass
    b.broadcast_proactive = _send
    return b


def _brain(reply: str | None = None, raises: Exception | None = None):
    """Brain falso: compose() devuelve `reply` o lanza `raises`."""
    b = MagicMock()
    if raises is not None:
        b.compose.side_effect = raises
    else:
        b.compose.return_value = reply
    return b


def _seed_system(repo, cpu=20.0, ram=40.0, disk=55.0):
    now = datetime.now(timezone.utc)
    for name, value in [("cpu_percent", cpu), ("ram_percent", ram), ("disk_percent", disk)]:
        repo.save(MetricPoint(timestamp=now, source="system", name=name, value=value))


# ── gather ────────────────────────────────────────────────────────────────

class TestGather:
    def test_collects_system_metrics(self, repo):
        _seed_system(repo, cpu=33.0, ram=66.0, disk=70.0)
        svc = BriefingService(repo=repo, brain=_brain("x"), broadcast=None)
        data = svc.gather()
        assert data["cpu"] == 33.0
        assert data["ram"] == 66.0
        assert data["disk"] == 70.0

    def test_missing_metrics_are_none(self, repo):
        svc = BriefingService(repo=repo, brain=_brain("x"), broadcast=None)
        data = svc.gather()
        assert data["cpu"] is None
        assert data["services_down"] == []
        assert data["gemini_cost_today"] == 0.0

    def test_detects_down_services(self, repo):
        now = datetime.now(timezone.utc)
        repo.save(MetricPoint(timestamp=now, source="nexcourt", name="status",
                              value=0.0, service="clubs-service"))
        repo.save(MetricPoint(timestamp=now, source="nexcourt", name="status",
                              value=1.0, service="reservations-service"))
        svc = BriefingService(repo=repo, brain=_brain("x"), broadcast=None)
        assert svc.gather()["services_down"] == ["clubs-service"]

    def test_sums_gemini_cost_today(self, repo):
        now = datetime.now(timezone.utc)
        repo.save(MetricPoint(timestamp=now, source="gemini", name="cost_usd", value=0.01))
        repo.save(MetricPoint(timestamp=now, source="gemini", name="cost_usd", value=0.02))
        svc = BriefingService(repo=repo, brain=_brain("x"), broadcast=None)
        assert svc.gather()["gemini_cost_today"] == pytest.approx(0.03)


# ── compose_text: LLM con piso de plantilla ────────────────────────────────

class TestComposeText:
    def _data(self, **over):
        base = {"cpu": 20.0, "ram": 40.0, "disk": 55.0,
                "services_down": [], "gemini_cost_today": 0.05}
        base.update(over)
        return base

    def test_uses_llm_when_it_responds(self, repo):
        svc = BriefingService(repo=repo, brain=_brain("Good morning, sir. All quiet."),
                              broadcast=None)
        text = svc.compose_text("morning", self._data())
        assert text == "Good morning, sir. All quiet."

    def test_falls_back_to_template_when_llm_raises(self, repo):
        svc = BriefingService(repo=repo, brain=_brain(raises=RuntimeError("429")),
                              broadcast=None)
        text = svc.compose_text("morning", self._data())
        # Plantilla determinista: nunca se cae el ritual.
        assert "Good morning, sir." in text
        assert "CPU 20%" in text

    def test_falls_back_when_llm_returns_empty(self, repo):
        svc = BriefingService(repo=repo, brain=_brain("   "), broadcast=None)
        text = svc.compose_text("morning", self._data())
        assert "Good morning, sir." in text

    def test_falls_back_when_llm_returns_sentinel(self, repo):
        svc = BriefingService(repo=repo, brain=_brain("(sin respuesta)"), broadcast=None)
        assert "Good morning, sir." in svc.compose_text("morning", self._data())

    def test_template_reports_down_services(self, repo):
        svc = BriefingService(repo=repo, brain=_brain(raises=RuntimeError()), broadcast=None)
        text = svc.compose_text("evening", self._data(services_down=["clubs-service"]))
        assert "clubs-service" in text
        assert "down" in text.lower()
        assert "Winding down, sir." in text


# ── run: orquestación end-to-end ───────────────────────────────────────────

class TestRun:
    def test_run_gathers_composes_and_emits(self, repo, broadcast):
        _seed_system(repo)
        brain = _brain("Morning, sir.")
        svc = BriefingService(repo=repo, brain=brain, broadcast=broadcast)
        out = svc.run("morning")
        assert out == "Morning, sir."
        brain.compose.assert_called_once()

    def test_run_survives_emit_without_broadcast(self, repo):
        _seed_system(repo)
        svc = BriefingService(repo=repo, brain=_brain("hi sir"), broadcast=None)
        # Sin broadcast no debe explotar: el briefing igual se compone.
        assert svc.run("evening") == "hi sir"
