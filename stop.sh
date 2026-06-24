#!/bin/bash
# ===================================================================
# FRIDAY — Stop script (WSL)
# Detiene TODOS los procesos de Friday (API + Dashboard + Scheduler)
# sin importar cómo fueron arrancados, más Ollama.
# ===================================================================

set +e  # no morir si un pkill no encuentra nada

PROJECT_DIR="/home/gonzalo/dev/personal/friday"
PIDFILE="$PROJECT_DIR/.friday.pid"
LOGFILE="$PROJECT_DIR/friday.log"
SHUTDOWN_SCRIPT="$PROJECT_DIR/friday/voice/shutdown_friday.sh"

echo "[$(date)] Deteniendo FRIDAY..." | tee -a "$LOGFILE"

# 1. Matar por PID si hay pidfile (arranque via start.sh)
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

# 2. Matar por patrón + puerto (cubre arranque via launch_friday/windows_wake.py,
#    ./venv/bin/friday, o cualquier otro método).
if [ -x "$SHUTDOWN_SCRIPT" ]; then
    bash "$SHUTDOWN_SCRIPT" > /dev/null 2>&1
else
    # Fallback si el script no existe (no debería pasar)
    pkill -9 -f 'friday\.app' 2>/dev/null
    pkill -9 -f 'venv/bin/friday' 2>/dev/null
    pkill -9 -f 'streamlit run' 2>/dev/null
    sleep 0.5
    fuser -k 8000/tcp 2>/dev/null
    fuser -k 8510/tcp 2>/dev/null
    pkill -9 ollama 2>/dev/null
    pkill -9 llama 2>/dev/null
    sleep 1
fi

echo "[$(date)] FRIDAY detenido." | tee -a "$LOGFILE"
