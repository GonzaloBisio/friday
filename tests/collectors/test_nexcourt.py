"""Tests para friday.collectors.nexcourt — NexcourtCollector con HTTP mockeado.

Cubre modos "direct" (management ports) y "kong" (gateway health).
"""

from unittest.mock import MagicMock

import pytest

from friday.collectors.nexcourt import NexcourtCollector, _parse_prometheus
from friday.collectors.nexcourt import _SERVICE_MGMT_PORTS, _SERVICE_KONG_PATHS


SAMPLE_PROMETHEUS = """\
# HELP http_server_requests_seconds_count
# TYPE http_server_requests_seconds_count counter
http_server_requests_seconds_count{method="GET",uri="/api/clubs"} 150
http_server_requests_seconds_count{method="POST",uri="/api/clubs"} 30
# HELP http_server_requests_seconds_sum
http_server_requests_seconds_sum{method="GET",uri="/api/clubs"} 12.5
http_server_requests_seconds_sum{method="POST",uri="/api/clubs"} 3.2
# HELP jvm_memory_used_bytes
jvm_memory_used_bytes{area="heap"} 1.5e8
# HELP process_cpu_usage
process_cpu_usage 0.032
# HELP some_unrelated_metric
some_unrelated_metric 999
"""


def _mock_health_response(status="UP", status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"status": status}
    return resp


