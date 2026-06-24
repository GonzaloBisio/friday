"""ResearchService — la capa de INTELIGENCIA de FRIDAY (research diario).

El video del "agentic OS" llama "second brain" a un corpus de conocimiento que se
auto-alimenta con intel externa fresca. FRIDAY ya tenía la telemetría (collectors →
SQLite); esto agrega lo que faltaba: CONOCIMIENTO. Un servicio agendado junta
novedades por tema y las escribe como un digest markdown en el KnowledgeStore.

Patrón: es un SERVICIO agendado, NO un Collector. Los Collector devuelven
MetricPoints time-series → SQLite; esto produce DOCUMENTOS → archivos .md. Mismo
molde que BriefingService (un job en app.py, no en _register_collectors).

Disciplina (la regla de oro del sistema): el LLM es nice-to-have, NUNCA el piso.
Acá el digest es 100% DETERMINISTA —titulares + links reales + snippets—, así que
nunca se cae ni alucina. La SÍNTESIS hablada la hace el cerebro on-demand cuando
Gonzalo pregunta "¿qué hay nuevo?", leyendo este digest con `consultar_research`
(ahí sí brilla su persona de voz). Separar las dos cosas es lo que lo hace robusto.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime

from friday.integrations.web_research import buscar_web_items

logger = logging.getLogger(__name__)

CATEGORY = "research"
# Techo del snippet por ítem en el markdown (legible sin inflar el archivo).
_MAX_SNIPPET = 240


@dataclass(frozen=True)
class ResearchTopic:
    """Un tema a seguir: un nombre lindo + la consulta real de búsqueda."""

    name: str
    query: str
    max_results: int = 5


class ResearchService:
    """Junta novedades por tema y escribe un digest markdown diario."""

    def __init__(self, store, topics, *, search=buscar_web_items) -> None:
        self._store = store
        self._topics = list(topics)
        self._search = search  # inyectable para testear sin red

    # ── Orquestación ──────────────────────────────────────────────────────

    def run(self, *, date: date_cls | None = None) -> str:
        """Junta, arma el digest y lo persiste. Devuelve la ruta escrita."""
        gathered = self.gather()
        text = self.compose(gathered, date=date)
        path = self._store.save_digest(CATEGORY, text, date=date)
        logger.info("Research: digest escrito en %s (%d temas)", path, len(gathered))
        return str(path)

    # ── Recolección (red, best-effort) ────────────────────────────────────

    def gather(self) -> list[tuple[ResearchTopic, list[dict]]]:
        """Busca cada tema. Un tema que falle queda con lista vacía — NUNCA corta el resto."""
        out: list[tuple[ResearchTopic, list[dict]]] = []
        for topic in self._topics:
            try:
                items = self._search(topic.query, topic.max_results)
            except Exception:
                logger.warning("Research: falló la búsqueda de '%s'", topic.name, exc_info=True)
                items = []
            out.append((topic, items))
        return out

    # ── Composición (markdown determinista, sin LLM) ──────────────────────

    def compose(
        self,
        gathered: list[tuple[ResearchTopic, list[dict]]],
        *,
        date: date_cls | None = None,
    ) -> str:
        """Arma el digest markdown. Puro y testeable (sin red)."""
        day = (date or datetime.now().date()).isoformat()
        total = sum(len(items) for _, items in gathered)
        lines = [
            f"# Research — {day}",
            "",
            f"> {total} novedades en {len(gathered)} temas · juntadas por FRIDAY",
            "",
        ]
        for topic, items in gathered:
            lines.append(f"## {topic.name}")
            lines.append("")
            if not items:
                lines.append("_Sin resultados ahora._")
                lines.append("")
                continue
            for it in items:
                title = it.get("title") or "(sin título)"
                url = it.get("url") or ""
                body = (it.get("body") or "").strip()
                if len(body) > _MAX_SNIPPET:
                    body = body[:_MAX_SNIPPET].rstrip() + "…"
                head = f"- [{title}]({url})" if url else f"- {title}"
                lines.append(head)
                if body:
                    lines.append(f"  {body}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def register_research_tools(tools_reg, store) -> None:
    """Expone el digest de research como tool de lectura del LLM (LOW)."""

    def consultar_research() -> str:
        """Devuelve el último digest de research que FRIDAY juntó (novedades de IA/tech y backend).

        Usá esto cuando Gonzalo pregunte qué hay nuevo, las novedades del día, o sobre
        tendencias de IA/tech/backend. Trae titulares y links REALES ya recolectados —
        resumí lo más relevante con tus palabras, no inventes.

        Returns:
            El digest markdown más reciente (puede venir recortado), o un aviso si todavía no hay.
        """
        note = store.latest(CATEGORY)
        if note is None:
            return "Todavía no junté research, sir. El digest se arma solo cada mañana."
        text = store.read(CATEGORY, note.name) or ""
        # Techo para no inflar el contexto del modelo local (CPU).
        return text[:4000]

    tools_reg.register(consultar_research)
