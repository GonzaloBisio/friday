"""CLI `friday-ir-learn` — aprende códigos IR del remoto físico y los guarda.

Uso (una vez que tengas el emisor Broadlink configurado en .env):

    friday-ir-learn leds celeste       # apuntá el remoto y apretá el botón celeste
    friday-ir-learn leds warm_white
    friday-ir-learn leds amber
    friday-ir-learn leds off
    friday-ir-learn tv power           # también sirve para TV, aire, etc.

    friday-ir-learn --list             # muestra lo aprendido

Los colores que mapea cada estado de voz están en
`friday.integrations.lights.STATE_TO_COMMAND`.
"""

from __future__ import annotations

import sys

from friday.config import settings
from friday.integrations.ir.backends import build_backend
from friday.integrations.ir.controller import IRController, IRError
from friday.integrations.ir.devices import IRCodes


def _controller() -> IRController:
    backend = build_backend(
        settings.ir_backend,
        broadlink_host=settings.ir_broadlink_host,
    )
    return IRController(backend, IRCodes(settings.ir_codes_path))


def _list() -> int:
    ctrl = _controller()
    devices = ctrl.devices()
    if not devices:
        print("No hay códigos aprendidos todavía.")
        return 0
    for dev in devices:
        print(f"{dev}:")
        for cmd in ctrl.commands(dev):
            print(f"  - {cmd}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--list":
        return _list()
    if len(argv) < 2:
        print("Uso: friday-ir-learn <device> <command>  (ej: friday-ir-learn leds celeste)")
        return 2

    device, command = argv[0], argv[1]
    if settings.ir_backend == "mock":
        print(
            "⚠️  ir_backend='mock': no hay hardware. Configurá ir_backend=broadlink y "
            "ir_broadlink_host en .env para aprender de verdad."
        )

    ctrl = _controller()
    print(f"Apuntá el remoto al emisor y apretá el botón para «{device}/{command}»...")
    try:
        ctrl.learn(device, command)
    except IRError as exc:
        print(f"❌ {exc}")
        return 1
    print(f"✅ Aprendido y guardado: {device}/{command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
