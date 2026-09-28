# FRIDAY — Índice de tools (generado)

> **No editar a mano.** Generado por `scripts/gen_tool_index.py` desde el registry real.
> Regenerar: `./venv/bin/python scripts/gen_tool_index.py` (un test falla si queda viejo).

- **30 tools** con todos los flags activos. Schema total ≈ **9,491 chars
  (~2,372 tokens)** que viajan en CADA llamada al LLM, a precio lleno (no hay
  cache implícito por debajo de 4.096 tokens) → ver [MODELS.md](MODELS.md#6-costo-por-turno-medido).
- **Riesgo**: LOW ejecuta solo · MEDIUM/HIGH queda pendiente de confirmación
  (`friday/agent/permissions.py`). `—` = tool de lectura directa (no pasa por el gate).
- `param?` = opcional. La descripción es la 1ra línea del docstring (lo único que ve el
  modelo además de los `Args:`) → mantenerla corta y precisa.

| Tool | Descripción (lo que ve el LLM) | Riesgo | Tags | Disponible | Fuente | Chars |
|---|---|---|---|---|---|---|
| `consultar_metricas(source, name?, horas?, limit?)` | Consulta métricas almacenadas en FRIDAY. | — |  | siempre | [friday/core/tools_registry.py:53](../friday/core/tools_registry.py#L53) | 676 |
| `resumen_costos(horas?)` | Resume el costo acumulado de uso de Gemini en un período. | — |  | siempre | [friday/core/tools_registry.py:75](../friday/core/tools_registry.py#L75) | 301 |
| `obtener_fecha_hora()` | Devuelve la fecha y hora actual del sistema. | — |  | siempre | [friday/core/tools_registry.py:107](../friday/core/tools_registry.py#L107) | 195 |
| `estado_sistemas(sistema?)` | Resumen del estado actual de los servicios monitoreados. | — |  | siempre | [friday/core/tools_registry.py:124](../friday/core/tools_registry.py#L124) | 297 |
| `metricas_servicio(servicio, horas?, limit?)` | Serie temporal de métricas de un servicio específico (NEXCOURT o AXIS). | — |  | siempre | [friday/core/tools_registry.py:168](../friday/core/tools_registry.py#L168) | 520 |
| `alarmas_activas()` | Alarmas de CloudWatch que están en estado ALARM ahora mismo. | — |  | `NEXCOURT_MODE=cloudwatch` | [friday/core/tools_registry.py:191](../friday/core/tools_registry.py#L191) | 208 |
| `errores_recientes(servicio, minutos?)` | Mensajes de log con nivel ERROR de un servicio en los últimos minutos. | — |  | `NEXCOURT_MODE=cloudwatch` | [friday/core/tools_registry.py:201](../friday/core/tools_registry.py#L201) | 426 |
| `errores_axis(container, minutos?)` | Líneas de log con ERROR/EXCEPTION de un container AXIS. | — |  | `AXIS_ENABLED=true` | [friday/core/tools_registry.py:225](../friday/core/tools_registry.py#L225) | 417 |
| `abrir_app(nombre)` | Abre una aplicación en la Mac de Gonzalo. | LOW | pc | siempre | [friday/agent/actions/pc_actions.py:63](../friday/agent/actions/pc_actions.py#L63) | 306 |
| `cerrar_app(nombre)` | Cierra una aplicación abierta en la Mac de Gonzalo. | LOW | pc | siempre | [friday/agent/actions/pc_actions.py:86](../friday/agent/actions/pc_actions.py#L86) | 317 |
| `abrir_url(url)` | Abre una URL en el navegador (o app) por defecto. | LOW | web | siempre | [friday/agent/actions/pc_actions.py:115](../friday/agent/actions/pc_actions.py#L115) | 299 |
| `buscar_en_google(consulta)` | Abre una búsqueda de Google en el navegador por defecto. | LOW | web | siempre | [friday/agent/actions/pc_actions.py:169](../friday/agent/actions/pc_actions.py#L169) | 330 |
| `buscar_web(consulta, cantidad?)` | Busca en la web y devuelve los primeros resultados (título, resumen y URL). | LOW | web, research | siempre | [friday/integrations/web_research.py:90](../friday/integrations/web_research.py#L90) | 382 |
| `leer_pagina(url)` | Baja una página web y devuelve su contenido principal en texto limpio. | LOW | web, research | siempre | [friday/integrations/web_research.py:120](../friday/integrations/web_research.py#L120) | 285 |
| `listar_procesos(top?)` | Lista los procesos que más CPU o memoria consumen. | LOW | pc | siempre | [friday/agent/actions/pc_actions.py:190](../friday/agent/actions/pc_actions.py#L190) | 285 |
| `leer_archivo(ruta, max_lineas?)` | Lee el contenido de un archivo de texto. | LOW | pc | siempre | [friday/agent/actions/pc_actions.py:219](../friday/agent/actions/pc_actions.py#L219) | 351 |
| `info_sistema()` | Retorna información detallada del sistema operativo y hardware. | LOW | pc | siempre | [friday/agent/actions/pc_actions.py:245](../friday/agent/actions/pc_actions.py#L245) | 208 |
| `listar_directorio(ruta?)` | Lista el contenido de un directorio. | LOW | pc | siempre | [friday/agent/actions/pc_actions.py:272](../friday/agent/actions/pc_actions.py#L272) | 284 |
| `reproducir_spotify(consulta, tipo?)` | Busca en Spotify y reproduce el primer resultado en el dispositivo activo. | LOW | spotify, web | siempre | [friday/integrations/spotify.py:165](../friday/integrations/spotify.py#L165) | 444 |
| `pausar_spotify()` | Pausa la reproducción actual de Spotify. | LOW | spotify | siempre | [friday/integrations/spotify.py:198](../friday/integrations/spotify.py#L198) | 187 |
| `siguiente_cancion()` | Pasa a la siguiente canción en Spotify. | LOW | spotify | siempre | [friday/integrations/spotify.py:217](../friday/integrations/spotify.py#L217) | 189 |
| `ajustar_volumen(porcentaje)` | Ajusta el volumen de Spotify (0-100) en el dispositivo activo. | LOW | spotify | siempre | [friday/integrations/spotify.py:236](../friday/integrations/spotify.py#L236) | 323 |
| `ver_gastos()` | Devuelve el resumen del mes de la planilla (ingresos, gastos, balance). | LOW | gastos | siempre | [friday/integrations/gastos.py:244](../friday/integrations/gastos.py#L244) | 214 |
| `registrar_gasto(texto)` | Registra un gasto (o ingreso) a partir de UNA frase de lo que dijo Gonzalo. | LOW | gastos | siempre | [friday/integrations/gastos.py:211](../friday/integrations/gastos.py#L211) | 342 |
| `recordar(contenido, clave?)` | Guarda algo para recordarlo en futuras conversaciones. | — |  | siempre | [friday/core/memory_tools.py:16](../friday/core/memory_tools.py#L16) | 415 |
| `olvidar(descripcion)` | Borra de la memoria lo que matchee la descripción. | — |  | siempre | [friday/core/memory_tools.py:36](../friday/core/memory_tools.py#L36) | 312 |
| `ejecutar_rutina(nombre)` | Ejecuta una rutina compuesta por su nombre (ej. 'focus', 'winddown', 'pausa'). | — |  | siempre | [friday/core/routines.py:112](../friday/core/routines.py#L112) | 315 |
| `listar_rutinas()` | Lista las rutinas disponibles que FRIDAY puede ejecutar. | — |  | siempre | [friday/core/routines.py:130](../friday/core/routines.py#L130) | 203 |
| `estado_de_friday()` | Reporta la salud actual de FRIDAY: éxito de tools, fallbacks y latencia. | — |  | siempre | [friday/core/health.py:82](../friday/core/health.py#L82) | 221 |
| `consultar_research()` | Devuelve el último digest de research que FRIDAY juntó (novedades de IA/tech y backend). | — |  | siempre | [friday/core/research.py:117](../friday/core/research.py#L117) | 239 |
