"""Registro de códigos IR — mapea (dispositivo, comando) → código crudo (hex).

Persiste en un JSON (gitignored: contiene la "huella" de tus dispositivos, no
secretos, pero es específico de tu casa). Estructura:

    {
      "leds":  {"on": "2600...", "celeste": "2600...", "warm_white": "2600..."},
      "tv":    {"power": "2600...", "vol_up": "2600..."},
      "aire":  {"on": "2600...", "off": "2600..."}
    }

Los códigos se aprenden UNA vez con `friday-ir-learn` y de ahí se reproducen.
"""

from __future__ import annotations

import json
from pathlib import Path


class IRCodes:
    """Diccionario (device, command) → código hex, respaldado en un JSON."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._data: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            # Normalizamos: solo dicts de str→str sobreviven.
            self._data = {
                dev: {cmd: str(code) for cmd, code in cmds.items()}
                for dev, cmds in raw.items()
                if isinstance(cmds, dict)
            }
        except (json.JSONDecodeError, OSError, AttributeError):
            self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self, device: str, command: str) -> str | None:
        return self._data.get(device, {}).get(command)

    def set(self, device: str, command: str, code: str) -> None:
        self._data.setdefault(device, {})[command] = code
        self._save()

    def has(self, device: str, command: str) -> bool:
        return command in self._data.get(device, {})

    def commands(self, device: str) -> list[str]:
        return sorted(self._data.get(device, {}).keys())

    def devices(self) -> list[str]:
        return sorted(self._data.keys())
