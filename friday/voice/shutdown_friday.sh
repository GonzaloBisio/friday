#!/bin/bash
# ===================================================================
# shutdown_friday.sh — Mata TODOS los procesos de FRIDAY + Ollama.
#
# Diseñado para NO matchearse a sí mismo: los patrones de pkill no
# aparecen en la línea de comando con la que se invoca este script
# (`bash .../shutdown_friday.sh`), así que pkill -f no mata al
# shell que lo ejecuta.
#
# Cubre TODAS las formas de arrancar FRIDAY:
#   - `python -m friday.app`        (start.sh)
#   - `./venv/bin/friday`            (launch_friday desde windows_wake.py)
#   - `python -m streamlit run`      (dashboard, subprocess hijo)
#
# Además mata por puerto (fallback que no depende de nombres).
# ===================================================================

set +e  # no morir si un pkill no encuentra nada

# ── FRIDAY: API (8000) + Dashboard (8510) + Scheduler ─────────────
# Por patrón de línea de comando:
pkill -9 -f 'friday\.app' 2>/dev/null
pkill -9 -f 'venv/bin/friday' 2>/dev/null
pkill -9 -f 'streamlit run' 2>/dev/null

# Por puerto (fallback brutal pero efectivo):
sleep 0.5
fuser -k 8000/tcp 2>/dev/null
fuser -k 8510/tcp 2>/dev/null

# ── Ollama (el modelo LLM local) ──────────────────────────────────
ollama stop 2>/dev/null
sleep 1
pkill -9 ollama 2>/dev/null
pkill -9 llama 2>/dev/null

sleep 1
echo done
