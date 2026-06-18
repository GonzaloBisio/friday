"""Cliente Gemini con function calling — el cerebro de FRIDAY."""

from __future__ import annotations

import logging
from typing import Any

from google import genai
from google.genai import types

from friday.collectors.gemini_usage import GeminiTracker, gemini_tracker
from friday.config import settings
from friday.core.tools_registry import ToolsRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Sos FRIDAY, el asistente personal de Gonzalo. "
    "Respondés en español rioplatense, conciso y directo. "
    "Tenés acceso a métricas del sistema, costos de Gemini y herramientas locales. "
    "Cuando necesités datos, usá las tools disponibles antes de responder. "
    "Si no tenés datos suficientes, decilo honestamente."
)

MAX_TOOL_ROUNDS = 10


class FridayBrain:
    """Orquesta la conversación con Gemini y ejecuta function calls."""

    def __init__(
        self,
        registry: ToolsRegistry,
        *,
        api_key: str | None = None,
        model: str | None = None,
        tracker: GeminiTracker | None = None,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self._client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self._model = model or settings.gemini_model_fast
        self._registry = registry
        self._tracker = tracker or gemini_tracker
        self._system_prompt = system_prompt
        self._history: list[types.Content] = []

    def chat(self, user_message: str) -> str:
        """Envía un mensaje y ejecuta el loop de function calling hasta obtener texto."""
        self._history.append(
            types.Content(role="user", parts=[types.Part(text=user_message)])
        )

        for _ in range(MAX_TOOL_ROUNDS):
            response = self._call_gemini()
            candidate = response.candidates[0]
            self._history.append(candidate.content)

            function_calls = [
                p.function_call for p in candidate.content.parts or []
                if p.function_call is not None
            ]

            if not function_calls:
                return _extract_text(candidate.content)

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

        return "Alcancé el límite de llamadas a tools. Intentá reformular la pregunta."

    def reset(self) -> None:
        """Limpia el historial de conversación."""
        self._history.clear()

    @property
    def history(self) -> list[types.Content]:
        return list(self._history)

    def _call_gemini(self) -> types.GenerateContentResponse:
        tools = self._registry.as_callable_list()
        config = types.GenerateContentConfig(
            system_instruction=self._system_prompt,
            tools=tools if tools else None,
            temperature=0.7,
        )

        response = self._client.models.generate_content(
            model=self._model,
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

    def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        try:
            result = self._registry.execute(name, args)
            logger.info("Tool %s ejecutada OK", name)
            return str(result)
        except Exception as exc:
            logger.error("Error ejecutando tool %s: %s", name, exc)
            return f"Error: {exc}"


def _extract_text(content: types.Content) -> str:
    parts = content.parts or []
    texts = [p.text for p in parts if p.text]
    return "\n".join(texts) if texts else "(sin respuesta)"