def _mock_prometheus_response(text=SAMPLE_PROMETHEUS, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


@pytest.fixture()
def mock_client():
    return MagicMock()


@pytest.fixture()
def collector(mock_client):
    """Collector en modo direct con dos servicios."""
    return NexcourtCollector(
        mode="direct",
        direct_host="http://localhost",
        services=["clubs-service", "reservations-service"],
        api_key="test-key",
        client=mock_client,
    )


@pytest.fixture()
def kong_collector(mock_client):
    """Collector en modo kong (solo health, sin prometheus)."""
    return NexcourtCollector(
        mode="kong",
        kong_url="https://dev-api.nexcourts.com",
        services=["clubs-service", "reservations-service"],
        client=mock_client,
    )


# ── Direct mode: health ──────────────────────────────────────────────────

class TestDirectModeHealth:
    def test_healthy_service_returns_status_1(self, mock_client, collector):
        mock_client.get.side_effect = [
            _mock_health_response("UP"),
            _mock_prometheus_response(),
            _mock_health_response("UP"),
            _mock_prometheus_response(),
        ]
        points = collector.collect()
        status_points = [p for p in points if p.name == "status"]
        assert len(status_points) == 2
        assert all(p.value == 1.0 for p in status_points)

    def test_down_service_returns_status_0(self, mock_client, collector):
        mock_client.get.side_effect = [
            _mock_health_response("DOWN"),
            _mock_health_response("UP"),
            _mock_prometheus_response(),
        ]
        points = collector.collect()
        status_points = [p for p in points if p.name == "status"]
        down = next(p for p in status_points if p.service == "clubs-service")
        assert down.value == 0.0
        assert down.tags["health"] == "DOWN"

    def test_unreachable_service_returns_status_0(self, mock_client, collector):
        mock_client.get.side_effect = Exception("connection refused")
        points = collector.collect()
        assert all(p.name == "status" for p in points)
        assert all(p.value == 0.0 for p in points)

    def test_http_error_returns_down(self, mock_client, collector):
        mock_client.get.return_value = _mock_health_response(status_code=503)
        points = collector.collect()
        status_points = [p for p in points if p.name == "status"]
        assert all(p.value == 0.0 for p in status_points)

    def test_uses_management_port_for_health(self, collector):
        """Verifica que en modo direct use el puerto de gestión 908x."""
        url = collector._health_url("clubs-service")
        assert f":{_SERVICE_MGMT_PORTS['clubs-service']}" in url
        assert "/actuator/health" in url

    def test_unknown_service_uses_legacy_url(self, collector):
        """Servicio sin puerto mapeado cae a URL legacy."""
        url = collector._health_url("unknown-service")
        assert "/unknown-service/actuator/health" in url


# ── Direct mode: prometheus ──────────────────────────────────────────────

class TestDirectModePrometheus:
    def test_parses_prometheus_metrics(self, mock_client, collector):
        mock_client.get.side_effect = [
            _mock_health_response("UP"),
            _mock_prometheus_response(),
            _mock_health_response("DOWN"),
        ]
        points = collector.collect()
        prom_points = [p for p in points if p.name != "status"]
        names = {p.name for p in prom_points}
        assert "http_server_requests_seconds_count" in names
        assert "jvm_memory_used_bytes" in names
        assert "process_cpu_usage" in names

    def test_skips_prometheus_when_service_down(self, mock_client, collector):
        mock_client.get.return_value = _mock_health_response("DOWN")
        points = collector.collect()
        assert all(p.name == "status" for p in points)

    def test_prometheus_fetch_uses_management_port(self, collector):
        url = collector._metrics_url("clubs-service")
        assert f":{_SERVICE_MGMT_PORTS['clubs-service']}" in url
        assert "/actuator/prometheus" in url


# ── Kong mode ────────────────────────────────────────────────────────────

class TestKongMode:
    def test_health_url_uses_kong_path(self, kong_collector):
        url = kong_collector._health_url("clubs-service")
        assert "dev-api.nexcourts.com" in url
        assert f"/health/{_SERVICE_KONG_PATHS['clubs-service']}" in url

    def test_kong_mode_skips_prometheus(self, mock_client, kong_collector):
        """En modo kong no se fetchea Prometheus (no expuesto por Kong)."""
        mock_client.get.side_effect = [
            _mock_health_response("UP"),
            _mock_health_response("UP"),
        ]
        points = kong_collector.collect()
        # Solo status, sin métricas prometheus
        prom_points = [p for p in points if p.name != "status"]
        assert len(prom_points) == 0

    def test_metrics_url_empty_in_kong_mode(self, kong_collector):
        url = kong_collector._metrics_url("clubs-service")
        assert url == ""

    def test_healthy_kong_service_returns_status_1(self, mock_client, kong_collector):
        mock_client.get.return_value = _mock_health_response("UP")
        points = kong_collector.collect()
        status_points = [p for p in points if p.name == "status"]
        assert all(p.value == 1.0 for p in status_points)

    def test_down_kong_service_returns_status_0(self, mock_client, kong_collector):
        mock_client.get.return_value = _mock_health_response("DOWN")
        points = kong_collector.collect()
        assert all(p.value == 0.0 for p in points)


# ── Config & edge cases ──────────────────────────────────────────────────

class TestNexcourtCollectorConfig:
    def test_empty_services_returns_empty(self):
        c = NexcourtCollector(mode="direct", direct_host="http://x", services=[], client=MagicMock())
        assert c.collect() == []

    def test_source_property(self, collector):
        assert collector.source == "nexcourt"

    def test_run_wrapper(self, mock_client, collector):
        mock_client.get.side_effect = Exception("boom")
        points = collector.run()
        assert isinstance(points, list)


# ── Prometheus parser ────────────────────────────────────────────────────

class TestParsePrometheus:
    def test_parses_known_metrics(self):
        result = _parse_prometheus(SAMPLE_PROMETHEUS)
        assert result["http_server_requests_seconds_count"] == pytest.approx(180.0)
        assert result["http_server_requests_seconds_sum"] == pytest.approx(15.7)
        assert result["jvm_memory_used_bytes"] == pytest.approx(1.5e8)
        assert result["process_cpu_usage"] == pytest.approx(0.032)

    def test_ignores_unknown_metrics(self):
        result = _parse_prometheus(SAMPLE_PROMETHEUS)
        assert "some_unrelated_metric" not in result

    def test_empty_input(self):
        assert _parse_prometheus("") == {}

    def test_comments_only(self):
        assert _parse_prometheus("# HELP foo\n# TYPE foo counter\n") == {}
