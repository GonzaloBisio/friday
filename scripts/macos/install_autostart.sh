#!/bin/bash
# Instala el listener de voz como LaunchAgent: arranca al iniciar sesión, queda
# escuchando "FRIDAY" y, al oírla, levanta el backend (start.sh). Idempotente.
#   bash scripts/macos/install_autostart.sh
# Log del listener: voices/friday-wake.log · stdout/stderr de launchd: voices/launchd.log
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LABEL="com.friday.wake"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

[ -x "$REPO/venv/bin/python" ] || { echo "Falta el venv: ver README (Instalación)"; exit 1; }
mkdir -p "$REPO/voices" "$HOME/Library/LaunchAgents"
sed "s#__REPO__#$REPO#g" "$REPO/scripts/macos/$LABEL.plist.template" > "$DEST"

# Re-instalar limpio si ya estaba cargado.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "✓ $LABEL instalado y corriendo ($DEST)"
echo "  Estado:  launchctl print gui/$(id -u)/$LABEL | grep state"
echo "  Log:     tail -f $REPO/voices/friday-wake.log"
