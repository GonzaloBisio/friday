# FRIDAY — Modelos: qué usar en cada momento

> Verificado el **2026-09-26** contra [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models),
> [/pricing](https://ai.google.dev/gemini-api/docs/pricing), [/thinking](https://ai.google.dev/gemini-api/docs/thinking)
> y [ollama.com/library/gemma4](https://ollama.com/library/gemma4/tags). Hardware objetivo: **MacBook M4, 16 GB**.
> Gemini 3.x verificado en vivo el 2026-09-27 (§7).

## 1. Por qué hubo que migrar

| Modelo | Estado (2026-09) | Impacto en FRIDAY |
|---|---|---|
| `gemini-2.0-flash` | **Apagado** | Devolvía 404 (ya se había migrado). |
| `gemini-2.5-flash` / `-pro` / `-flash-lite` | **Access limited** ("usar 3.5 Flash-Lite o 3.8 Flash") | Eran los defaults → migrados. |
| Familia **3.x** | Thinking **siempre ON** (no hay `budget=0`); usa `thinking_level`; el thinking **cuenta dentro de `max_output_tokens`** | Con el techo viejo de 200 tokens la respuesta salía vacía → techo 1024 + `thinking_level` por modelo. |

## 2. Matriz de decisión (lo configurado)

| Rol (`config.py`) | Modelo | Thinking | USD / 1M (in · out · cached) | Cuándo se usa |
|---|---|---|---|---|
| `gemini_model_fast` | **`gemini-3.5-flash-lite`** | `low` | 0.30 · 2.50 · 0.03 | Turnos de voz con tools (~80% del tráfico). **Mismo precio que el viejo 2.5-flash** → respeta el tope mensual. |
| `gemini_model_balanced` | **`gemini-3.8-flash`** | `low` | 0.75 · 3.75 · 0.075 ⁽¹⁾ | AUTO con mensajes >200 chars (análisis, comparaciones). |
| `gemini_model_lite` | **`gemini-3.5-flash-lite`** | `low` | 0.30 · 2.50 · 0.03 | `compose()`: briefings y redacción one-shot sin tools. |
| `gemini_model_reasoning` | **`gemini-3.1-pro-preview`** | default | 2.00 · 12.00 · 0.20 | **Solo** `model="pro"` explícito. Preview y **sin free tier**. AUTO nunca escala acá. |
| `ollama_model` (local) | **`gemma4:e4b-it-qat`** (6.1 GB) | — | gratis | `LLM_PROVIDER=ollama`, sin internet, o fallback automático ante 429. |

⁽¹⁾ Precio promo de 3.6/3.7/3.8-flash hasta **2026-12-31**; desde 2027-01-01 se duplica (1.50 · 7.50).

**Alternativas evaluadas** (cambiar por `.env`):
- `GEMINI_MODEL_FAST=gemini-3.6-flash` → **modo calidad**. Único 3.x flash con thinking `minimal` (menor
  latencia al primer token) y probablemente mejores tool calls; cuesta 2.5× (5× desde 2027).
- `gemini-3.1-flash-lite` (0.25 · 1.50) → aún más barato, generación anterior; útil para briefings si
  querés exprimir costos.

## 3. Local (Ollama) en 16 GB

| Tag (verificado) | Disco | Contexto | Veredicto |
|---|---|---|---|
| **`gemma4:e4b-it-qat`** | 6.1 GB | 128K | **Default.** Tools nativas, entra con Whisper + TTS + navegador abiertos. |
| `gemma4:12b-it-qat` | 7.2 GB | 256K | Mejor razonamiento. Usalo si FRIDAY es lo principal abierto (`OLLAMA_MODEL=gemma4:12b-it-qat`). |
| `gemma4:e2b-it-qat` | 4.3 GB | 128K | Ultra liviano; tool calling más flojo. |
| `gemma4:26b-*` / `31b-*` | 16–20 GB | 256K | **No entran** en 16 GB. |

- Las variantes `e*` pesan más que su tamaño sugiere (encoders de audio/visión + embeddings por capa);
  por eso `12b-it-qat` casi iguala a `e4b-it-qat` en disco.
- **`ollama_think=false`** (crítico): Gemma 4 piensa por defecto y el razonamiento se come
  `num_predict` → respuesta vacía. Medido: con thinking 12.8 s y vacío; sin thinking **0.4 s** y correcto.
- **Medido en el M4** (tools reales vía `FridaySystem`): "how much RAM" → `info_sistema` ✔ (13.7 s en frío,
  incluye cargar el modelo) · "remember…" → `recordar` ✔ (11.3 s: la memoria nueva cambia el system
  prompt e invalida el KV-cache) · "what time is it" → `obtener_fecha_hora` ✔ (**1.9 s** con cache).
  Calidad: guardó la memoria como "no sugar" (perdió "café") → para memorias, mejor Gemini.
- `ollama_num_ctx=8192`: explícito a propósito. Con ~2.9K tokens fijos por llamada (system + tools), el
  default de Ollama recortaba el system prompt.
- Tuning opcional del servicio (lo sugiere el propio `brew`): `OLLAMA_FLASH_ATTENTION=1` y
  `OLLAMA_KV_CACHE_TYPE=q8_0` (≈ mitad de RAM de KV-cache).
- Qwen/Ministral/Phi para tool calling local: **no verificados** en esta revisión; Gemma 4 alcanza.

## 4. Voz

| Etapa | Qué usa | Medido en el M4 |
|---|---|---|
| Wake word | Vosk `small-en-us-0.15` con grammar restringida | detecta "friday" ✔ |
| STT | **Parakeet `parakeet-tdt-0.6b-v3`** (MLX/GPU) → fallback whisper-large-v3-turbo (MLX) → faster-whisper `small.en` (CPU) → Vosk | ver tabla abajo |
| TTS | Pocket TTS **en streaming**: voz clonada de `voices/jarvis.wav` si existe (pesos gated, login HF) → si no, voz de **catálogo** `TTS_VOICE` (default **`michael`**, sin login) → fallback Piper `en_US-ryan-high` | 1er audio **0.04–0.09 s**; RTF 0.14 (6.4 s de audio en 0.88 s) |

Benchmark STT (4 frases de ~3 s, voz sintética; el único error de todos fue "reservation**s**"):

| Modelo | Media | Exactas |
|---|---|---|
| **parakeet-tdt-0.6b-v3** (default) | **0.14 s** | 3/4 |
| whisper-small.en | 0.26 s | 3/4 |
| whisper-large-v3-turbo | 1.05 s | 3/4 |
| distil-whisper-large-v3 | 2.06 s | 2/4 |

Whisper siempre procesa 30 s de audio (padding) aunque hables 3: por eso Parakeet gana 7×. ⚠️ Medido
con voz sintética, no con acento real: si entiende peor, `FRIDAY_STT=mlx` vuelve a whisper-turbo.

Knobs (env del listener salvo `TTS_VOICE`): `TTS_VOICE` (`.env`), `FRIDAY_STT=parakeet|mlx|faster-whisper`,
`FRIDAY_END_SILENCE` (default 0.8 s), `FRIDAY_PARAKEET_MODEL`, `FRIDAY_MLX_WHISPER_MODEL`.

## 5. Latencia de un turno (de que dejás de hablar a que FRIDAY suena)

| Etapa | Antes | Ahora | Qué se hizo |
|---|---|---|---|
| Cierre de turno (silencio) | 1.3 s + hasta 0.25 s | **0.8 s** (+≤0.1 s) | `END_SILENCE_S` 0.8, lectura del mic cada 100 ms |
| STT | 1.05–1.4 s | **~0 s** | Parakeet (0.14 s) + **STT especulativo**: arranca a los 0.3 s de silencio, dentro de la espera del cierre |
| LLM sin tool | ~0.8–1 s | ~0.8–1 s | "qué hora es" ya no llama tool (usa `[local time]`) |
| LLM con tool | ~2–2.6 s | ~2–2.6 s | 2 llamadas en serie (inevitable) |
| TTS al 1er audio | ~0.9 s + arranque afplay | **~0.09 s** | streaming Pocket TTS → PyAudio |
| **Total sin tool** | **~4.6 s** | **~1.8 s** | |
| **Total con tool** | **~6.2 s** | **~3.5 s** | |

Cada turno loguea el desglose en `voices/friday-wake.log` (`[tiempos] respuesta ~X s = endpoint + STT +
LLM + TTS 1er audio`). Charla continua: tras la wake word no hace falta repetirla (60 s de silencio
para salir); barge-in con filtro de **eco por contenido** (`_is_echo`: si lo "oído" coincide ≥50% con lo
que FRIDAY está diciendo, se ignora — antes se interrumpía sola con los parlantes de la MacBook).

Probado y descartado: keep-alive largo del cliente HTTP de Gemini (sin diferencia medible frente al
ruido de red, 0.7–1.6 s).

**Siguiente salto — `gemini-3.8-live`** (GA 2026-09): audio nativo de punta a punta, full-duplex con
barge-in; reemplazaría STT → LLM → TTS (latencia típica sub-segundo). Contras: audio a $3/1M in ·
$12/1M out (≈ $0.10–0.15 por 10 min de charla → puede superar el tope de USD 4/mes), depende de
internet y usa las voces de Gemini (se pierde `michael`/Pocket).

## 6. Costo por turno (medido)

Cada llamada manda **~3.6–4.0K tokens** (system ~0.6K + tools ~2.4K + memorias + historial). Un turno
sin tool = 1 llamada; con tool = 2 (~7.6K). **El cache implícito NO aplica**: los 3.x Flash exigen
**≥4.096 tokens** de input y `flash-lite` ni figura entre los soportados
([docs de caching](https://ai.google.dev/gemini-api/docs/caching), verificado 2026-09-27; `cached=None`
en todas las llamadas medidas). Precio lleno:

| Modelo | Turno sin tool | Turno con tool | 1.500 turnos/mes (70/30) |
|---|---|---|---|
| **3.5-flash-lite** | ~$0.0012 | ~$0.0024 | **~$2.3** |
| 3.6/3.8-flash | ~$0.0029 | ~$0.0058 | ~$5.5 (x2 desde 2027) |
| 3.1-pro-preview | ~$0.008+ | — | solo a pedido |

Qué reduce tokens de verdad (`friday/core/context_window.py`): resultados de tools de turnos previos
recortados a 600 chars (`tool_result_history_chars`) y el prefijo estable (sigue sirviendo para el
KV-cache de Ollama). Palanca pendiente: **achicar los schemas de tools** (~2.4K por llamada, ver
[TOOLS.md](TOOLS.md)) — cada 1K menos ≈ −25% de costo.

## 7. Verificación en vivo (2026-09-27)

Gemini con key real: 3/3 pedidos con tool correcta (`info_sistema`, `obtener_fecha_hora`,
`listar_procesos`), ~2 s por turno con tool, ~0.9 s sin tool. Para repetirla:

```bash
bash stop.sh; bash start.sh
curl -s -X POST http://127.0.0.1:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"message":"how much RAM am I using?","model":"auto"}'   # debe llamar info_sistema
grep -iE "gemini|error|429" friday.log | tail
```
Si responde vacío o `(sin respuesta)`: subir `GEMINI_MAX_OUTPUT_TOKENS` o bajar el `thinking_level`.
Si un ID devuelve 404: revisar la página de modelos y actualizar `config.py` + `gemini_pricing`.
