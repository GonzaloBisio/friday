"""Tests para friday.core.context_window (prefijo estable + recorte)."""

from datetime import datetime

from friday.core.context_window import compact_tool_result, day_stamp, with_time_note


def test_day_stamp_has_no_time():
    assert day_stamp(datetime(2026, 9, 26, 19, 5)) == "Saturday 26 September 2026"


def test_time_note_is_appended():
    assert with_time_note("hola", datetime(2026, 9, 26, 7, 3)) == "hola\n\n[local time 07:03]"


def test_compact_returns_same_object_when_short():
    s = "corto"
    assert compact_tool_result(s, 100) is s


def test_compact_truncates_and_is_idempotent():
    once = compact_tool_result("z" * 1000, 50)
    assert once.startswith("z" * 50) and "recortado" in once
    assert compact_tool_result(once, 50) is once


def test_compact_disabled_with_zero():
    s = "z" * 1000
    assert compact_tool_result(s, 0) is s
