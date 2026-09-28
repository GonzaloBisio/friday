"""Tests para friday.core.brain — FridayBrain con SDK de Gemini mockeado.

Actualizado para modelo adaptativo y persistencia de chat (ChatResult).
"""

from unittest.mock import MagicMock, patch

import pytest

from friday.collectors.gemini_usage import GeminiTracker
from friday.config import settings
from friday.core.brain import FridayBrain, ChatResult, _extract_text, MAX_TOOL_ROUNDS
from friday.core.tools_registry import ToolsRegistry


def _make_text_response(text: str, tokens_in: int = 10, tokens_out: int = 5):
    part = MagicMock()
    part.function_call = None
    part.text = text

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    usage = MagicMock()
    usage.prompt_token_count = tokens_in
    usage.candidates_token_count = tokens_out

    response = MagicMock()
    response.candidates = [candidate]
    response.usage_metadata = usage
    return response


def _make_fc_response(name: str, args: dict, tokens_in: int = 10, tokens_out: int = 5):
    fc = MagicMock()
    fc.name = name
    fc.args = args

    part = MagicMock()
    part.function_call = fc
    part.text = None

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    usage = MagicMock()
    usage.prompt_token_count = tokens_in
    usage.candidates_token_count = tokens_out

    response = MagicMock()
    response.candidates = [candidate]
    response.usage_metadata = usage
    return response


@pytest.fixture()
def tracker():
    return GeminiTracker()


@pytest.fixture()
def registry():
    reg = ToolsRegistry()

    def sumar(a: int, b: int) -> str:
        """Suma dos números."""
        return str(a + b)

    def consultar_metricas(source: str, name: str | None = None,
                           horas: int = 24, limit: int = 50) -> str:
        return '[{"value": 42}]'

    reg.register(sumar)
    reg.register(consultar_metricas)
    return reg


@pytest.fixture()
def brain(registry, tracker):
    with patch("friday.core.brain.genai") as mock_genai:
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        b = FridayBrain(
            registry=registry,
            api_key="fake-key",
            model="gemini-2.5-flash",
            tracker=tracker,
        )
        b._mock_client = mock_client
        yield b


