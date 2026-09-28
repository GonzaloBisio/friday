#!/bin/bash
# ===================================================================
# shutdown_friday.sh — Mata TODOS los procesos de FRIDAY (+ Ollama con
# --with-ollama). macOS y Linux.
#
# Diseñado para NO matchearse a sí mismo: los patrones de pkill no
# aparecen en la línea de comando con la que se invoca este script.
#
# Cubre: `python -m friday.app` (start.sh), `venv/bin/friday` (listener),
# `streamlit run` (dashboard legacy). Fallback por puerto con lsof/fuser.
# ===================================================================

set +e

pkill -9 -f 'friday\.app' 2>/dev/null
pkill -9 -f 'venv/bin/friday( |$)' 2>/dev/null  # no matchea venv/bin/friday-wake
pkill -9 -f 'streamlit run' 2>/dev/null

# Por puerto: lsof existe en macOS y casi todo Linux; fuser como fallback.
sleep 0.5
for port in 8000 8510; do
    if command -v lsof >/dev/null 2>&1; then
        lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null | xargs kill -9 2>/dev/null
    elif command -v fuser >/dev/null 2>&1; then
        fuser -k "$port/tcp" 2>/dev/null
    fi
done

# Ollama: SIEMPRE descargar los modelos de la RAM (en 16GB son ~6GB que vuelven).
# El SERVIDOR queda vivo (servicio de login vía `brew services`) para que la
# próxima wake word no espere el arranque; --with-ollama lo apaga también.
if command -v ollama >/dev/null 2>&1; then
    ollama ps 2>/dev/null | awk 'NR>1 {print $1}' | xargs -n1 ollama stop 2>/dev/null
fi
if [ "$1" = "--with-ollama" ]; then
    if [ "$(uname)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        brew services stop ollama >/dev/null 2>&1
    fi
    sleep 1
    pkill -9 -x ollama 2>/dev/null
fi

sleep 1
echo done
