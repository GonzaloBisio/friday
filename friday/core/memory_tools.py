"""Tools de memoria para FRIDAY — recordar y olvidar (capa de aprendizaje, Fase A).

Se registran directo en el ToolsRegistry (como las tools de lectura): escribir en la
memoria local es de bajo riesgo y tiene que ser frictionless para el uso por voz.
"""

from __future__ import annotations

from friday.core.tools_registry import ToolsRegistry
from friday.storage.memory_repo import MemoryRepository


def register_memory_tools(tools_reg: ToolsRegistry, memory_repo: MemoryRepository) -> None:
    """Registra `recordar` y `olvidar`, cerrando sobre el MemoryRepository."""

    def recordar(contenido: str, clave: str = "") -> str:
        """Guarda algo para recordarlo en futuras conversaciones.

        Usá esto cuando Gonzalo te pida recordar algo, o mencione una preferencia o
        dato suyo que convenga retener (ej. "recordá que tomo el café sin azúcar").

        Args:
            contenido: Lo que hay que recordar, en una frase corta.
            clave: Opcional. Una etiqueta corta y estable (ej. "cafe") para algo que
                puede cambiar — volver a usar la misma clave ACTUALIZA el valor.

        Returns:
            Confirmación.
        """
        contenido = (contenido or "").strip()
        if not contenido:
            return "No me dijiste qué recordar."
        memory_repo.remember(contenido, key=clave or None)
        return f"Anotado: {contenido}"

    def olvidar(descripcion: str) -> str:
        """Borra de la memoria lo que matchee la descripción.

        Args:
            descripcion: Texto para identificar qué olvidar (ej. "lo del café").

        Returns:
            Cuántas memorias se borraron.
        """
        descripcion = (descripcion or "").strip()
        if not descripcion:
            return "No me dijiste qué olvidar."
        n = memory_repo.forget(descripcion)
        return "No tenía nada así guardado." if n == 0 else f"Listo, olvidé {n} cosa(s)."

    tools_reg.register(recordar)
    tools_reg.register(olvidar)
