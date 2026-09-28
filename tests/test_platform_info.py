"""Tests para friday.platform_info."""

from friday import platform_info


def test_forced_platform(monkeypatch):
    monkeypatch.setenv("FRIDAY_PLATFORM", "LINUX")
    assert platform_info.detect_platform() == "linux"


def test_disk_path_non_mac_is_root():
    assert platform_info.disk_path("linux") == "/"
