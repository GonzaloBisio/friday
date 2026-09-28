"""Tests para friday.collectors.system — SystemCollector."""

from unittest.mock import patch, MagicMock

import pytest

from friday.collectors.system import SystemCollector


@pytest.fixture()
def collector():
    return SystemCollector()


def _mock_psutil():
    """Retorna patches para psutil con valores controlados."""
    mem = MagicMock()
    mem.percent = 65.3
    mem.used = 8_000_000_000

    disk = MagicMock()
    disk.percent = 42.1

    return {
        "friday.collectors.system.psutil.cpu_percent": patch(
            "friday.collectors.system.psutil.cpu_percent", return_value=23.5
        ),
        "friday.collectors.system.psutil.virtual_memory": patch(
            "friday.collectors.system.psutil.virtual_memory", return_value=mem
        ),
        "friday.collectors.system.psutil.disk_usage": patch(
            "friday.collectors.system.psutil.disk_usage", return_value=disk
        ),
        "friday.collectors.system.psutil.boot_time": patch(
            "friday.collectors.system.psutil.boot_time", return_value=1718000000.0
        ),
    }


class TestSystemCollectorCollect:
    def test_returns_all_system_metrics(self, collector):
        patches = _mock_psutil()
        with patches["friday.collectors.system.psutil.cpu_percent"], \
             patches["friday.collectors.system.psutil.virtual_memory"], \
             patches["friday.collectors.system.psutil.disk_usage"], \
             patches["friday.collectors.system.psutil.boot_time"]:
            points = collector.collect()

        names = {p.name for p in points}
        assert names == {"cpu_percent", "ram_percent", "ram_used_bytes", "disk_percent", "uptime_seconds"}
        assert all(p.source == "system" for p in points)

    def test_cpu_value_matches_psutil(self, collector):
        patches = _mock_psutil()
        with patches["friday.collectors.system.psutil.cpu_percent"], \
             patches["friday.collectors.system.psutil.virtual_memory"], \
             patches["friday.collectors.system.psutil.disk_usage"], \
             patches["friday.collectors.system.psutil.boot_time"]:
            points = collector.collect()

        cpu = next(p for p in points if p.name == "cpu_percent")
        assert cpu.value == 23.5
        assert cpu.unit == "%"

    def test_ram_values(self, collector, monkeypatch):
        # Camino psutil (Linux / sin sysctl): el % sale de virtual_memory().
        monkeypatch.setattr("friday.collectors.system.platform_info.mac_memory_used_pct", lambda: None)
        patches = _mock_psutil()
        with patches["friday.collectors.system.psutil.cpu_percent"], \
             patches["friday.collectors.system.psutil.virtual_memory"], \
             patches["friday.collectors.system.psutil.disk_usage"], \
             patches["friday.collectors.system.psutil.boot_time"]:
            points = collector.collect()

        ram_pct = next(p for p in points if p.name == "ram_percent")
        ram_used = next(p for p in points if p.name == "ram_used_bytes")
        assert ram_pct.value == 65.3
        assert ram_used.value == 8_000_000_000.0


class TestSystemCollectorRun:
    def test_run_returns_points_on_success(self, collector):
        """run() es el wrapper seguro que llama collect()."""
        patches = _mock_psutil()
        with patches["friday.collectors.system.psutil.cpu_percent"], \
             patches["friday.collectors.system.psutil.virtual_memory"], \
             patches["friday.collectors.system.psutil.disk_usage"], \
             patches["friday.collectors.system.psutil.boot_time"]:
            points = collector.run()
        assert len(points) == 5

    def test_run_returns_empty_on_exception(self, collector):
        """Si psutil falla, run() no explota — retorna lista vacía."""
        with patch("friday.collectors.system.psutil.cpu_percent", side_effect=OSError("no access")):
            points = collector.run()
        assert points == []

    def test_source_property(self, collector):
        assert collector.source == "system"


def test_ram_uses_macos_kernel_pressure_when_available(monkeypatch):
    """macOS: psutil cuenta caché como usada (~80% en reposo → alertas en loop)."""
    from friday.collectors.system import SystemCollector
    monkeypatch.setattr("friday.collectors.system.platform_info.mac_memory_used_pct", lambda: 64.0)
    ram = next(p for p in SystemCollector().collect() if p.name == "ram_percent")
    assert ram.value == 64.0
