#!/bin/bash
# ===================================================================
# FRIDAY — Stop script (WSL)
# Detiene el proceso de Friday de forma elegante.
# ===================================================================

set -euo pipefail

PROJECT_DIR="/home/gonzalo/dev/personal/friday"
PIDFILE="$PROJECT_DIR/.friday.pid"
LOGFILE="$PROJECT_DIR/friday.log"

if [ ! -f "$PIDFILE" ]; then
    echo "FRIDAY no está corriendo (no se encontró $PIDFILE)"
    exit 1
fi

PID=$(cat "$PIDFILE")

if kill -0 "$PID" 2>/dev/null; then
    echo "[$(date)] Deteniendo FRIDAY (PID $PID)..." | tee -a "$LOGFILE"
    kill "$PID"
    sleep 2

    if kill -0 "$PID" 2>/dev/null; then
        echo "Forzando cierre..." | tee -a "$LOGFILE"
        kill -9 "$PID"
    fi

    rm -f "$PIDFILE"
    echo "[$(date)] FRIDAY detenido." | tee -a "$LOGFILE"
else
    echo "El proceso $PID ya no existe. Limpiando pidfile..."
    rm -f "$PIDFILE"
fi
