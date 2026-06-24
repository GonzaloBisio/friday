"""KnowledgeStore — la capa de CONOCIMIENTO de FRIDAY, en archivos markdown.

A diferencia de los repos SQLite (métricas time-series, chat, memorias key-value),
el conocimiento de FRIDAY —research, intel, notas— vive como archivos `.md` en una
carpeta. ¿Por qué markdown y no SQLite? Porque son DOCUMENTOS, no métricas:

  - curables a mano (corregís/anotás lo que FRIDAY junta),
  - portables, greppables y versionables (git) sin depender de la app,
  - el LLM los lee nativo.

Y el día que quieras un visor lindo (Obsidian, p.ej.), apuntás a esta misma carpeta:
cero migración, porque son solo `.md`. Esa portabilidad es justamente la razón de
elegir markdown sobre una tabla.

Organización en disco:  <base>/<category>/<YYYY-MM-DD>.md  (un digest por día y
categoría). Reusable: 'research' hoy; mañana 'projects', 'comms', lo que sea.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path

# Nombres de nota/categoría seguros: sin separadores de ruta (anti path-traversal).
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_HEADING = re.compile(r"^#\s+(.+?)\s*$")


@dataclass(frozen=True)
class KnowledgeNote:
    """Metadatos de una nota de conocimiento (un archivo .md)."""

    category: str
    name: str               # stem del archivo, ej. "2026-06-24"
    title: str              # primer heading '# ...' o el name si no hay
    path: Path
    modified_at: datetime


class KnowledgeStore:
    """Acceso a la carpeta de conocimiento. Crea subdirectorios por categoría on-demand."""

    def __init__(self, base_dir: Path | str) -> None:
        self._base = Path(base_dir)

    # ── Escritura ─────────────────────────────────────────────────────────

    def save_digest(
        self, category: str, content: str, *, date: date_cls | None = None
    ) -> Path:
        """Guarda (o sobreescribe) el digest del día para una categoría.

        Re-correr el mismo día PISA el archivo: el digest representa "lo último que
        junté hoy", no un append infinito. Devuelve la ruta escrita.
        """
        day = (date or datetime.now().date()).isoformat()
        path = self._category_dir(category, create=True) / f"{day}.md"
        path.write_text(content, encoding="utf-8")
        return path

    # ── Lectura ───────────────────────────────────────────────────────────

    def latest(self, category: str) -> KnowledgeNote | None:
        """La nota más reciente de la categoría (por nombre, que es la fecha)."""
        notes = self.list(category, limit=1)
        return notes[0] if notes else None

    def list(self, category: str, limit: int = 30) -> list[KnowledgeNote]:
        """Notas de la categoría, más recientes primero (nombre = fecha → orden lexicográfico)."""
        directory = self._category_dir(category)
        if not directory.is_dir():
            return []
        files = sorted(directory.glob("*.md"), key=lambda p: p.name, reverse=True)
        return [self._note(category, p) for p in files[:limit]]

    def read(self, category: str, name: str) -> str | None:
        """Contenido crudo de una nota por nombre. None si no existe o el nombre es inseguro."""
        if not _SAFE_NAME.match(name or ""):
            return None
        path = self._category_dir(category) / f"{name}.md"
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    # ── Internos ──────────────────────────────────────────────────────────

    def _category_dir(self, category: str, *, create: bool = False) -> Path:
        if not _SAFE_NAME.match(category or ""):
            raise ValueError(f"Categoría inválida: {category!r}")
        directory = self._base / category
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _note(category: str, path: Path) -> KnowledgeNote:
        title = path.stem
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                m = _HEADING.match(line)
                if m:
                    title = m.group(1)
                    break
        except OSError:
            pass
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return KnowledgeNote(
            category=category, name=path.stem, title=title, path=path, modified_at=mtime
        )
