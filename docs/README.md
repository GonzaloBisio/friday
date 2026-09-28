# FRIDAY — Documentación

> Asistente personal de Gonzalo Bisio. Por voz, estilo Jarvis, **local-first**, nativo en Mac.
> Wake word → escucha → cerebro (Gemini 3.x / Gemma 4 local) → responde con voz clonada. Y, con
> autorización humana, ejecuta acciones reales sobre sus sistemas y herramientas.

Punto de entrada para **cualquier IA o persona**. Orden de lectura sugerido para no gastar de más:
`CLAUDE.md` (raíz, 1 pantalla) → el doc puntual que necesites de esta tabla.

| Documento | Para qué | Mantenimiento |
|-----------|----------|---------------|
| [../CLAUDE.md](../CLAUDE.md) | Índice compacto para agentes: comandos, invariantes, dónde está cada cosa. | a mano |
| [CODEMAP.md](CODEMAP.md) | **DÓNDE**: grafo de ejecución, qué hace cada archivo, recetas "quiero agregar X". | a mano (test valida las líneas) |
| [TOOLS.md](TOOLS.md) | **QUÉ PUEDE HACER**: cada tool que ve el LLM, riesgo, fuente, tamaño. | **generado** (`scripts/gen_tool_index.py`) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | **CÓMO y POR QUÉ**: procesos, pipeline de voz, cerebro, gotchas. | a mano |
| [MODELS.md](MODELS.md) | **CON QUÉ MODELO**: matriz Gemini/Gemma/voz, precios, costo por turno. | a mano (revisar cada ~3 meses) |
| [ROADMAP.md](ROADMAP.md) | **A DÓNDE VAMOS**: integraciones, modelo de autorización, fases. | a mano |
| [MIGRATION.md](MIGRATION.md) | Traer voz, secretos y datos desde la PC Windows vieja. | one-shot |

`../FRIDAY_IMPLEMENTATION_PLAN.md` es el plan original (2026-06, Windows): **histórico**, no describe
el estado actual.

## North Star

FRIDAY debe convertirse en un **asistente personal completamente operativo** que:

1. **Conversa** de forma natural por voz, con personalidad (estilo Jarvis).
2. **Observa** los sistemas de Gonzalo (AXIS y NEXCOURT en AWS) y reporta su estado.
3. **Controla** sus herramientas (posts de LinkedIn, tickets SIRADIG, gastos personales)
   **siempre con autorización humana** para acciones sensibles.
4. Sigue siendo **barato y local** salvo decisión explícita en contrario.

## Principios de diseño (no negociables)

- **Local-first / barato**: nada de costos por uso salvo aprobación; tope mensual en la API key.
- **Humano al mando**: las acciones con riesgo pasan por el *gate* de permisos y requieren
  confirmación. Ver [ROADMAP.md](ROADMAP.md#modelo-de-autorización).
- **Conceptos antes que código**: entender el porqué antes de tocar una línea.
- **Mejora continua**: cada integración es incremental y usable por sí sola.
