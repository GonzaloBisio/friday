"""Cliente Gemini con function calling — el cerebro de FRIDAY.

Soporta:
- Modelo adaptativo: fast (voz + tools), balanced (consultas largas), lite
  (compose one-shot) y reasoning (solo pedido explícito). IDs en config.py.
- Prefijo estable para el cache implícito de Gemini (ver context_window.py).
- Persistencia de conversaciones via ChatRepository.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from friday.collectors.gemini_usage import GeminiTracker, gemini_tracker
from friday.config import settings
from friday.core.activity import activity_log, format_args
from friday.core.context_window import (
    compact_tool_result,
    day_stamp,
    with_time_note,
)
from friday.core.health import health_tracker
from friday.core.hud import hud_bridge
from friday.core.llm_base import FRIDAY_SYSTEM_PROMPT, ChatResult
from friday.core.tools_registry import ToolsRegistry
from friday.storage.chat_repo import ChatMessage, ChatRepository

logger = logging.getLogger(__name__)

# Mismo prompt que el cerebro Ollama (persona + reglas anti-alucinación/voz).
SYSTEM_PROMPT = FRIDAY_SYSTEM_PROMPT

MAX_TOOL_ROUNDS = 10

# Palabras clave que sugieren consulta simple (métricas, estado) → flash
_SIMPLE_KEYWORDS = [
    "cómo", "cuánto", "cpu", "ram", "disco", "métrica", "métricas",
    "nexcourt", "servicio", "estado", "costo", "gasté", "gasto",
    "uptime", "proceso", "temperatura", "status", "monitor",
]


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
        memory_repo: Any = None,
    ) -> None:
        self._client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self._default_model = model or settings.gemini_model_fast
        self._reasoning_model = settings.gemini_model_reasoning
        self._registry = registry
        self._tracker = tracker or gemini_tracker
        self._system_prompt = system_prompt
        self._memory_repo = memory_repo
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
        hud_bridge.set_context(user_message)  # el "por qué" de los paneles que se abran
        # Resultados de tools de turnos previos → recortados (una sola vez: después
        # el prefijo queda estable y cacheable). El turno nuevo los ve completos.
        self._compact_old_tool_results()
        # La hora viaja en el mensaje (no en el system prompt) para que el prefijo
        # system+tools sea idéntico entre llamadas → cache implícito de Gemini.
        self._history.append(
            types.Content(role="user", parts=[types.Part(text=with_time_note(user_message))])
        )
        # Acota el historial en memoria antes de llamar al modelo: el brain es un
        # singleton y sin esto el input crece sin techo turno a turno.
        self._trim_history()

        # Guardar mensaje del usuario
        self._save_message("user", user_message, model=selected_model)

        # Pilar 6: medimos la latencia de respuesta del cerebro (incluye el path de
        # fallback). El finally garantiza registrarla aunque se propague un error.
        start = time.perf_counter()
        try:
            return self._run_tool_loop(selected_model)
        except genai_errors.ClientError as exc:
            # 429 RESOURCE_EXHAUSTED: se acabó la cuota de Gemini. En vez de quedar
            # mudos, degradamos a Ollama local para esta respuesta. Cualquier otro
            # error de cliente (auth, request inválido) sí debe propagarse.
            if exc.code != 429:
                raise
            logger.warning("Gemini sin cuota (429); fallback a Ollama local.")
            health_tracker.record_fallback()
            return self._fallback_to_ollama(user_message)
        finally:
            health_tracker.record_latency((time.perf_counter() - start) * 1000)

    def _run_tool_loop(self, selected_model: str) -> ChatResult:
        """Loop de function calling contra Gemini. Puede lanzar ClientError."""
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

    def _fallback_to_ollama(self, user_message: str) -> ChatResult:
        """Responde con Ollama local cuando Gemini se queda sin cuota.

        Contexto COMPARTIDO (Fase 2): le pasamos el mismo chat_repo + session_id,
        así Ollama carga la conversación (ya ventaneada) desde la DB —incluido el
        mensaje del usuario que Gemini acaba de guardar— y CONTINÚA el hilo en vez
        de arrancar en blanco. Usamos `reply()` (no `chat()`) para no re-agregar
        ni re-persistir ese mensaje de usuario. Ollama persiste su respuesta; acá
        solo la reflejamos en el historial de Gemini para que el próximo turno en
        la nube tenga continuidad. Sin conversión de formatos: la DB es la fuente
        de verdad neutral y cada cerebro carga desde ahí.

        Degradación acotada: si Gemini cortó tras ejecutar tools en una ronda
        previa, esos resultados intermedios viven solo en memoria de Gemini (no en
        DB), así que Ollama rehace desde el mensaje del usuario. Aceptable para un
        camino de emergencia.
        """
        from friday.core.ollama_brain import OllamaBrain

        local = OllamaBrain(
            registry=self._registry,
            memory_repo=self._memory_repo,
            system_prompt=self._system_prompt,
            chat_repo=self._chat_repo,
            session_id=self._session_id,
        )
        result = local.reply()
        self._history.append(
            types.Content(role="model", parts=[types.Part(text=result.text)])
        )
        return result

    def _compact_old_tool_results(self) -> None:
        """Recorta los function_response ya consumidos por el modelo.

        Se llama al empezar un turno: todo lo que hay en el historial pertenece a
        turnos ANTERIORES, cuyo resultado el modelo ya leyó y resumió en su
        respuesta. Mantener 6K chars de una página por 12 turnos es puro costo.
        """
        limit = settings.tool_result_history_chars
        if limit <= 0:
            return
        for content in self._history:
            for part in content.parts or []:
                fr = getattr(part, "function_response", None)
                if fr is None or not isinstance(fr.response, dict):
                    continue
                result = fr.response.get("result")
                if isinstance(result, str):
                    compacted = compact_tool_result(result, limit)
                    if compacted is not result:
                        fr.response = {**fr.response, "result": compacted}

    def _trim_history(self) -> None:
        """Mantiene solo los últimos N turnos en memoria para acotar tokens.

        Un turno arranca en un mensaje de usuario CON texto (no en un
        function_response, que también es role="user" pero sin texto). Cortamos
        siempre en un borde de turno para no dejar un function_response huérfano
        sin su function_call previa —Gemini rechaza eso—.
        """
        window = settings.chat_history_window
        if window <= 0 or len(self._history) <= window:
            return
        starts = [
            i for i, c in enumerate(self._history)
            if c.role == "user"
            and any(getattr(p, "text", None) for p in (c.parts or []))
        ]
        if len(starts) <= window:
            return
        self._history = self._history[starts[-window]:]

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

        # Mensajes largos (>200 chars) probablemente requieren razonamiento →
        # escalón balanceado (2.5-flash), NO pro. Pro tiene un free tier ínfimo
        # y mandar auto ahí era lo que reventaba la cuota (429). Pro solo bajo
        # pedido explícito (chat model="pro").
        if len(msg_lower) > 200:
            return settings.gemini_model_balanced

        # Default: flash (más barato, cubre el 80% de casos)
        return settings.gemini_model_fast

    def compose(self, prompt: str, *, model: str | None = None) -> str:
        """Genera texto one-shot, SIN historial ni tools. Stateless.

        Pensado para que los rituales y análisis (Pilares 2-3) usen al LLM para
        redactar —briefings, resúmenes— sin contaminar la conversación del
        usuario ni gastar el loop de tools. No toca `self._history` ni persiste.
        Propaga errores (incluido 429): el caller decide el fallback —un briefing
        tiene su propio piso de plantilla determinista—.
        """
        # Sin tools ni historial → alcanza el modelo lite (el más barato).
        used_model = model or settings.gemini_model_lite
        config = types.GenerateContentConfig(
            system_instruction=self._build_system_instruction(),
            max_output_tokens=settings.gemini_max_output_tokens,
            temperature=0.7,
            thinking_config=self._thinking_for(used_model),
        )
        response = self._client.models.generate_content(
            model=used_model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )
        self._track_usage(response, used_model)
        candidates = response.candidates or []
        if not candidates:
            return "(sin respuesta)"
        return _extract_text(candidates[0].content)

    # ── Gemini call ───────────────────────────────────────────────────────

    def _call_gemini(
        self,
        model_override: str | None = None,
    ) -> types.GenerateContentResponse:
        model = model_override or self._default_model
        tools = self._registry.as_callable_list()
        config = types.GenerateContentConfig(
            system_instruction=self._build_system_instruction(),
            tools=tools if tools else None,
            # Manejamos las tools en el loop manual (con logging y gate), no que el
            # SDK las ejecute solo — así controlamos qué corre y lo registramos.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            # Techo = thinking + respuesta. La brevedad de voz la impone el prompt;
            # un techo bajo (200) dejaba la respuesta vacía en 3.x (ver config).
            max_output_tokens=settings.gemini_max_output_tokens,
            temperature=0.7,
            thinking_config=self._thinking_for(model),
        )

        response = self._client.models.generate_content(
            model=model,
            contents=self._history,
            config=config,
        )

        self._track_usage(response, model)
        return response

    def _thinking_for(self, model: str) -> "types.ThinkingConfig | None":
        """Config de thinking según la familia del modelo.

        - 3.x: no se puede apagar; se usa `thinking_level` (minimal/low/...) de
          settings.gemini_thinking_levels. Sin entrada → default del modelo.
        - 2.x (legacy): budget=0 en flash (si no, el pensar vaciaba la respuesta);
          None en el modelo de reasoning.
        """
        if model.startswith("gemini-2"):
            if model == self._reasoning_model or "pro" in model:
                return None
            return types.ThinkingConfig(thinking_budget=0)
        level = settings.gemini_thinking_levels.get(model)
        if not level:
            return None
        return types.ThinkingConfig(thinking_level=level.upper())

    def _build_system_instruction(self) -> str:
        """System prompt + FECHA (no hora) + memoria de Gonzalo.

        Todo lo de acá debe ser estable entre llamadas: es el prefijo que Gemini
        cachea implícitamente (90% off). La hora exacta va en cada mensaje de
        usuario (with_time_note); la fecha cambia una vez por día.
        """
        prompt = f"{self._system_prompt}\n\nToday is {day_stamp()}."
        return prompt + self._memory_block()

    def _memory_block(self) -> str:
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

    def _track_usage(
        self, response: types.GenerateContentResponse, model: str = ""
    ) -> None:
        usage = response.usage_metadata
        if usage is None:
            return
        self._tracker.record(
            tokens_in=usage.prompt_token_count or 0,
            tokens_out=usage.candidates_token_count or 0,
            model=model,
        )

    # ── Tool execution ────────────────────────────────────────────────────

    def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        activity_log.record(name, "running", format_args(args))
        try:
            result = self._registry.execute(name, args)
            logger.info("Tool %s ejecutada OK", name)
            activity_log.record(name, "ok", str(result))
            hud_bridge.tool_result(name, args, result)
            return str(result)
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
            # No arrastramos la sesión entera al contexto: misma ventana que en runtime.
            self._trim_history()
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
