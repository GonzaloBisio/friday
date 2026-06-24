#!/bin/bash
# ===================================================================
# test_shutdown.sh — Test de integración del shutdown de FRIDAY.
#
# Verifica que shutdown_friday.sh mata TODOS los procesos:
#   1. Arranca FRIDAY via ./venv/bin/friday (como launch_friday)
#   2. Verifica puertos 8000 (API) y 8510 (Dashboard) escuchando
#   3. Ejecuta shutdown_friday.sh
#   4. Verifica que puertos quedaron libres
#   5. Verifica que no quedan procesos friday/streamlit vivos
#
# Uso: bash tests/voice/test_shutdown.sh
# ===================================================================

set -u

PROJECT_DIR="/home/gonzalo/dev/personal/friday"
SHUTDOWN_SCRIPT="$PROJECT_DIR/friday/voice/shutdown_friday.sh"
FRIDAY_BIN="$PROJECT_DIR/venv/bin/friday"
PASS=0
FAIL=0

# ── Helpers ────────────────────────────────────────────────────────
green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }
bold()  { printf "\033[1m%s\033[0m\n" "$1"; }

check_port_up() {
    local port=$1
    ss -tlnp 2>/dev/null | grep -q ":${port}.*LISTEN"
}

check_port_down() {
    local port=$1
    ! ss -tlnp 2>/dev/null | grep -q ":${port}.*LISTEN"
}

count_friday_procs() {
    pgrep -af 'friday\.app|venv/bin/friday|streamlit run' 2>/dev/null \
        | grep -v 'pgrep\|test_shutdown\|shutdown_friday\.sh\|grep' | wc -l
}

cleanup() {
    # Si el test falla a mitad, limpiar todo para no dejar procesos colgados.
    bash "$SHUTDOWN_SCRIPT" > /dev/null 2>&1
}
trap cleanup EXIT

# ── Test ───────────────────────────────────────────────────────────
bold "=========================================="
bold "  Test: Shutdown de FRIDAY"
bold "=========================================="

# 0. Limpiar cualquier instancia previa
echo ""
echo "[0] Limpiando instancias previas..."
bash "$SHUTDOWN_SCRIPT" > /dev/null 2>&1
sleep 2

PREV=$(count_friday_procs)
if [ "$PREV" -ne 0 ]; then
    red "  FAIL: Hay $PREV procesos friday corriendo y no se pudieron limpiar"
    FAIL=$((FAIL + 1))
    exit 1
fi
green "  OK: ambiente limpio."

# 1. Arrancar FRIDAY via ./venv/bin/friday (como launch_friday)
echo ""
echo "[1] Arrancando FRIDAY via ./venv/bin/friday..."
cd "$PROJECT_DIR"
nohup "$FRIDAY_BIN" --api-port 8000 --dashboard-port 8510 > /tmp/friday_shutdown_test.log 2>&1 &
FRIDAY_PID=$!
echo "  PID lancado: $FRIDAY_PID"

# 2. Esperar a que API (8000) y Dashboard (8510) escuchen
echo ""
echo "[2] Esperando puertos 8000 + 8510..."
WAIT_OK=0
for i in $(seq 1 30); do
    if check_port_up 8000 && check_port_up 8510; then
        WAIT_OK=1
        break
    fi
    sleep 1
done

if [ "$WAIT_OK" -eq 1 ]; then
    green "  OK: API (8000) y Dashboard (8510) escuchando."
else
    red "  FAIL: FRIDAY no arrancó en 30s."
    cat /tmp/friday_shutdown_test.log 2>/dev/null | tail -20
    FAIL=$((FAIL + 1))
    exit 1
fi

# Confirmar que el proceso está vivo y es del tipo ./venv/bin/friday
PROC_LINE=$(ps -o pid,cmd -p "$FRIDAY_PID" --no-headers 2>/dev/null)
echo "  Proceso: $PROC_LINE"
if echo "$PROC_LINE" | grep -q 'venv/bin/friday'; then
    green "  OK: arrancado via ./venv/bin/friday (reproduce escenario Windows)."
else
    red "  WARN: el proceso no es ./venv/bin/friday: $PROC_LINE"
fi

# 3. Ejecutar shutdown
echo ""
echo "[3] Ejecutando shutdown_friday.sh..."
bash "$SHUTDOWN_SCRIPT"
SHUTDOWN_OUT=$(bash "$SHUTDOWN_SCRIPT" 2>/dev/null)
if echo "$SHUTDOWN_OUT" | grep -q "done"; then
    green "  OK: script completó (echo done)."
else
    red "  FAIL: script no completó. Output: $SHUTDOWN_OUT"
    FAIL=$((FAIL + 1))
fi

sleep 2

# 4. Verificar puertos libres
echo ""
echo "[4] Verificando puertos libres..."
if check_port_down 8000; then
    green "  OK: puerto 8000 (API) libre."
else
    red "  FAIL: puerto 8000 sigue escuchando."
    FAIL=$((FAIL + 1))
fi

if check_port_down 8510; then
    green "  OK: puerto 8510 (Dashboard) libre."
else
    red "  FAIL: puerto 8510 sigue escuchando."
    FAIL=$((FAIL + 1))
fi

# 5. Verificar que no quedan procesos friday/streamlit
echo ""
echo "[5] Verificando que no quedan procesos friday..."
REMAINING=$(count_friday_procs)
if [ "$REMAINING" -eq 0 ]; then
    green "  OK: no quedan procesos friday/streamlit vivos."
else
    red "  FAIL: quedan $REMAINING procesos:"
    pgrep -af 'friday\.app|venv/bin/friday|streamlit run' 2>/dev/null \
        | grep -v 'pgrep\|test_shutdown\|shutdown_friday\|grep'
    FAIL=$((FAIL + 1))
fi

# ── Resultado ──────────────────────────────────────────────────────
echo ""
bold "=========================================="
if [ "$FAIL" -eq 0 ]; then
    green "  RESULTADO: PASS (todas las verificaciones OK)"
    bold "=========================================="
    exit 0
else
    red "  RESULTADO: FAIL ($FAIL verificaciones fallaron)"
    bold "=========================================="
    exit 1
fi
