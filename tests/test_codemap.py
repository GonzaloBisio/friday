"""docs/CODEMAP.md: cada `simbolo():N` debe seguir apuntando a su def/class.

El mapa es el índice que usan las IAs para ir directo al código; si una línea
se corre, este test avisa en vez de dejar que el índice mienta. Si la línea del
mapa nombra un archivo (`friday/voice/wake.py` o `friday.app`), el símbolo se
busca SOLO en ese archivo.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = re.compile(r"\b(\w+)\(\):(\d+)")
FILE = re.compile(r"\bfriday(?:/[\w/]+\.py|(?:\.\w+)+)")


def _file_of(token: str) -> Path | None:
    rel = token if token.endswith(".py") else token.replace(".", "/") + ".py"
    path = ROOT / rel
    return path if path.exists() else None


def _check(text: str) -> list[str]:
    sources = {p: p.read_text(encoding="utf-8").splitlines()
               for p in (ROOT / "friday").rglob("*.py")}
    stale = []
    for doc_line in text.splitlines():
        files = [f for t in FILE.findall(doc_line) if (f := _file_of(t))]
        for name, line in REF.findall(doc_line):
            n = int(line)
            pat = re.compile(rf"^\s*(def|class)\s+{name}\b")
            pool = [sources[f] for f in files] or list(sources.values())
            if not any(n <= len(ls) and pat.match(ls[n - 1]) for ls in pool):
                stale.append(f"{name}():{n}")
    return stale


def test_codemap_line_refs_are_current():
    stale = _check((ROOT / "docs" / "CODEMAP.md").read_text(encoding="utf-8"))
    assert not stale, f"Refs viejas en docs/CODEMAP.md: {stale}"


def test_detects_ref_pointing_to_wrong_file():
    # Regresión: main():N de wake.py pegado a friday.app debe fallar.
    wake_main = next(i + 1 for i, l in enumerate(
        (ROOT / "friday/voice/wake.py").read_text().splitlines()) if l.startswith("def main("))
    assert _check(f"friday.app:main():{wake_main}") == [f"main():{wake_main}"]
