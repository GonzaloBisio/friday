"""Recalcula las referencias `simbolo():N` de docs/CODEMAP.md.

Las líneas se corren con cada edición; en vez de corregirlas a mano, correr:
    ./venv/bin/python scripts/fix_codemap_refs.py
Si la línea del mapa nombra un archivo (`friday/voice/wake.py` o `friday.app`), el
símbolo se busca en ese archivo; si no, en todo `friday/` (debe ser único).
tests/test_codemap.py falla si alguna referencia quedó vieja.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "CODEMAP.md"
REF = re.compile(r"\b(\w+)\(\):(\d+)")
FILE = re.compile(r"\bfriday(?:/[\w/]+\.py|(?:\.\w+)+)")


def _defs(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = re.match(r"\s*(?:def|class)\s+(\w+)\b", line)
        if m:
            out.setdefault(m.group(1), i)
    return out


def main() -> int:
    files = {p: _defs(p) for p in (ROOT / "friday").rglob("*.py")}
    changed, unresolved = 0, []
    lines = DOC.read_text(encoding="utf-8").splitlines(keepends=True)
    for idx, doc_line in enumerate(lines):
        named = []
        for tok in FILE.findall(doc_line):
            rel = tok if tok.endswith(".py") else tok.replace(".", "/") + ".py"
            if (ROOT / rel).exists():
                named.append(ROOT / rel)

        def fix(m: re.Match) -> str:
            nonlocal changed
            name = m.group(1)
            pool = named or list(files)
            hits = {files[f][name] for f in pool if name in files[f]}
            if len(hits) != 1:
                unresolved.append(f"{name}(): {len(hits)} candidatos")
                return m.group(0)
            new = f"{name}():{hits.pop()}"
            changed += new != m.group(0)
            return new

        lines[idx] = REF.sub(fix, doc_line)
    DOC.write_text("".join(lines), encoding="utf-8")
    print(f"{changed} referencias actualizadas en docs/CODEMAP.md")
    for u in unresolved:
        print(f"  ⚠ sin resolver: {u}")
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
