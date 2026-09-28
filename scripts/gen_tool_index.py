"""Genera docs/TOOLS.md: el catálogo de tools que ve el LLM, desde el registry REAL.

Por qué: es el índice que una IA (o vos) consulta para saber QUÉ puede hacer
FRIDAY y DÓNDE está cada tool, sin grepear el repo. Sale del mismo wiring que
`friday.app.FridaySystem`, así que no puede desincronizarse del código.
`tests/test_tool_index.py` falla si alguien agrega una tool y no regenera.

Uso:
    ./venv/bin/python scripts/gen_tool_index.py          # escribe docs/TOOLS.md
    ./venv/bin/python scripts/gen_tool_index.py --check  # exit 1 si está desactualizado
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "TOOLS.md"
# Antes de cualquier `import friday`: que gane ESTE checkout y no otro instalado en el venv.
sys.path.insert(0, str(ROOT))

# Tools que solo existen con ciertos flags (ver core/tools_registry.py).
_CONDITIONAL = {
    "alarmas_activas": "`NEXCOURT_MODE=cloudwatch`",
    "errores_recientes": "`NEXCOURT_MODE=cloudwatch`",
    "errores_axis": "`AXIS_ENABLED=true`",
}


def _build_system():
    """FridaySystem con DB en memoria y TODOS los flags que agregan tools."""
    tmp = tempfile.mkdtemp(prefix="friday-index-")
    os.environ.update({
        "DB_PATH": ":memory:",
        "KNOWLEDGE_DIR": tmp,
        "NEXCOURT_MODE": "cloudwatch",
        "AXIS_ENABLED": "true",
        "LLM_PROVIDER": "ollama",  # no instancia el SDK de Gemini
    })
    import logging
    logging.disable(logging.CRITICAL)
    from friday.app import FridaySystem
    return FridaySystem()


def render() -> str:
    from friday.core.tool_schema import function_to_tool_schema

    system = _build_system()
    reg = system.tools_registry
    actions = {spec.name: spec for spec in system.gate._registry.catalog}

    rows, total_chars = [], 0
    for name in reg.names:
        fn = reg.get(name)
        real = inspect.unwrap(fn)
        src = Path(inspect.getsourcefile(real)).resolve().relative_to(ROOT)
        line = inspect.getsourcelines(real)[1]
        schema = function_to_tool_schema(fn)
        size = len(json.dumps(schema, ensure_ascii=False))
        total_chars += size
        params = ", ".join(
            p if p in schema["function"]["parameters"]["required"] else f"{p}?"
            for p in schema["function"]["parameters"]["properties"]
        )
        spec = actions.get(name)
        risk = spec.risk.value.upper() if spec else "—"
        tags = ", ".join(spec.tags) if spec and spec.tags else ""
        cond = _CONDITIONAL.get(name, "siempre")
        desc = schema["function"]["description"].replace("|", "\\|")
        rows.append(
            f"| `{name}({params})` | {desc} | {risk} | {tags} | {cond} "
            f"| [{src}:{line}](../{src}#L{line}) | {size} |"
        )

    header = f"""# FRIDAY — Índice de tools (generado)

> **No editar a mano.** Generado por `scripts/gen_tool_index.py` desde el registry real.
> Regenerar: `./venv/bin/python scripts/gen_tool_index.py` (un test falla si queda viejo).

- **{len(rows)} tools** con todos los flags activos. Schema total ≈ **{total_chars:,} chars
  (~{total_chars // 4:,} tokens)** que viajan en CADA llamada al LLM, a precio lleno (no hay
  cache implícito por debajo de 4.096 tokens) → ver [MODELS.md](MODELS.md#6-costo-por-turno-medido).
- **Riesgo**: LOW ejecuta solo · MEDIUM/HIGH queda pendiente de confirmación
  (`friday/agent/permissions.py`). `—` = tool de lectura directa (no pasa por el gate).
- `param?` = opcional. La descripción es la 1ra línea del docstring (lo único que ve el
  modelo además de los `Args:`) → mantenerla corta y precisa.

| Tool | Descripción (lo que ve el LLM) | Riesgo | Tags | Disponible | Fuente | Chars |
|---|---|---|---|---|---|---|
"""
    return header + "\n".join(rows) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != content:
            print("docs/TOOLS.md desactualizado: correr scripts/gen_tool_index.py")
            return 1
        return 0
    OUT.write_text(content, encoding="utf-8")
    print(f"Escrito {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
