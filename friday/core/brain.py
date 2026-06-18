"""Cliente Gemini con function calling — el cerebro de FRIDAY.

Soporta:
- Modelo adaptativo: gemini-2.5-flash para consultas simples,
  gemini-2.5-pro para razonamiento complejo.
- Persistencia de conversaciones via ChatRepository.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

from friday.collectors.gemini_usage import GeminiTracker, gemini_tracker
from friday.config import settings
from friday.core.tools_registry import ToolsRegistry
from friday.storage.chat_repo import ChatMessage, ChatRepository

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Sos FRIDAY, el asistente personal de Gonzalo. "
    "Respondés en español rioplatense, conciso y directo. "
    "Tenés acceso a métricas del sistema, costos de Gemini y herramientas locales. "
    "Cuando necesités datos, usá las tools disponibles antes de responder. "
    "Si no tenés datos suficientes, decilo honestamente."
)

MAX_TOOL_ROUNDS = 10

# Palabras clave que sugieren consulta simple (métricas, estado) → flash
_SIMPLE_KEYWORDS = [
    "cómo", "cuánto", "cpu", "ram", "disco", "métrica", "métricas",
    "nexcourt", "servicio", "estado", "costo", "gasté", "gasto",
    "uptime", "proceso", "temperatura", "status", "monitor",
]


@dataclass
class ChatResult:
    """Resultado de una llamada a chat()."""
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0


class FridayBrain:
    """Orquesta la conversación con Gemini y ejecuta function calls.

    Soporta modelo adaptativo: usa flash por defecto, pro para consultas complejas.
    Persiste el historial en SQLite via ChatRepository.
    """

    def __init__(
        self,
        registry: ToolsRegistry,
        *,
        api_key: str | None = None,
        model: str | None = None,
        tracker: GeminiTracker | None = None,
        system_prompt: str = SYSTEM_PROMPT,
        chat_repo: ChatRepository | None = None,
        session_id: str | None = None,
    ) -> None:
        self._client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self._default_model = model or settings.gemini_model_fast
        self._reasoning_model = settings.gemini_model_reasoning
        self._registry = registry
        self._tracker = tracker or gemini_tracker
        self._system_prompt = system_prompt
        self._history: list[types.Content] = []

        # Persistencia
        self._chat_repo = chat_repo
        self._session_id = session_id

        # Cargar historial previo si hay repo configurado
        if self._chat_repo and self._session_id:
            self._load_history()

    # ── Chat API ──────────────────────────────────────────────────────────

    def chat(self, user_message: str, model: str = "auto") -> ChatResult:
        """Envía un mensaje y ejecuta el loop de function calling.

        Args:
            user_message: Texto del usuario.
            model: "auto" (clasifica), "flash", o "pro".

        Returns:
            ChatResult con respuesta, modelo usado y tokens.
        """
        selected_model = self._select_model(user_message, model)
        self._history.append(
            types.Content(role="user", parts=[types.Part(text=user_message)])
        )

        # Guardar mensaje del usuario
        self._save_message("user", user_message, model=selected_model)

        total_tokens_in = 0
        total_tokens_out = 0

        for _ in range(MAX_TOOL_ROUNDS):
            response = self._call_gemini(model_override=selected_model)
            candidate = response.candidates[0]
            self._history.append(candidate.content)

            usage = response.usage_metadata
            if usage:
                total_tokens_in += usage.prompt_token_count or 0
                total_tokens_out += usage.candidates_token_count or 0

            function_calls = [
                p.function_call for p in candidate.content.parts or []
                if p.function_call is not None
            ]

            if not function_calls:
                text = _extract_text(candidate.content)
                self._save_message(
                    "assistant", text,
                    model=selected_model,
                    tokens_in=total_tokens_in,
                    tokens_out=total_tokens_out,
                )
                return ChatResult(
                    text=text,
                    model=selected_model,
                    tokens_in=total_tokens_in,
                    tokens_out=total_tokens_out,
                )

            response_parts = []
            for fc in function_calls:
                result = self._execute_tool(fc.name, dict(fc.args) if fc.args else {})
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": result},
                        )
                    )
                )

            self._history.append(
                types.Content(role="user", parts=response_parts)
            )

        fallback = "Alcancé el límite de llamadas a tools. Intentá reformular la pregunta."
        self._save_message("assistant", fallback, model=selected_model)
        return ChatResult(text=fallback, model=selected_model)

    def reset(self) -> None:
        """Limpia el historial en memoria (no borra de DB)."""
        self._history.clear()

    def new_session(self, title: str = "") -> str | None:
        """Crea una nueva sesión y carga historial vacío. Retorna el ID."""
        if not self._chat_repo:
            return None
        self._history.clear()
        self._session_id = self._chat_repo.create_session(title)
        return self._session_id

    def switch_session(self, session_id: str) -> None:
        """Cambia a una sesión existente y carga su historial."""
        if not self._chat_repo:
            return
        self._session_id = session_id
        self._history.clear()
        self._load_history()

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def history(self) -> list[types.Content]:
        return list(self._history)

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def model(self) -> str:
        return self._default_model

    # ── Model selection ───────────────────────────────────────────────────

    def _select_model(self, message: str, requested: str) -> str:
        """Determina qué modelo usar basado en el mensaje y preferencia."""
        if requested == "flash":
            return settings.gemini_model_fast
        if requested == "pro":
            return settings.gemini_model_reasoning
        # "auto": clasificar
        return self._classify(message)

    def _classify(self, message: str) -> str:
        """Clasifica la complejidad del mensaje para elegir modelo.

        Heurística simple: si el mensaje es corto y usa palabras clave
        de consulta de métricas/estado → flash. Si es largo o parece
        requerir razonamiento → pro.
        """
        msg_lower = message.lower().strip()

        # Mensajes muy cortos con palabras clave → flash
        if len(msg_lower) < 100:
            for kw in _SIMPLE_KEYWORDS:
                if kw in msg_lower:
                    return settings.gemini_model_fast

        # Mensajes largos (>200 chars) probablemente requieren razonamiento → pro
        if len(msg_lower) > 200:
            return settings.gemini_model_reasoning

        # Default: flash (más barato, cubre el 80% de casos)
        return settings.gemini_model_fast

    # ── Gemini call ───────────────────────────────────────────────────────

    def _call_gemini(
        self,
        model_override: str | None = None,
    ) -> types.GenerateContentResponse:
        model = model_override or self._default_model
        tools = self._registry.as_callable_list()
        config = types.GenerateContentConfig(
            system_instruction=self._system_prompt,
            tools=tools if tools else None,
            temperature=0.7,
        )

        response = self._client.models.generate_content(
            model=model,
            contents=self._history,
            config=config,
        )

        self._track_usage(response)
        return response

    def _track_usage(self, response: types.GenerateContentResponse) -> None:
        usage = response.usage_metadata
        if usage is None:
            return
        self._tracker.record(
            tokens_in=usage.prompt_token_count or 0,
            tokens_out=usage.candidates_token_count or 0,
        )

    # ── Tool execution ────────────────────────────────────────────────────

    def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        try:
            result = self._registry.execute(name, args)
            logger.info("Tool %s ejecutada OK", name)
            return str(result)
        except Exception as exc:
            logger.error("Error ejecutando tool %s: %s", name, exc)
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
        """Carga el historial desde la DB y lo convierte a formato Gemini."""
        if not self._chat_repo or not self._session_id:
            return
        try:
            messages = self._chat_repo.load_session(self._session_id)
            for msg in messages:
                if msg.role == "user":
                    self._history.append(
                        types.Content(role="user", parts=[types.Part(text=msg.content)])
                    )
                elif msg.role == "assistant":
                    self._history.append(
                        types.Content(role="model", parts=[types.Part(text=msg.content)])
                    )
            if messages:
                logger.info(
                    "Historial cargado: %d mensajes de sesión %s",
                    len(messages), self._session_id[:8],
                )
        except Exception:
            logger.exception("Error cargando historial")


def _extract_text(content: types.Content) -> str:
    parts = content.parts or []
    texts = [p.text for p in parts if p.text]
    return "\n".join(texts) if texts else "(sin respuesta)"
