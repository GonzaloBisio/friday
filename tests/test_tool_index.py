"""docs/TOOLS.md debe reflejar el registry real (índice para IAs y humanos)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tool_index_is_up_to_date():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_tool_index.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0, r.stdout + r.stderr
