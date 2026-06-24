# FRIDAY — Documentación

> Asistente personal de Gonzalo Bisio. Por voz, estilo Jarvis. **100% local y gratis.**
> Wake word → escucha → cerebro local → responde con voz clonada. Y, con autorización
> humana, ejecuta acciones reales sobre sus sistemas y herramientas.

Esta carpeta es el punto de entrada para **cualquier IA o persona** que necesite entender
el proyecto: qué hace, cómo está construido y hacia dónde va.

## Mapa de la documentación

| Documento | Para qué |
|-----------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | **QUÉ y CÓMO**: el sistema actual, pieza por pieza, con rutas de archivos y el porqué de cada decisión técnica. |
| [ROADMAP.md](ROADMAP.md) | **A DÓNDE VAMOS**: el plan de integraciones (observabilidad AWS, LinkedIn, SIRADIG, gastos), el modelo de autorización y las fases de mejora continua. |

## North Star (la visión)

FRIDAY debe convertirse en un **asistente personal completamente operativo** que:

1. **Conversa** de forma natural por voz, con personalidad (estilo Jarvis).
2. **Observa** los sistemas de Gonzalo (AXIS y NEXCOURT en AWS) y reporta su estado.
3. **Controla** sus herramientas (posts de LinkedIn, tickets SIRADIG, gastos personales)
   **siempre con autorización humana** para acciones sensibles.
4. Sigue siendo **gratis y local** salvo decisión explícita en contrario.

## Principios de diseño (no negociables)

- **Local-first / gratis**: nada de costos por uso salvo que el usuario lo apruebe.
- **Humano al mando**: las acciones con riesgo (escritura, acciones externas) pasan por
  un *gate* de permisos y requieren confirmación. Ver [ROADMAP.md](ROADMAP.md#modelo-de-autorización).
- **Conceptos antes que código**: entender el porqué antes de tocar una línea.
- **Mejora continua**: cada integración es incremental y usable por sí sola.

## Cómo levantar todo (resumen)

- **Listener de voz (Windows)**: `friday-wake.vbs` (autostart oculto al login) o
  `friday-wake.bat` (visible, para debug). Al decir "FRIDAY" se autolanza el backend y abre el HUD.
- **Backend (WSL)**: lo levanta el listener al decir "FRIDAY" (Ollama + API + dashboard), o
  manualmente con `start.sh`.
- **Command Center (HUD)**: http://localhost:8000/ · **API/Docs**: http://localhost:8000/docs

> Detalle completo del runtime en [ARCHITECTURE.md](ARCHITECTURE.md#cómo-corre-todo).
