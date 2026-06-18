"""Tests para friday.core.tools_registry — ToolsRegistry y tools de lectura."""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from friday.core.tools_registry import ToolsRegistry, build_registry, _points_to_json
from friday.models import MetricPoint
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository


@pytest.fixture()
def registry():
    return ToolsRegistry()


def _sample_fn(x: int, y: int = 1) -> int:
    """Suma dos números."""
    return x + y


class TestToolsRegistry:
    def test_register_and_list(self, registry):
        registry.register(_sample_fn)
        assert "_sample_fn" in registry.names
        assert len(registry) == 1

    def test_execute_calls_function(self, registry):
        registry.register(_sample_fn)
        result = registry.execute("_sample_fn", {"x": 3, "y": 7})
        assert result == 10

    def test_execute_unknown_tool_raises(self, registry):
        with pytest.raises(KeyError, match="no_existe"):
            registry.execute("no_existe", {})

    def test_contains(self, registry):
        registry.register(_sample_fn)
        assert "_sample_fn" in registry
        assert "otro" not in registry

    def test_get_returns_callable(self, registry):
        registry.register(_sample_fn)
        fn = registry.get("_sample_fn")
        assert fn is _sample_fn

    def test_get_unknown_returns_none(self, registry):
        assert registry.get("nada") is None

    def test_as_callable_list(self, registry):
        registry.register(_sample_fn)
        callables = registry.as_callable_list()
        assert len(callables) == 1
        assert callables[0] is _sample_fn


@pytest.fixture()
def repo_with_data(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    repo = MetricsRepository(conn)
    now = datetime.now(timezone.utc)
    points = [
        MetricPoint(timestamp=now, source="system", name="cpu_percent", value=45.0, unit="%"),
        MetricPoint(timestamp=now, source="system", name="ram_percent", value=60.0, unit="%"),
        MetricPoint(timestamp=now, source="gemini", name="cost_usd", value=0.005, unit="usd"),
        MetricPoint(timestamp=now, source="gemini", name="requests", value=3.0, unit="count"),
        MetricPoint(timestamp=now, source="gemini", name="tokens_in", value=1500.0, unit="tokens"),
        MetricPoint(timestamp=now, source="gemini", name="tokens_out", value=800.0, unit="tokens"),
    ]
    repo.save_many(points)
    yield repo
    conn.close()


class TestBuildRegistry:
    def test_builds_with_default_tools(self, repo_with_data):
        reg = build_registry(repo_with_data)
        assert "consultar_metricas" in reg
        assert "resumen_costos" in reg
        assert len(reg) == 2


class TestConsultarMetricas:
    def test_returns_json_with_metrics(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("consultar_metricas", {"source": "system"})
        data = json.loads(result)
        assert len(data) == 2
        names = {d["name"] for d in data}
        assert "cpu_percent" in names
        assert "ram_percent" in names

    def test_filters_by_name(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("consultar_metricas", {"source": "system", "name": "cpu_percent"})
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["value"] == 45.0

    def test_empty_source_returns_empty(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("consultar_metricas", {"source": "productivity"})
        data = json.loads(result)
        assert data == []


class TestResumenCostos:
    def test_returns_cost_summary(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("resumen_costos", {})
        data = json.loads(result)
        assert data["costo_total_usd"] == pytest.approx(0.005, rel=1e-4)
        assert data["requests_totales"] == 3
        assert data["tokens_in_totales"] == 1500
        assert data["tokens_out_totales"] == 800

    def test_returns_zeros_when_no_data(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        conn = get_connection(db_path)
        repo = MetricsRepository(conn)
        reg = build_registry(repo)
        result = reg.execute("resumen_costos", {})
        data = json.loads(result)
        assert data["costo_total_usd"] == 0.0
        assert data["requests_totales"] == 0
        conn.close()

    def test_respects_horas_window(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("resumen_costos", {"horas": 1})
        data = json.loads(result)
        assert data["costo_total_usd"] == pytest.approx(0.005, rel=1e-4)


class TestPointsToJson:
    def test_serializes_points(self):
        now = datetime.now(timezone.utc)
        points = [MetricPoint(timestamp=now, source="s", name="n", value=1.0)]
        result = _points_to_json(points)
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["source"] == "s"
        assert data[0]["value"] == 1.0
