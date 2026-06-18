#!/bin/bash
# ===================================================================
# FRIDAY — Startup script (WSL)
# Lanza el scheduler + Streamlit dashboard en background.
# Usa un pidfile para evitar ejecuciones duplicadas.
# ===================================================================

set -euo pipefail

PROJECT_DIR="/home/gonzalo/dev/personal/friday"
PIDFILE="$PROJECT_DIR/.friday.pid"
LOGFILE="$PROJECT_DIR/friday.log"

# --- Evitar ejecución duplicada ---
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[$(date)] FRIDAY ya está corriendo (PID $OLD_PID)" >> "$LOGFILE"
        exit 0
    fi
    # PID file exists but process is dead — cleanup
    rm -f "$PIDFILE"
fi

# --- Activar entorno y lanzar ---
cd "$PROJECT_DIR"
source venv/bin/activate

echo "[$(date)] Iniciando FRIDAY..." >> "$LOGFILE"

# Lanza en background y guarda el PID
nohup python -m friday.app --dashboard --port 8510 >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

echo "[$(date)] FRIDAY iniciado con PID $(cat $PIDFILE)" >> "$LOGFILE"
