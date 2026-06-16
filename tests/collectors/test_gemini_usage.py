"""Tests para friday.collectors.gemini_usage — GeminiTracker y GeminiUsageCollector."""

import pytest

from friday.collectors.gemini_usage import GeminiTracker, GeminiUsageCollector


@pytest.fixture()
def tracker():
    return GeminiTracker()


@pytest.fixture()
def collector(tracker):
    return GeminiUsageCollector(tracker=tracker)


class TestGeminiTracker:
    def test_record_accumulates(self, tracker):
        tracker.record(tokens_in=100, tokens_out=50)
        tracker.record(tokens_in=200, tokens_out=80)
        totals = tracker.totals
        assert totals["requests"] == 2
        assert totals["tokens_in"] == 300
        assert totals["tokens_out"] == 130

    def test_snapshot_and_reset(self, tracker):
        tracker.record(tokens_in=500, tokens_out=200)
        snap = tracker.snapshot_and_reset()
        assert snap["requests"] == 1
        assert snap["tokens_in"] == 500
        assert snap["tokens_out"] == 200
        # Después del reset, los contadores están en cero
        assert tracker.totals["requests"] == 0
        assert tracker.totals["tokens_in"] == 0

    def test_empty_tracker(self, tracker):
        totals = tracker.totals
        assert totals["requests"] == 0
        assert totals["tokens_in"] == 0
        assert totals["tokens_out"] == 0


class TestGeminiUsageCollector:
    def test_collect_returns_four_metrics(self, tracker, collector):
        tracker.record(tokens_in=1000, tokens_out=500)
        points = collector.collect()
        names = {p.name for p in points}
        assert names == {"requests", "tokens_in", "tokens_out", "cost_usd"}
        assert all(p.source == "gemini" for p in points)

    def test_cost_calculation(self, tracker, collector):
        """Verifica que el costo se calcule con los precios de config."""
        tracker.record(tokens_in=1000, tokens_out=1000)
        points = collector.collect()
        cost = next(p for p in points if p.name == "cost_usd")
        # 1K tokens_in * 0.00125 + 1K tokens_out * 0.005 = 0.00625
        assert cost.value == pytest.approx(0.00625, rel=1e-4)
        assert cost.unit == "usd"

    def test_collect_resets_counters(self, tracker, collector):
        """Después de collect(), los contadores del tracker quedan en cero."""
        tracker.record(tokens_in=100, tokens_out=50)
        collector.collect()
        # Segundo collect sin nuevos records
        points = collector.collect()
        tokens_in = next(p for p in points if p.name == "tokens_in")
        assert tokens_in.value == 0.0

    def test_collect_with_no_usage(self, collector):
        """Sin uso, retorna métricas con valor cero."""
        points = collector.collect()
        assert len(points) == 4
        assert all(p.value == 0.0 for p in points)

    def test_source_property(self, collector):
        assert collector.source == "gemini"


class TestGeminiUsageCollectorRun:
    def test_run_wraps_collect(self, tracker, collector):
        tracker.record(tokens_in=100, tokens_out=50)
        points = collector.run()
        assert len(points) == 4
