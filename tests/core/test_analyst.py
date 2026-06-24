"""Tests para friday.core.analyst — TrendAnalyzer (Pilar 3: tendencias)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from friday.core.analyst import TrendAnalyzer
from friday.models import MetricPoint
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository


@pytest.fixture()
def conn():
    c = get_connection(":memory:", check_same_thread=False)
    yield c
    c.close()


@pytest.fixture()
def repo(conn):
    return MetricsRepository(conn)


def _seed(repo, name, value, minutes_ago, count=6):
    """Siembra `count` puntos de una métrica alrededor de `minutes_ago`."""
    base = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    for i in range(count):
        repo.save(MetricPoint(
            timestamp=base - timedelta(seconds=i * 10),
            source="system", name=name, value=value,
        ))


def _seed_trend(repo, name, baseline_val, recent_val):
    """Baseline a ~3h atrás (dentro de 6h-1h) y reciente a ~20min (dentro de 1h)."""
    _seed(repo, name, baseline_val, minutes_ago=180)
    _seed(repo, name, recent_val, minutes_ago=20)


# ── Detección ──────────────────────────────────────────────────────────────

class TestDetection:
    def test_detects_sustained_rise(self, repo):
        # RAM: baseline 55%, reciente 75% → +36%, por encima del floor (50) y del umbral (25%).
        _seed_trend(repo, "ram_percent", baseline_val=55.0, recent_val=75.0)
        notifs = TrendAnalyzer(repo).analyze()
        ram = [n for n in notifs if "RAM" in n.title]
        assert len(ram) == 1
        assert ram[0].level == "warning"
        assert ram[0].source == "analyst"

    def test_no_alert_when_rise_below_threshold(self, repo):
        # 55 → 60 = +9%, por debajo del 25%.
        _seed_trend(repo, "ram_percent", baseline_val=55.0, recent_val=60.0)
        assert TrendAnalyzer(repo).analyze() == []

    def test_no_alert_below_floor(self, repo):
        # Sube fuerte (10 → 25 = +150%) pero sigue por debajo del floor de RAM (50): ruido.
        _seed_trend(repo, "ram_percent", baseline_val=10.0, recent_val=25.0)
        assert TrendAnalyzer(repo).analyze() == []

    def test_no_alert_with_insufficient_data(self, repo):
        # Solo 2 puntos por ventana, < analyst_min_points (5).
        _seed(repo, "ram_percent", 55.0, minutes_ago=180, count=2)
        _seed(repo, "ram_percent", 80.0, minutes_ago=20, count=2)
        assert TrendAnalyzer(repo).analyze() == []


# ── Anti-spam (disciplina del cambio de estado) ─────────────────────────────

class TestAntiSpam:
    def test_does_not_repeat_same_insight(self, repo):
        _seed_trend(repo, "ram_percent", baseline_val=55.0, recent_val=75.0)
        analyzer = TrendAnalyzer(repo)
        first = analyzer.analyze()
        second = analyzer.analyze()
        assert len(first) == 1
        assert second == []  # mismo estado → no repite

    def test_realerts_after_returning_to_normal(self, repo):
        _seed_trend(repo, "ram_percent", baseline_val=55.0, recent_val=75.0)
        analyzer = TrendAnalyzer(repo)
        assert len(analyzer.analyze()) == 1
        # El estado interno se limpia si la tendencia ya no califica.
        analyzer._clear("ram_percent")
        assert "ram_percent" not in analyzer._state


# ── run(): persiste + despacha ──────────────────────────────────────────────

class TestRun:
    def test_run_persists_and_dispatches(self, repo):
        _seed_trend(repo, "ram_percent", baseline_val=55.0, recent_val=75.0)
        dispatcher = MagicMock()
        notif_repo = MagicMock()
        out = TrendAnalyzer(repo, dispatcher=dispatcher, notif_repo=notif_repo).run()
        assert len(out) == 1
        notif_repo.save.assert_called_once()
        dispatcher.dispatch.assert_called_once_with(out)

    def test_run_no_insight_does_not_dispatch(self, repo):
        _seed_trend(repo, "ram_percent", baseline_val=55.0, recent_val=58.0)
        dispatcher = MagicMock()
        TrendAnalyzer(repo, dispatcher=dispatcher).run()
        dispatcher.dispatch.assert_not_called()
