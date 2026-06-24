"""Tests del control IR (registro, controller, backend selection) y luces.

Todo con MockBackend: ni hardware ni red. Verifica la cadena completa
estado de voz → comando → "emisión" sin un Broadlink real.
"""

import pytest

from friday.integrations.ir.backends import MockBackend, build_backend
from friday.integrations.ir.controller import IRController, IRError
from friday.integrations.ir.devices import IRCodes
from friday.integrations.lights import STATE_TO_COMMAND, Lights


# ── IRCodes (registro persistente) ──────────────────────────────────


def test_codes_set_get_roundtrip(tmp_path):
    codes = IRCodes(tmp_path / "codes.json")
    codes.set("leds", "celeste", "2600abcd")
    assert codes.get("leds", "celeste") == "2600abcd"
    assert codes.has("leds", "celeste")
    assert not codes.has("leds", "amber")


def test_codes_persist_across_instances(tmp_path):
    path = tmp_path / "codes.json"
    IRCodes(path).set("tv", "power", "deadbeef")
    # Una instancia nueva debe leer lo que guardó la anterior.
    assert IRCodes(path).get("tv", "power") == "deadbeef"


def test_codes_listing(tmp_path):
    codes = IRCodes(tmp_path / "codes.json")
    codes.set("leds", "celeste", "01")
    codes.set("leds", "amber", "02")
    codes.set("tv", "power", "03")
    assert codes.devices() == ["leds", "tv"]
    assert codes.commands("leds") == ["amber", "celeste"]


def test_codes_corrupt_file_degrades_to_empty(tmp_path):
    path = tmp_path / "codes.json"
    path.write_text("{ not valid json", encoding="utf-8")
    codes = IRCodes(path)
    assert codes.devices() == []


# ── IRController ────────────────────────────────────────────────────


def test_controller_send_emits_stored_code(tmp_path):
    backend = MockBackend()
    codes = IRCodes(tmp_path / "c.json")
    codes.set("leds", "celeste", "2600abcd")
    ctrl = IRController(backend, codes)

    ctrl.send("leds", "celeste")
    assert backend.sent == ["2600abcd"]


def test_controller_send_unknown_code_raises(tmp_path):
    ctrl = IRController(MockBackend(), IRCodes(tmp_path / "c.json"))
    with pytest.raises(IRError):
        ctrl.send("leds", "celeste")


def test_controller_learn_stores_code(tmp_path):
    backend = MockBackend()
    ctrl = IRController(backend, IRCodes(tmp_path / "c.json"))
    code = ctrl.learn("leds", "celeste")
    assert ctrl.has("leds", "celeste")
    assert ctrl.commands("leds") == ["celeste"]
    assert code.startswith("mock-code-")


# ── Backend factory ─────────────────────────────────────────────────


def test_build_backend_mock():
    assert isinstance(build_backend("mock"), MockBackend)


def test_build_backend_unknown_raises():
    with pytest.raises(ValueError):
        build_backend("zigbee")


def test_build_backend_broadlink_requires_host():
    # Sin host, el BroadlinkBackend se niega a construirse (IRError).
    with pytest.raises(IRError):
        build_backend("broadlink", broadlink_host="")


# ── Lights (estado de voz → color) ──────────────────────────────────


def _lights_with(tmp_path, enabled=True):
    backend = MockBackend()
    codes = IRCodes(tmp_path / "c.json")
    # Aprendemos todos los comandos que mapean los estados.
    for command in set(STATE_TO_COMMAND.values()):
        codes.set("leds", command, f"code-{command}")
    ctrl = IRController(backend, codes)
    return Lights(ctrl, device="leds", enabled=enabled), backend


def test_lights_apply_maps_state_to_command(tmp_path):
    lights, backend = _lights_with(tmp_path)
    lights._apply("listening")
    assert backend.sent == ["code-celeste"]
    assert lights.state == "listening"


def test_lights_dedupe_same_state(tmp_path):
    lights, backend = _lights_with(tmp_path)
    lights._apply("listening")
    lights._apply("listening")  # mismo estado: no reenvía
    assert backend.sent == ["code-celeste"]


def test_lights_disabled_does_nothing(tmp_path):
    lights, backend = _lights_with(tmp_path, enabled=False)
    lights.set_state("listening")
    assert backend.sent == []


def test_lights_missing_code_does_not_raise(tmp_path):
    # Estado válido pero sin código aprendido → degrada en silencio, no rompe.
    backend = MockBackend()
    codes = IRCodes(tmp_path / "c.json")  # vacío: ningún código
    lights = Lights(IRController(backend, codes), device="leds")
    lights._apply("listening")  # no debe lanzar
    assert backend.sent == []
    assert lights.state is None


def test_lights_unknown_state_ignored(tmp_path):
    lights, backend = _lights_with(tmp_path)
    lights.set_state("dancing")  # no está en STATE_TO_COMMAND
    assert backend.sent == []
