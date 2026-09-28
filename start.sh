#!/bin/bash
# ===================================================================
# FRIDAY — Startup script (macOS / Linux)
# Lanza API + HUD + scheduler en background. Pidfile → sin duplicados.
# Asegura Ollama (cerebro local de fallback) antes de arrancar.
# ===================================================================

set -euo pipefail

# Raíz del repo = carpeta de este script (sin rutas hardcodeadas).
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$PROJECT_DIR/.friday.pid"
LOGFILE="$PROJECT_DIR/friday.log"
API_PORT="${API_PORT:-8000}"

# --- Evitar ejecución duplicada ---
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[$(date)] FRIDAY ya está corriendo (PID $OLD_PID)" | tee -a "$LOGFILE"
        exit 0
    fi
    rm -f "$PIDFILE"  # pidfile huérfano
fi

# --- Ollama: si no responde, levantarlo (brew services en macOS, serve si no) ---
if command -v ollama >/dev/null 2>&1 && ! curl -sf http://127.0.0.1:11434/api/version >/dev/null; then
    if [ "$(uname)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        brew services start ollama >/dev/null 2>&1 || true
    else
        (nohup ollama serve >/dev/null 2>&1 &)
    fi
fi

# --- Activar entorno y lanzar ---
cd "$PROJECT_DIR"
source venv/bin/activate

echo "[$(date)] Iniciando FRIDAY..." >> "$LOGFILE"
nohup python -m friday.app --api-port "$API_PORT" >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
echo "[$(date)] FRIDAY iniciado con PID $(cat "$PIDFILE") → http://127.0.0.1:$API_PORT/" | tee -a "$LOGFILE"
