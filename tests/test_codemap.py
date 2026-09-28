"""docs/CODEMAP.md: cada `simbolo():N` debe seguir apuntando a su def/class.

El mapa es el índice que usan las IAs para ir directo al código; si una línea
se corre, este test avisa en vez de dejar que el índice mienta.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = re.compile(r"\b(\w+)\(\):(\d+)")


def test_codemap_line_refs_are_current():
    sources = {p: p.read_text(encoding="utf-8").splitlines()
               for p in (ROOT / "friday").rglob("*.py")}
    stale = []
    for name, line in REF.findall((ROOT / "docs" / "CODEMAP.md").read_text(encoding="utf-8")):
        n = int(line)
        pat = re.compile(rf"^\s*(def|class)\s+{name}\b")
        if not any(n <= len(ls) and pat.match(ls[n - 1]) for ls in sources.values()):
            stale.append(f"{name}():{n}")
    assert not stale, f"Refs viejas en docs/CODEMAP.md: {stale}"
