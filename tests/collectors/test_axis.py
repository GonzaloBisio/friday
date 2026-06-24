"""Tests para friday.collectors.axis — AxisCollector con runner SSH inyectado.

No abre SSH: el runner se reemplaza por una función que devuelve salida canned.
"""

import pytest

from friday.collectors.axis import AxisCollector, _parse_output, _health_from_status, _pct

# Salida combinada: sección ps + marcador + sección stats.
_OUTPUT = """\
axis-backend|running|Up 2 days (healthy)
axis-nginx|running|Up 2 days
axis-postgres|exited|Exited (1) 2 minutes ago
hardcore_hellman|exited|Exited (0) 4 months ago
@@STATS@@
axis-backend|0.32%|13.58%
axis-nginx|0.00%|0.18%
"""

_CONTAINERS = ["axis-backend", "axis-nginx", "axis-postgres", "axis-frontend"]


def _collector(output=_OUTPUT, containers=None):
    return AxisCollector(
        host="axis",
        containers=containers if containers is not None else _CONTAINERS,
        runner=lambda cmd: output,
    )


class TestStatus:
    def test_running_container_is_up(self):
        pts = {(p.service, p.name): p for p in _collector().collect()}
        st = pts[("axis-backend", "status")]
        assert st.value == 1.0
        assert st.tags["health"] == "healthy"

    def test_running_without_healthcheck_is_up(self):
        st = next(p for p in _collector().collect()
                  if p.service == "axis-nginx" and p.name == "status")
        assert st.value == 1.0
        assert st.tags["health"] == "UP"

    def test_exited_container_is_down(self):
        st = next(p for p in _collector().collect()
                  if p.service == "axis-postgres" and p.name == "status")
        assert st.value == 0.0
        assert st.tags["health"] == "DOWN"

    def test_missing_container_is_absent(self):
        # axis-frontend está en la lista pero no aparece en la salida.
        st = next(p for p in _collector().collect()
                  if p.service == "axis-frontend" and p.name == "status")
        assert st.value == 0.0
        assert st.tags["health"] == "absent"

    def test_stray_container_ignored(self):
        services = {p.service for p in _collector().collect()}
        assert "hardcore_hellman" not in services


class TestUtilization:
    def test_cpu_and_mem_for_running(self):
        pts = {(p.service, p.name): p for p in _collector().collect()}
        assert pts[("axis-backend", "cpu_percent")].value == 0.32
        assert pts[("axis-backend", "mem_percent")].value == 13.58
        assert pts[("axis-backend", "mem_percent")].unit == "%"

    def test_no_utilization_for_down_container(self):
        names = {(p.service, p.name) for p in _collector().collect()}
        assert ("axis-postgres", "cpu_percent") not in names
        assert ("axis-postgres", "mem_percent") not in names


class TestEmptyAndFailure:
    def test_no_containers_returns_empty(self):
        assert _collector(containers=[]).collect() == []

    def test_none_output_returns_empty(self):
        col = AxisCollector(host="axis", containers=_CONTAINERS, runner=lambda cmd: None)
        assert col.collect() == []


class TestParsingHelpers:
    def test_health_from_status(self):
        assert _health_from_status("running", "Up 2 days (healthy)") == "healthy"
        assert _health_from_status("running", "Up 5 min (unhealthy)") == "unhealthy"
        assert _health_from_status("running", "Up 2 days") == "UP"
        assert _health_from_status("exited", "Exited (0) 1 hour ago") == "DOWN"

    def test_pct(self):
        assert _pct("13.58%") == 13.58
        assert _pct("0.00%") == 0.0
        assert _pct("nope") is None

    def test_parse_output_splits_sections(self):
        states, stats = _parse_output(_OUTPUT)
        assert states["axis-backend"] == ("running", "healthy")
        assert stats["axis-backend"] == (0.32, 13.58)
        assert "hardcore_hellman" in states  # parse no filtra; el collector sí
