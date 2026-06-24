"""Configuración del agente de PC — registra acciones y conecta con tools_registry."""

from __future__ import annotations

import functools
import json
from typing import Callable

from friday.agent.actions.pc_actions import (
    abrir_app,
    abrir_url,
    buscar_en_google,
    cerrar_app,
    info_sistema,
    leer_archivo,
    listar_directorio,
    listar_procesos,
)
from friday.agent.permissions import PermissionGate
from friday.agent.registry import ActionRegistry, RiskLevel
from friday.core.tools_registry import ToolsRegistry
from friday.integrations.spotify import (
    ajustar_volumen,
    pausar_spotify,
    reproducir_spotify,
    siguiente_cancion,
)
from friday.integrations.gastos import registrar_gasto, ver_gastos
from friday.integrations.web_research import buscar_web, leer_pagina


def build_action_registry() -> ActionRegistry:
    """Registra todas las acciones de PC en la allowlist."""
    reg = ActionRegistry()

    # LOW: abrir/cerrar una app es reversible y de bajo riesgo. Se ejecuta
    # solo (sin confirmación), necesario para el control por voz tipo Alexa.
    # Para volver a exigir confirmación, cambiar a RiskLevel.MEDIUM.
    reg.register("abrir_app", "Abre una aplicación por nombre", RiskLevel.LOW, abrir_app, tags=("pc",))
    reg.register("cerrar_app", "Cierra una aplicación por nombre", RiskLevel.LOW, cerrar_app, tags=("pc",))
    # WEB: abrir URLs y buscar en Google. Reversible, bajo riesgo → ejecuta solo.
    reg.register("abrir_url", "Abre una URL (web o spotify:) en el navegador/app por defecto", RiskLevel.LOW, abrir_url, tags=("web",))
    reg.register("buscar_en_google", "Abre en el navegador una búsqueda de Google (para que la vea Gonzalo)", RiskLevel.LOW, buscar_en_google, tags=("web",))
    # RESEARCH: traen el TEXTO al modelo (vs. abrir el navegador) → discutir/comparar/recomendar.
    reg.register("buscar_web", "Busca en la web y DEVUELVE los resultados (título, resumen, URL) para razonar sobre ellos", RiskLevel.LOW, buscar_web, tags=("web", "research"))
    reg.register("leer_pagina", "Baja una URL y devuelve su contenido principal en texto, para leerlo/resumirlo/discutirlo", RiskLevel.LOW, leer_pagina, tags=("web", "research"))
    reg.register("listar_procesos", "Lista procesos top por memoria/CPU", RiskLevel.LOW, listar_procesos, tags=("pc",))
    reg.register("leer_archivo", "Lee un archivo de texto", RiskLevel.LOW, leer_archivo, tags=("pc",))
    reg.register("info_sistema", "Info detallada del sistema", RiskLevel.LOW, info_sistema, tags=("pc",))
    reg.register("listar_directorio", "Lista contenido de un directorio", RiskLevel.LOW, listar_directorio, tags=("pc",))

    # SPOTIFY: reproducir/pausar/saltar. Reproducir música es inocuo y reversible
    # → LOW (control por voz fluido, sin confirmaciones).
    reg.register("reproducir_spotify", "Reproduce música en Spotify. tipo: 'track' para una canción puntual, 'playlist' para una lista o género (ej. Tech House), 'artist' para un artista, 'album' para un disco", RiskLevel.LOW, reproducir_spotify, tags=("spotify", "web"))
    reg.register("pausar_spotify", "Pausa la reproducción de Spotify", RiskLevel.LOW, pausar_spotify, tags=("spotify",))
    reg.register("siguiente_cancion", "Pasa a la siguiente canción en Spotify", RiskLevel.LOW, siguiente_cancion, tags=("spotify",))
    reg.register("ajustar_volumen", "Ajusta el volumen de Spotify (0-100) en el dispositivo activo", RiskLevel.LOW, ajustar_volumen, tags=("spotify",))

    # GASTOS: ver el resumen y cargar gastos en la planilla. cargar_gasto ESCRIBE
    # → hoy LOW (frictionless por voz); subir a MEDIUM cuando exista confirmación
    # por voz (Fase G). Es reversible borrando la fila.
    reg.register("ver_gastos", "Muestra el resumen del mes de la planilla de gastos (ingresos, gastos, balance)", RiskLevel.LOW, ver_gastos, tags=("gastos",))
    # registrar_gasto toma UNA frase ("10 mil en súper con débito") y FRIDAY parsea
    # monto/categoría/medio en Python — mucho más confiable para el LLM de 7B que
    # pedirle 5 args estructurados (que terminaba alucinando).
    reg.register("registrar_gasto", "Registra un gasto o ingreso dictado en una sola frase (ej. '10 mil en super con débito')", RiskLevel.LOW, registrar_gasto, tags=("gastos",))

    return reg


def register_agent_tools(tools_reg: ToolsRegistry, gate: PermissionGate) -> None:
    """Expone cada acción del gate como una tool de PRIMERA CLASE (no anidada).

    Antes TODO iba detrás de una sola tool `ejecutar_accion_pc(accion, argumentos)`,
    donde `argumentos` era un JSON STRINGIFICADO. Un modelo de 7B no podía construir
    ese JSON anidado y terminaba NARRANDO el éxito sin llamar la tool (alucinación
    confirmada en friday.log: cargar_gasto se "ejecutaba" pero nunca corría).

    Al registrar cada acción con su firma REAL (`abrir_app(nombre)`,
    `cargar_gasto(monto, categoria, …)`), el schema que ve el modelo es claro y la
    llama bien. Cada tool sigue pasando por el PermissionGate (el riesgo queda intacto):
    LOW ejecuta, MEDIUM/HIGH devuelve pending_confirmation.
    """
    for spec in gate._registry.catalog:
        tools_reg.register(_make_gated_tool(gate, spec))


def _make_gated_tool(gate: PermissionGate, spec) -> Callable:
    """Crea una tool que conserva la firma/docstring de la acción y pasa por el gate.

    functools.wraps copia __name__/__doc__/__annotations__/__wrapped__, así
    inspect.signature (que usa tool_schema) ve la firma REAL de la acción y genera
    el schema correcto. En éxito devuelve el resultado pelado (texto que el modelo
    puede leer directo); si queda pendiente o falla, devuelve el estado en JSON.
    """
    fn = spec.fn

    @functools.wraps(fn)
    def tool(**kwargs) -> str:
        result = gate.request(spec.name, kwargs)
        if isinstance(result, dict) and result.get("status") == "ok":
            return str(result.get("result", ""))
        return json.dumps(result, ensure_ascii=False, default=str)

    # El nombre de la tool (clave en el registry y en el schema) es el de la ACCIÓN
    # —como la llama el LLM y la indexa el gate—, no el de la función subyacente
    # (que podría diferir, ej. un lambda registrado con otro nombre).
    tool.__name__ = spec.name
    tool.__qualname__ = spec.name
    return tool
