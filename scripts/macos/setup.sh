#!/bin/bash
# ===================================================================
# FRIDAY — instalación completa en macOS (Apple Silicon). Idempotente:
# se puede correr de nuevo sin romper nada (saltea lo que ya está).
#
#   bash scripts/macos/setup.sh              # todo
#   bash scripts/macos/setup.sh --no-autostart
#
# Qué hace: brew deps → venv py3.12 + pip → modelos de voz → Ollama +
# Gemma 4 → .env inicial → LaunchAgent del listener (autostart).
# ===================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VOICES="$REPO/voices"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b-it-qat}"
step() { printf "\n\033[1m▶ %s\033[0m\n" "$1"; }

step "1/6 Dependencias del sistema (Homebrew)"
command -v brew >/dev/null || { echo "Instalá Homebrew: https://brew.sh"; exit 1; }
brew install python@3.12 portaudio ollama ffmpeg

step "2/6 Entorno Python 3.12 + FRIDAY (backend + voz + dev)"
[ -x "$REPO/venv/bin/python" ] || /opt/homebrew/bin/python3.12 -m venv "$REPO/venv"
"$REPO/venv/bin/pip" install -q --upgrade pip
"$REPO/venv/bin/pip" install -q -e "$REPO[ir,voice,dev]"

step "3/6 Modelos de voz → voices/"
mkdir -p "$VOICES"
if [ ! -d "$VOICES/vosk-model-small-en-us-0.15" ]; then
    curl -sSfL -o "$VOICES/vosk.zip" https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
    unzip -q -o "$VOICES/vosk.zip" -d "$VOICES" && rm "$VOICES/vosk.zip"
fi
PIPER=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high
for f in en_US-ryan-high.onnx en_US-ryan-high.onnx.json; do
    [ -f "$VOICES/$f" ] || curl -sSfL -o "$VOICES/$f" "$PIPER/$f"
done
[ -f "$VOICES/jarvis.wav" ] || echo "  ⚠ Falta voices/jarvis.wav (voz Jarvis). Sin él se usa Piper/Ryan. Ver docs/MIGRATION.md"
# whisper-large-v3-turbo (MLX, ~1.6GB) se baja solo en el primer arranque del listener.

step "4/6 Ollama (servicio al login) + $OLLAMA_MODEL"
brew services start ollama >/dev/null
for _ in $(seq 1 30); do curl -sf http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
# `ollama pull` puede salir 0 tras un timeout de red: verificar y reintentar.
for _ in 1 2 3; do
    ollama list | grep -q "^${OLLAMA_MODEL}" && break
    ollama pull "$OLLAMA_MODEL" || true
done
ollama list | grep -q "^${OLLAMA_MODEL}" || { echo "  ✗ No se pudo bajar $OLLAMA_MODEL"; exit 1; }

step "5/6 Configuración (.env)"
if [ ! -f "$REPO/.env" ]; then
    printf '# Ver .env.example. Sin GEMINI_API_KEY → 100%% local.\nLLM_PROVIDER=ollama\n' > "$REPO/.env"
    echo "  .env creado con LLM_PROVIDER=ollama (agregá GEMINI_API_KEY y pasá a gemini)"
else
    echo "  .env ya existe (no lo toco)"
fi

step "6/6 Autostart del listener de voz"
if [ "${1:-}" = "--no-autostart" ]; then
    echo "  salteado (--no-autostart)"
else
    bash "$REPO/scripts/macos/install_autostart.sh"
fi

printf "\n\033[32m✓ FRIDAY instalado.\033[0m Decí \"FRIDAY\" o corré: bash start.sh → http://127.0.0.1:8000/\n"
printf "  macOS pedirá permiso de Micrófono la primera vez (Ajustes → Privacidad).\n"
