#!/bin/bash
# ===================================================================
# FRIDAY — Stop script (macOS / Linux)
# Detiene API + HUD + scheduler (se hayan arrancado como se hayan
# arrancado) y, con --with-ollama, también Ollama.
# ===================================================================

set +e  # no morir si un pkill no encuentra nada

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$PROJECT_DIR/.friday.pid"
LOGFILE="$PROJECT_DIR/friday.log"

echo "[$(date)] Deteniendo FRIDAY..." | tee -a "$LOGFILE"

# 1. Por PID (arranque via start.sh): SIGTERM y, si no alcanza, SIGKILL.
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null
        sleep 1
        kill -9 "$PID" 2>/dev/null
        echo "  PID $PID terminado."
    fi
    rm -f "$PIDFILE"
fi

# 2. Por patrón + puerto (cubre el arranque desde el listener de voz, etc.).
bash "$PROJECT_DIR/friday/voice/shutdown_friday.sh" "$@" > /dev/null 2>&1

echo "[$(date)] FRIDAY detenido." | tee -a "$LOGFILE"
