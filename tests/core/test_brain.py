"""Tests para friday.core.brain — FridayBrain con SDK de Gemini mockeado.

Actualizado para modelo adaptativo y persistencia de chat (ChatResult).
"""

from unittest.mock import MagicMock, patch

import pytest

from friday.collectors.gemini_usage import GeminiTracker
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
        assert result.model == "gemini-2.5-flash"

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
        assert result.model == "gemini-2.5-flash"

    def test_explicit_pro_model(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok")
        result = brain.chat("explícame la teoría de la relatividad", model="pro")
        assert result.model == "gemini-2.5-pro"

    def test_auto_classifies_short_metric_query_as_flash(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("42%")
        result = brain.chat("cómo viene la cpu")
        assert result.model == "gemini-2.5-flash"

    def test_auto_classifies_long_message_as_pro(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok")
        long_msg = "Necesito que analices " + "el rendimiento del sistema " * 10
        result = brain.chat(long_msg)
        assert result.model == "gemini-2.5-pro"

    def test_auto_defaults_to_flash(self, brain):
        brain._mock_client.models.generate_content.return_value = _make_text_response("ok")
        result = brain.chat("hola")
        assert result.model == "gemini-2.5-flash"


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
