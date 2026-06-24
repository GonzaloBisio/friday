"""Cerebro local de FRIDAY basado en Ollama — sin costo de tokens.

v2: conversación + tool calling (function calling de Ollama).
Expone la misma interfaz pública que FridayBrain para ser
intercambiable vía el factory.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import httpx

from friday.config import settings
from friday.core.activity import activity_log, format_args
from friday.core.health import health_tracker
from friday.core.llm_base import FRIDAY_SYSTEM_PROMPT, ChatResult
from friday.storage.chat_repo import ChatMessage, ChatRepository

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = FRIDAY_SYSTEM_PROMPT

_OFFLINE_MSG = (
    "No pude contactar al cerebro local (Ollama) en {host}. "
    "¿Está corriendo? Verificá con `ollama serve`."
)

MAX_TOOL_ROUNDS = 10


class OllamaBrain:
    """Cerebro local vía Ollama. Misma interfaz pública que FridayBrain.

    v2: conversación + tool calling. Soporta el loop de function calling
    de Ollama (equivalente al de Gemini en FridayBrain). Persiste el
    historial en SQLite via ChatRepository.
    """

    def __init__(
        self,
        registry: Any = None,
        *,
        host: str | None = None,
        model: str | None = None,
        system_prompt: str = SYSTEM_PROMPT,
        chat_repo: ChatRepository | None = None,
        session_id: str | None = None,
        timeout: float | None = None,
        memory_repo: Any = None,
    ) -> None:
        self._host = (host or settings.ollama_host).rstrip("/")
        self._model = model or settings.ollama_model
        self._system_prompt = system_prompt
        self._timeout = timeout if timeout is not None else settings.ollama_timeout_seconds
        self._registry = registry
        self._memory_repo = memory_repo
        self._history: list[dict[str, Any]] = []

        self._chat_repo = chat_repo
        self._session_id = session_id
        if self._chat_repo and self._session_id:
            self._load_history()

    # ── Chat API ──────────────────────────────────────────────────────────

    def chat(self, user_message: str, model: str = "auto") -> ChatResult:
        """Envía un mensaje al modelo local y devuelve la respuesta.

        El parámetro `model` se acepta por compatibilidad con FridayBrain
        (flash/pro/auto), pero Ollama usa un único modelo configurado.

        Si hay tools registradas, entra en loop de function calling:
        ejecuta tools pedidas por el modelo y reintenta hasta obtener
        una respuesta final (o MAX_TOOL_ROUNDS).
        """
        self._history.append({"role": "user", "content": user_message})
        # Acota el historial: el brain es singleton, sin esto el contexto crece sin techo.
        self._trim_history()
        self._save_message("user", user_message, model=self._model)
        # Pilar 6: latencia del camino primario. reply() NO se mide acá porque
        # también lo usa el fallback de Gemini, que ya cronometra en FridayBrain.chat.
        start = time.perf_counter()
        try:
            return self.reply()
        finally:
            health_tracker.record_latency((time.perf_counter() - start) * 1000)

    def reply(self) -> ChatResult:
        """Genera una respuesta a partir del historial ACTUAL.

        No agrega ni persiste un mensaje de usuario: asume que el último turno
        ya está en `self._history`. Lo usa el fallback de Gemini (FridayBrain)
        para continuar la conversación con el contexto compartido vía la DB, sin
        duplicar el mensaje del usuario que Gemini ya guardó.
        """
        # Construir tool schemas si hay registry con tools
        tools_schema = None
        if self._registry and len(self._registry) > 0:
            from friday.core.tool_schema import build_tools_schema
            tools_schema = build_tools_schema(self._registry)

        total_tokens_in = 0
        total_tokens_out = 0

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                data = self._call_ollama(tools_schema)
            except httpx.HTTPError as exc:
                logger.error("Error contactando Ollama: %s", exc)
                return ChatResult(
                    text=_OFFLINE_MSG.format(host=self._host), model=self._model,
                )

            message = data.get("message", {})
            tokens_in = int(data.get("prompt_eval_count", 0) or 0)
            tokens_out = int(data.get("eval_count", 0) or 0)
            total_tokens_in += tokens_in
            total_tokens_out += tokens_out

            tool_calls = message.get("tool_calls", []) or []

            if not tool_calls:
                # Respuesta final sin tool calls
                text = (message.get("content") or "").strip() or "(sin respuesta)"
                self._history.append({"role": "assistant", "content": text})
                self._save_message(
                    "assistant", text, model=self._model,
                    tokens_in=total_tokens_in, tokens_out=total_tokens_out,
                )
                return ChatResult(
                    text=text, model=self._model,
                    tokens_in=total_tokens_in, tokens_out=total_tokens_out,
                )

            # El modelo pidió ejecutar tools
            self._history.append({
                "role": "assistant",
                "content": message.get("content", ""),
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {}) or {}
                result = self._execute_tool(name, args)
                self._history.append({"role": "tool", "content": str(result)})

        # Límite de rondas
        fallback = "I've reached the tool call limit. Please try again, sir."
        self._save_message("assistant", fallback, model=self._model)
        return ChatResult(text=fallback, model=self._model)

    def compose(self, prompt: str, *, model: str | None = None) -> str:
        """Genera texto one-shot, SIN historial ni tools. Stateless.

        Equivalente local de FridayBrain.compose: rituales/análisis (Pilares 2-3)
        redactan con el LLM sin tocar `self._history` ni persistir. Propaga
        httpx.HTTPError si Ollama no responde: el caller decide el fallback.
        """
        now = datetime.now().strftime("%A %d %B %Y, %H:%M")
        messages = [
            {"role": "system", "content": f"{self._system_prompt}\n\nCurrent date/time: {now}."},
            {"role": "user", "content": prompt},
        ]
        body = {
            "model": model or self._model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "options": {"num_predict": 220, "temperature": 0.7},
        }
        resp = httpx.post(f"{self._host}/api/chat", json=body, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("message", {}).get("content") or "").strip() or "(sin respuesta)"

    def _trim_history(self) -> None:
        """Mantiene solo los últimos N turnos en memoria para acotar tokens.

        Un turno arranca en un mensaje role="user". Los resultados de tools son
        role="tool", así que cortar en un borde de usuario no deja tool messages
        huérfanos de su assistant+tool_calls previo.
        """
        window = settings.chat_history_window
        if window <= 0 or len(self._history) <= window:
            return
        starts = [i for i, m in enumerate(self._history) if m.get("role") == "user"]
        if len(starts) <= window:
            return
        self._history = self._history[starts[-window]:]

    def reset(self) -> None:
        """Limpia el historial en memoria (no borra de DB)."""
        self._history.clear()

    def new_session(self, title: str = "") -> str | None:
        if not self._chat_repo:
            return None
        self._history.clear()
        self._session_id = self._chat_repo.create_session(title)
        return self._session_id

    def switch_session(self, session_id: str) -> None:
        if not self._chat_repo:
            return
        self._session_id = session_id
        self._history.clear()
        self._load_history()

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def model(self) -> str:
        return self._model

    # ── Ollama call ───────────────────────────────────────────────────────

    def _build_messages(self) -> list[dict[str, Any]]:
        """Construye la lista de mensajes con fecha/hora (y memoria) en el system prompt."""
        now = datetime.now().strftime("%A %d %B %Y, %H:%M")
        dated_prompt = f"{self._system_prompt}\n\nCurrent date/time: {now}."
        dated_prompt += self._memory_block()
        return [{"role": "system", "content": dated_prompt}, *self._history]

    def _memory_block(self) -> str:
        """Bloque con lo que FRIDAY recuerda de Gonzalo, para inyectar al prompt.

        Esto es el "aprendizaje" de la Fase A: el conocimiento no vive en los pesos
        del modelo sino en SQLite, y se le da al modelo como contexto cada turno.
        """
        if not self._memory_repo:
            return ""
        try:
            memories = self._memory_repo.all(limit=settings.memory_context_limit)
        except Exception:
            logger.exception("Error leyendo la memoria")
            return ""
        if not memories:
            return ""
        lines = "\n".join(f"- {m.value}" for m in memories)
        return (
            "\n\nWhat you remember about Gonzalo (use it naturally when relevant; "
            "do not recite it back unprompted):\n" + lines
        )

    def _call_ollama(
        self, tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Llama a Ollama /api/chat. Opcionalmente pasa tools para function calling."""
        messages = self._build_messages()
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            # Mantener el modelo en VRAM 30 min evita recargas lentas entre turnos.
            "keep_alive": "30m",
            # num_predict: techo de tokens. 150 da 2-3 frases completas sin cortar
            # la respuesta a la mitad (80 las clipeaba). temperature 0.8 le da chispa
            # conversacional sin desbocarse.
            "options": {"num_predict": 150, "temperature": 0.8},
        }
        if tools:
            body["tools"] = tools

        resp = httpx.post(
            f"{self._host}/api/chat",
            json=body,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Ejecuta una tool del registry y devuelve el resultado como string."""
        if not self._registry:
            return "Error: no tools available."
        activity_log.record(name, "running", format_args(args))
        try:
            result = self._registry.execute(name, args)
            logger.info("Tool %s ejecutada OK", name)
            activity_log.record(name, "ok", str(result))
            return str(result)
        except KeyError:
            logger.warning("Tool desconocida: %s", name)
            activity_log.record(name, "error", f"unknown tool '{name}'")
            return f"Error: unknown tool '{name}'."
        except Exception as exc:
            logger.error("Error ejecutando tool %s: %s", name, exc)
            activity_log.record(name, "error", str(exc))
            return f"Error: {exc}"

    # ── Persistence ───────────────────────────────────────────────────────

    def _save_message(
        self,
        role: str,
        content: str,
        model: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        if not self._chat_repo or not self._session_id:
            return
        try:
            msg = ChatMessage(
                session_id=self._session_id,
                role=role,
                content=content,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
            self._chat_repo.save_message(msg)
        except Exception:
            logger.exception("Error guardando mensaje en historial")

    def _load_history(self) -> None:
        if not self._chat_repo or not self._session_id:
            return
        try:
            for msg in self._chat_repo.load_session(self._session_id):
                if msg.role in ("user", "assistant"):
                    self._history.append({"role": msg.role, "content": msg.content})
            # Misma ventana que en runtime: no arrastrar la sesión entera al contexto.
            self._trim_history()
        except Exception:
            logger.exception("Error cargando historial")
