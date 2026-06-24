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

    def test_cost_calculation_unknown_model_uses_scalar_fallback(self, tracker, collector):
        """Sin modelo, cae al escalar de config (robusto al valor real del .env)."""
        from friday.config import settings

        tracker.record(tokens_in=1000, tokens_out=1000)  # sin modelo → "unknown"
        points = collector.collect()
        cost = next(p for p in points if p.name == "cost_usd")
        expected = (
            settings.gemini_cost_per_1k_input_tokens
            + settings.gemini_cost_per_1k_output_tokens
        )
        assert cost.value == pytest.approx(expected, rel=1e-4)
        assert cost.unit == "usd"

    def test_cost_calculation_per_model_uses_pricing_table(self, tracker, collector):
        """Con modelo conocido, aplica la tabla por modelo (no el escalar)."""
        tracker.record(tokens_in=1000, tokens_out=1000, model="gemini-2.0-flash")
        tracker.record(tokens_in=1000, tokens_out=1000, model="gemini-2.5-pro")
        points = collector.collect()
        cost = next(p for p in points if p.name == "cost_usd")
        # 2.0-flash: 0.0001 + 0.0004 = 0.0005 ; 2.5-pro: 0.00125 + 0.01 = 0.01125
        assert cost.value == pytest.approx(0.0005 + 0.01125, rel=1e-4)

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
