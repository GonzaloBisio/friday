"""Tests para friday.core.ollama_brain — OllamaBrain con HTTP mockeado (respx)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import respx

from friday.core.llm_base import ChatResult
from friday.core.ollama_brain import OllamaBrain

HOST = "http://localhost:11434"
CHAT_URL = f"{HOST}/api/chat"


def _ok_response(content: str = "Hola, soy FRIDAY.", pin: int = 12, pout: int = 8):
    return httpx.Response(
        200,
        json={
            "message": {"role": "assistant", "content": content},
            "prompt_eval_count": pin,
            "eval_count": pout,
        },
    )


# ── Happy path ─────────────────────────────────────────────────────────────

@respx.mock
def test_chat_returns_text_and_tokens():
    route = respx.post(CHAT_URL).mock(return_value=_ok_response())
    brain = OllamaBrain(host=HOST, model="qwen2.5:7b")

    result = brain.chat("hola")

    assert route.called
    assert isinstance(result, ChatResult)
    assert result.text == "Hola, soy FRIDAY."
    assert result.model == "qwen2.5:7b"
    assert result.tokens_in == 12
    assert result.tokens_out == 8


@respx.mock
def test_chat_sends_system_prompt_and_no_streaming():
    route = respx.post(CHAT_URL).mock(return_value=_ok_response())
    brain = OllamaBrain(host=HOST, model="qwen2.5:7b")

    brain.chat("¿cuánta RAM tengo?")

    sent = json.loads(route.calls.last.request.content)
    assert sent["stream"] is False
    assert sent["model"] == "qwen2.5:7b"
    assert sent["messages"][0]["role"] == "system"
    assert "FRIDAY" in sent["messages"][0]["content"]
    assert sent["messages"][-1] == {"role": "user", "content": "¿cuánta RAM tengo?"}


# ── Error / offline ────────────────────────────────────────────────────────

@respx.mock
def test_chat_returns_friendly_message_when_ollama_offline():
    respx.post(CHAT_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    brain = OllamaBrain(host=HOST)

    result = brain.chat("hola")

    # No crashea y avisa que Ollama no responde.
    assert "Ollama" in result.text
    assert result.model == brain.model


@respx.mock
def test_chat_returns_friendly_message_on_http_500():
    respx.post(CHAT_URL).mock(return_value=httpx.Response(500))
    brain = OllamaBrain(host=HOST)

    result = brain.chat("hola")

    assert "Ollama" in result.text


# ── Reglas de negocio ──────────────────────────────────────────────────────

@respx.mock
def test_chat_persists_user_and_assistant_messages():
    respx.post(CHAT_URL).mock(return_value=_ok_response())
    repo = MagicMock()
    repo.load_session.return_value = []
    brain = OllamaBrain(host=HOST, chat_repo=repo, session_id="sess-1")

    brain.chat("hola")

    # Debe persistir el mensaje del usuario y la respuesta del asistente.
    assert repo.save_message.call_count == 2


@respx.mock
def test_history_accumulates_turns():
    respx.post(CHAT_URL).mock(return_value=_ok_response())
    brain = OllamaBrain(host=HOST)

    brain.chat("hola")
    assert len(brain.history) == 2  # user + assistant
    assert brain.history[0]["role"] == "user"
    assert brain.history[1]["role"] == "assistant"


def test_reset_clears_history():
    brain = OllamaBrain(host=HOST)
    brain._history.append({"role": "user", "content": "x"})

    brain.reset()

    assert brain.history == []


def test_trim_history_keeps_last_n_turns():
    from friday.config import settings

    brain = OllamaBrain(host=HOST)
    for i in range(20):
        brain._history.append({"role": "user", "content": f"q{i}"})
        brain._history.append({"role": "assistant", "content": f"a{i}"})

    brain._trim_history()

    starts = [m for m in brain._history if m["role"] == "user"]
    assert len(starts) == settings.chat_history_window
    assert starts[0]["content"] == f"q{20 - settings.chat_history_window}"


@respx.mock
def test_compose_returns_text_without_touching_history():
    """compose() one-shot: genera sin tocar el historial (rituales, Pilar 2)."""
    respx.post(CHAT_URL).mock(return_value=_ok_response("Morning, sir."))
    brain = OllamaBrain(host=HOST, model="qwen2.5:7b")

    out = brain.compose("brief me")

    assert out == "Morning, sir."
    assert brain._history == []  # stateless


@respx.mock
def test_reply_generates_without_adding_user_message():
    """reply() responde sobre el historial actual sin re-agregar un user.

    Es lo que usa el fallback de Gemini para continuar el hilo con contexto
    compartido sin duplicar el mensaje del usuario (ya guardado por Gemini)."""
    respx.post(CHAT_URL).mock(return_value=_ok_response("Respondo local, sir."))
    brain = OllamaBrain(host=HOST, model="qwen2.5:7b")
    # Historial pre-cargado (como si viniera de la DB): termina en el user.
    brain._history = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "buenas, sir"},
        {"role": "user", "content": "cómo viene la cpu"},
    ]

    result = brain.reply()

    assert result.text == "Respondo local, sir."
    # No duplicó el user: solo se agregó el assistant nuevo al final.
    users = [m for m in brain._history if m["role"] == "user"]
    assert len(users) == 2
    assert brain._history[-1] == {"role": "assistant", "content": "Respondo local, sir."}


def test_trim_history_cuts_on_user_boundary_not_mid_tool():
    brain = OllamaBrain(host=HOST)
    for i in range(20):
        brain._history.append({"role": "user", "content": f"q{i}"})
        brain._history.append({"role": "assistant", "content": "", "tool_calls": [{}]})
        brain._history.append({"role": "tool", "content": "resultado"})
        brain._history.append({"role": "assistant", "content": f"a{i}"})

    brain._trim_history()

    # Nunca arrancamos en un tool message huérfano: el primero es un user.
    assert brain._history[0]["role"] == "user"


# ── Tool calling ──────────────────────────────────────────────────────────

def _tool_call_response(tool_name: str, tool_args: dict, content: str = ""):
    """Respuesta HTTP de Ollama con un tool_call."""
    return httpx.Response(
        200,
        json={
            "message": {
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "function": {
                            "name": tool_name,
                            "arguments": tool_args,
                        }
                    }
                ],
            },
            "prompt_eval_count": 20,
            "eval_count": 15,
        },
    )


@respx.mock
def test_chat_with_tool_call_executes_and_gets_final_response():
    """El modelo pide una tool, se ejecuta, y en la segunda vuelta responde."""
    # Mock de la tool
    registry = MagicMock()
    registry.__len__ = lambda self: 1
    registry.as_callable_list.return_value = [lambda: "ok"]
    registry.execute.return_value = "resultado de la tool"

    # Primera llamada: tool_call, segunda: respuesta final
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            _tool_call_response("mi_tool", {"arg": "val"}),
            _ok_response("Respuesta final."),
        ]
    )

    brain = OllamaBrain(host=HOST, model="qwen2.5:7b", registry=registry)

    result = brain.chat("usá la tool")

    assert result.text == "Respuesta final."
    assert route.call_count == 2
    # La tool se ejecutó con los argumentos del modelo
    registry.execute.assert_called_once_with("mi_tool", {"arg": "val"})
    # El historial incluye user, assistant(tool_call), tool(result), assistant(final)
    assert len(brain.history) == 4
    assert brain.history[-1]["role"] == "assistant"
    assert brain.history[-1]["content"] == "Respuesta final."


@respx.mock
def test_chat_without_registry_sends_no_tools():
    """Sin registry, no se pasan tools al modelo. Comportamiento v1."""
    route = respx.post(CHAT_URL).mock(return_value=_ok_response())
    brain = OllamaBrain(host=HOST, model="qwen2.5:7b")  # sin registry

    brain.chat("hola")

    sent = json.loads(route.calls.last.request.content)
    assert "tools" not in sent


@respx.mock
def test_chat_max_tool_rounds_returns_fallback():
    """Si el modelo nunca deja de pedir tools, se corta en MAX_TOOL_ROUNDS."""
    registry = MagicMock()
    registry.__len__ = lambda self: 1
    registry.as_callable_list.return_value = [lambda: "ok"]
    registry.execute.return_value = "ok"

    # Siempre responde con tool_call → ciclo infinito simulado
    respx.post(CHAT_URL).mock(
        return_value=_tool_call_response("loop_tool", {})
    )

    brain = OllamaBrain(host=HOST, model="qwen2.5:7b", registry=registry)

    result = brain.chat("loopeá")

    assert "tool call limit" in result.text.lower()
    # Debe haber llamado MAX_TOOL_ROUNDS veces (10)
    assert respx.post(CHAT_URL).call_count == 10


@respx.mock
def test_chat_tool_execution_error_is_reported_to_model():
    """Si una tool falla, el error se pasa como resultado y el modelo sigue."""
    registry = MagicMock()
    registry.__len__ = lambda self: 1
    registry.as_callable_list.return_value = [lambda: "ok"]
    registry.execute.side_effect = RuntimeError("falló la tool")

    respx.post(CHAT_URL).mock(
        side_effect=[
            _tool_call_response("falla_tool", {}),
            _ok_response("La tool falló, pero sigo."),
        ]
    )

    brain = OllamaBrain(host=HOST, model="qwen2.5:7b", registry=registry)

    result = brain.chat("fallá")

    assert result.text == "La tool falló, pero sigo."
    # El resultado de la tool fue el mensaje de error
    tool_msg = brain.history[2]
    assert tool_msg["role"] == "tool"
    assert "falló la tool" in tool_msg["content"]
