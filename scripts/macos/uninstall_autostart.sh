#!/bin/bash
# Saca el listener de voz del arranque y lo detiene.
LABEL="com.friday.wake"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && echo "✓ detenido" || echo "(no estaba cargado)"
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist" && echo "✓ removido del arranque"
