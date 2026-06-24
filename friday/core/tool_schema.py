"""Genera schemas JSON para tools de Ollama a partir de funciones Python.

Ollama /api/chat espera tools en formato OpenAI function calling:
    {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}

Este módulo extrae el schema de type hints + docstrings vía inspect.signature.
"""

from __future__ import annotations

import inspect
import types as _types
import typing
from typing import Any, Callable


def _python_type_to_json_type(py_type: Any) -> str:
    """Convierte un tipo Python a su equivalente JSON Schema."""
    origin = typing.get_origin(py_type)
    if origin is not None:
        # Union | Optional → tomar el primer tipo no-None
        if origin is typing.Union or origin is _types.UnionType:
            args = typing.get_args(py_type)
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                return _python_type_to_json_type(non_none[0])
        return "string"

    if py_type is str:
        return "string"
    if py_type is int:
        return "integer"
    if py_type is float:
        return "number"
    if py_type is bool:
        return "boolean"
    return "string"


def _parse_docstring(fn: Callable) -> dict[str, Any]:
    """Extrae la descripción general y las descripciones de parámetros del docstring.

    Parsea formato Google-style:
        Args:
            nombre: descripción.
        Returns:
            ...
    """
    doc = inspect.getdoc(fn) or ""
    lines = doc.split("\n")

    description = ""
    param_descriptions: dict[str, str] = {}
    current_section: str | None = None

    for line in lines:
        stripped = line.strip()

        if stripped in ("Args:", "Arguments:"):
            current_section = "args"
            continue
        if stripped.startswith("Returns:") or stripped.startswith("Return:"):
            current_section = None
            continue

        if current_section == "args" and ":" in stripped:
            name, _, desc = stripped.partition(":")
            param_descriptions[name.strip()] = desc.strip()
        elif not description and stripped and not current_section:
            description = stripped

    return {"description": description, "params": param_descriptions}


def function_to_tool_schema(fn: Callable) -> dict[str, Any]:
    """Convierte una función Python al schema JSON de Ollama/OpenAI function calling.

    Returns:
        {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
    """
    sig = inspect.signature(fn)
    doc_info = _parse_docstring(fn)

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        param_type = (
            param.annotation
            if param.annotation is not inspect.Parameter.empty
            else str
        )
        json_type = _python_type_to_json_type(param_type)

        prop: dict[str, Any] = {"type": json_type}
        if param_name in doc_info["params"]:
            prop["description"] = doc_info["params"][param_name]

        properties[param_name] = prop

        # Sin default → requerido
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": doc_info["description"],
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def build_tools_schema(registry: Any) -> list[dict[str, Any]]:
    """Genera la lista completa de tool schemas a partir de un ToolsRegistry."""
    return [function_to_tool_schema(fn) for fn in registry.as_callable_list()]