class TestBrainTextResponse:
    def test_simple_text_response(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("Hola, soy FRIDAY")
        result = brain.chat("Hola")
        assert isinstance(result, ChatResult)
        assert result.text == "Hola, soy FRIDAY"
        assert result.model == settings.gemini_model_fast

    def test_tracks_usage(self, brain, tracker):
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok", tokens_in=100, tokens_out=50)
        brain.chat("test")
        totals = tracker.totals
        assert totals["tokens_in"] == 100
        assert totals["tokens_out"] == 50
        assert totals["requests"] == 1

    def test_history_grows(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("resp")
        brain.chat("msg1")
        assert len(brain.history) == 2  # user + assistant


class TestBrainFunctionCalling:
    def test_executes_tool_and_returns_text(self, brain):
        fc_resp = _make_fc_response("sumar", {"a": 3, "b": 7})
        text_resp = _make_text_response("El resultado es 10")
        brain._mock_client.models.generate_content.side_effect = [fc_resp, text_resp]

        result = brain.chat("Sumá 3 + 7")
        assert "10" in result.text
        assert brain._mock_client.models.generate_content.call_count == 2

    def test_tracks_usage_for_each_round(self, brain, tracker):
        fc_resp = _make_fc_response("sumar", {"a": 1, "b": 2}, tokens_in=20, tokens_out=10)
        text_resp = _make_text_response("3", tokens_in=30, tokens_out=15)
        brain._mock_client.models.generate_content.side_effect = [fc_resp, text_resp]

        result = brain.chat("1+2")
        totals = tracker.totals
        assert totals["requests"] == 2
        assert totals["tokens_in"] == 50
        assert totals["tokens_out"] == 25
        assert result.tokens_in == 50
        assert result.tokens_out == 25

    def test_tool_error_continues(self, brain):
        fc_resp = _make_fc_response("inexistente", {})
        text_resp = _make_text_response("No pude ejecutar eso")
        brain._mock_client.models.generate_content.side_effect = [fc_resp, text_resp]

        result = brain.chat("hacé algo")
        assert brain._mock_client.models.generate_content.call_count == 2

    def test_max_rounds_limit(self, brain):
        fc_resp = _make_fc_response("sumar", {"a": 1, "b": 1})
        brain._mock_client.models.generate_content.return_value = fc_resp

        result = brain.chat("loop infinito")
        assert "límite" in result.text
        assert brain._mock_client.models.generate_content.call_count == MAX_TOOL_ROUNDS


class TestBrainReset:
    def test_reset_clears_history(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok")
        brain.chat("msg")
        assert len(brain.history) > 0
        brain.reset()
        assert len(brain.history) == 0


class TestBrainNoUsageMetadata:
    def test_handles_none_usage(self, brain, tracker):
        resp = _make_text_response("ok")
        resp.usage_metadata = None
        brain._mock_client.models.generate_content.return_value = resp
        brain.chat("test")
        assert tracker.totals["requests"] == 0


class TestAdaptiveModel:
    def test_explicit_flash_model(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok")
        result = brain.chat("cpu status", model="flash")
        assert result.model == settings.gemini_model_fast

    def test_explicit_pro_model(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok")
        result = brain.chat("explícame la teoría de la relatividad", model="pro")
        assert result.model == settings.gemini_model_reasoning

    def test_auto_classifies_short_metric_query_as_flash(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("42%")
        result = brain.chat("cómo viene la cpu")
        assert result.model == settings.gemini_model_fast

    def test_auto_classifies_long_message_as_balanced(self, brain):
        # AUTO nunca debe escalar a pro (free tier ínfimo → 429). Mensaje largo
        # va al escalón balanceado (2.5-flash). Pro solo bajo pedido explícito.
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok")
        long_msg = "Necesito que analices " + "el rendimiento del sistema " * 10
        result = brain.chat(long_msg)
        assert result.model == settings.gemini_model_balanced
        assert result.model != settings.gemini_model_reasoning

    def test_auto_defaults_to_flash(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok")
        result = brain.chat("hola")
        assert result.model == settings.gemini_model_fast


class TestQuotaFallback:
    """Cuando Gemini se queda sin cuota (429), FRIDAY no debe quedar muda:
    degrada a Ollama local en vez de propagar el error."""

    def _quota_error(self):
        from google.genai import errors
        return errors.ClientError(
            429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED", "code": 429}}
        )

    def test_429_falls_back_to_ollama(self, brain):
        brain._mock_client.models.generate_content.side_effect = self._quota_error()
        with patch("friday.core.ollama_brain.OllamaBrain") as mock_ollama_cls:
            mock_ollama_cls.return_value.reply.return_value = ChatResult(
                text="Respondo local, sir.", model="qwen2.5:7b",
            )
            result = brain.chat("cómo viene la cpu")
        assert result.text == "Respondo local, sir."
        assert result.model == "qwen2.5:7b"
        # Contexto compartido: continúa el hilo con reply() (no re-agrega el user).
        mock_ollama_cls.return_value.reply.assert_called_once_with()
        # Y se le pasa el MISMO repo + sesión: así carga la conversación de la DB.
        ckw = mock_ollama_cls.call_args.kwargs
        assert ckw["chat_repo"] is brain._chat_repo
        assert ckw["session_id"] == brain._session_id

    def test_non_429_client_error_propagates(self, brain):
        from google.genai import errors
        bad_request = errors.ClientError(
            400, {"error": {"message": "bad", "status": "INVALID_ARGUMENT", "code": 400}}
        )
        brain._mock_client.models.generate_content.side_effect = bad_request
        with pytest.raises(errors.ClientError):
            brain.chat("hola")


class TestHistoryWindow:
    """La ventana de historial acota los tokens: el brain es singleton y sin
    techo el contexto crece sin parar. Recorta en bordes de turno."""

    def test_trim_keeps_last_n_turns(self, brain):
        from google.genai import types
        brain._history = []
        for i in range(20):
            brain._history.append(
                types.Content(role="user", parts=[types.Part(text=f"q{i}")])
            )
            brain._history.append(
                types.Content(role="model", parts=[types.Part(text=f"a{i}")])
            )
        brain._trim_history()
        starts = [c for c in brain._history if c.role == "user"]
        assert len(starts) == settings.chat_history_window
        assert starts[0].parts[0].text == f"q{20 - settings.chat_history_window}"

    def test_trim_cuts_on_turn_boundary_not_mid_tool(self, brain):
        from google.genai import types
        brain._history = []
        for i in range(20):
            brain._history.append(
                types.Content(role="user", parts=[types.Part(text=f"q{i}")])
            )
            brain._history.append(types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(name="t", args={}))],
            ))
            brain._history.append(types.Content(
                role="user",
                parts=[types.Part(function_response=types.FunctionResponse(
                    name="t", response={"result": "x"}))],
            ))
            brain._history.append(
                types.Content(role="model", parts=[types.Part(text=f"a{i}")])
            )
        brain._trim_history()
        first = brain._history[0]
        # Nunca arrancamos en un function_response huérfano: el primer elemento
        # es un mensaje de usuario CON texto (un borde de turno real).
        assert first.role == "user"
        assert first.parts[0].text is not None

    def test_no_trim_when_under_window(self, brain):
        from google.genai import types
        brain._history = [
            types.Content(role="user", parts=[types.Part(text="hola")]),
            types.Content(role="model", parts=[types.Part(text="buenas")]),
        ]
        brain._trim_history()
        assert len(brain._history) == 2


class TestCompose:
    """compose() es one-shot: genera texto sin tocar el historial ni persistir.
    Lo usan los rituales (Pilar 2) para no contaminar la charla del usuario."""

    def test_returns_text(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("Morning, sir.")
        assert brain.compose("brief me") == "Morning, sir."

    def test_does_not_touch_history(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok")
        before = len(brain._history)
        brain.compose("brief me")
        assert len(brain._history) == before  # one-shot: historial intacto

    def test_tracks_usage(self, brain, tracker):
        brain._mock_client.models.generate_content.return_value = _make_text_response(
            "ok", tokens_in=40, tokens_out=12,
        )
        brain.compose("brief me")
        assert tracker.totals["tokens_in"] == 40
        assert tracker.totals["tokens_out"] == 12


class TestExtractText:
    def test_extracts_text_from_parts(self):
        part = MagicMock()
        part.text = "hola"
        content = MagicMock()
        content.parts = [part]
        assert _extract_text(content) == "hola"

    def test_returns_fallback_when_no_text(self):
        content = MagicMock()
        content.parts = []
        assert _extract_text(content) == "(sin respuesta)"

    def test_handles_none_parts(self):
        content = MagicMock()
        content.parts = None
        assert _extract_text(content) == "(sin respuesta)"


class TestThinkingConfig:
    """3.x no permite apagar el thinking: se usa thinking_level; 2.x usa budget."""

    def test_gemini3_uses_thinking_level(self, brain, monkeypatch):
        monkeypatch.setattr(settings, "gemini_thinking_levels", {"gemini-3.6-flash": "minimal"})
        cfg = brain._thinking_for("gemini-3.6-flash")
        assert cfg.thinking_level.value == "MINIMAL"
        assert cfg.thinking_budget is None

    def test_gemini3_unlisted_uses_model_default(self, brain, monkeypatch):
        monkeypatch.setattr(settings, "gemini_thinking_levels", {})
        assert brain._thinking_for("gemini-3.8-flash") is None

    def test_legacy_flash_disables_thinking_with_budget(self, brain):
        cfg = brain._thinking_for("gemini-2.5-flash")
        assert cfg.thinking_budget == 0


class TestStablePrefix:
    """El system prompt no debe cambiar minuto a minuto (cache implícito)."""

    def test_system_instruction_has_no_clock_time(self, brain):
        import re
        instr = brain._build_system_instruction()
        assert not re.search(r"\d{2}:\d{2}", instr)
        assert "Today is" in instr

    def test_user_message_carries_time_note(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok")
        brain.chat("hola")
        first = brain.history[0]
        assert first.parts[0].text.startswith("hola\n\n[local time ")

    def test_old_function_responses_are_compacted(self, brain, monkeypatch):
        from google.genai import types
        monkeypatch.setattr(settings, "tool_result_history_chars", 40)
        brain._history = [
            types.Content(role="user", parts=[types.Part(text="leé")]),
            types.Content(role="user", parts=[types.Part(
                function_response=types.FunctionResponse(
                    name="leer_pagina", response={"result": "y" * 3000}),
            )]),
        ]
        brain._compact_old_tool_results()
        result = brain._history[1].parts[0].function_response.response["result"]
        assert len(result) < 150 and "recortado" in result
