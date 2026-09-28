# FRIDAY — Modelos: qué usar en cada momento

> Verificado el **2026-09-26** contra [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models),
> [/pricing](https://ai.google.dev/gemini-api/docs/pricing), [/thinking](https://ai.google.dev/gemini-api/docs/thinking)
> y [ollama.com/library/gemma4](https://ollama.com/library/gemma4/tags). Hardware objetivo: **MacBook M4, 16 GB**.
> ⚠️ Los modelos 3.x **no se probaron todavía contra la API real** (falta la key en esta Mac):
> la integración está cubierta por tests con mocks. Primera prueba en vivo: ver §6.

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
| STT | **mlx-whisper `whisper-large-v3-turbo`** (GPU/Metal) → fallback faster-whisper `small.en` (CPU) → Vosk | frase de 9 palabras exacta en **1.06 s** |
| TTS | Pocket TTS con voz **Jarvis clonada** (`voices/jarvis.wav`) → fallback Piper `en_US-ryan-high` | Piper ✔ · Jarvis pendiente de `jarvis.wav` + login HF |

Knobs: `FRIDAY_STT=mlx|faster-whisper`, `FRIDAY_MLX_WHISPER_MODEL=<repo HF>` (env del listener).

**Futuro — `gemini-3.8-live`** (GA 2026-09): audio nativo de punta a punta con barge-in; reemplazaría
STT → LLM → TTS en un solo stream (latencia mucho menor). Contras: audio a $3/1M in · $12/1M out,
depende de internet y **pierde la voz clonada de Jarvis**. Vale un experimento como modo opcional.

## 5. Costo por turno

Cada llamada al LLM manda **~2.9K tokens fijos**: system prompt (~510) + schema de tools (~2.4K,
ver [TOOLS.md](TOOLS.md)) + memorias (hasta 30) + historial (12 turnos). Un turno de voz con una
tool son **2 llamadas**. Estimación (8K tokens in, ~150 out por turno):

| Modelo | Sin cache | Con cache implícito (~75% del input) | 1.500 turnos/mes |
|---|---|---|---|
| 3.5-flash-lite | ~$0.0028 | **~$0.0012** | ~$1.8 (sin cache ~$4.2) |
| 3.6/3.8-flash | ~$0.0066 | ~$0.0025 | ~$3.8 (x2 desde 2027) |
| 3.1-pro-preview | ~$0.03 | — | solo a pedido |

**Por qué importa el cache y qué se hizo** (`friday/core/context_window.py`):
1. **Prefijo estable**: el system prompt lleva solo la **fecha**; la hora viaja en cada mensaje
   (`[local time HH:MM]`). Antes la hora-minuto al inicio invalidaba el cache en cada llamada. Aplica
   también a Ollama (reusa el KV-cache → menos prefill en el M4).
2. **Resultados viejos recortados** a 600 chars (`tool_result_history_chars`): un `leer_pagina` de 6K
   chars ya no se reenvía 12 turnos.
3. **No** se hizo ruteo dinámico de tools (mandar solo las relevantes): cambiaría el prefijo en cada
   turno (rompe el cache) y arriesga que el modelo no encuentre la tool.

> Pendiente: el tracker de costos (`collectors/gemini_usage.py`) cobra todo el input a precio lleno;
> registrar `usage_metadata.cached_content_token_count` daría el costo real y confirmaría que el
> cache pega.

## 6. Primera prueba en vivo (cuando esté la key)

```bash
# .env: LLM_PROVIDER=gemini + GEMINI_API_KEY=...
bash stop.sh; bash start.sh
curl -s -X POST http://127.0.0.1:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"message":"how much RAM am I using?","model":"auto"}'   # debe llamar info_sistema
grep -iE "gemini|error|429" friday.log | tail
```
Si responde vacío o `(sin respuesta)`: subir `GEMINI_MAX_OUTPUT_TOKENS` o bajar el `thinking_level`.
Si un ID devuelve 404: revisar la página de modelos y actualizar `config.py` + `gemini_pricing`.
