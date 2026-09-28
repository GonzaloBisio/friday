# Migración Windows/WSL → Mac (M4)

> **Para una IA en la PC Windows:** leé este archivo entero y ejecutá la **Parte A**.
> Todo se hace desde WSL (Ubuntu), donde vive el repo viejo. No toques el código: solo movés
> archivos. Pedí confirmación a Gonzalo antes de cada `git push`.

FRIDAY ahora corre nativo en la Mac (desde 2026-09-27; el código de Windows/WSL se retiró).
En la PC vieja quedaron cosas que **no están en git** y hay que traer:

| Qué | Dónde está (PC vieja) | Cómo viaja | Destino en la Mac |
|---|---|---|---|
| **`jarvis.wav`** (opcional: clip ~9s para clonar la voz; sin él se usa `TTS_VOICE`) | `C:\Users\gonza\friday\voices\jarvis.wav` = `/mnt/c/Users/gonza/friday/voices/jarvis.wav` | **git** (excepción en `.gitignore`) | `~/friday/voices/jarvis.wav` |
| **`.env`** (GEMINI_API_KEY, Spotify, NEXCOURT, etc.) | `~/dev/personal/friday/.env` (WSL) | **NUNCA git.** Gestor de contraseñas o copia manual de los valores | `~/friday/.env` |
| Service account de Google Sheets (JSON) | ruta en `GOOGLE_SHEETS_CREDENTIALS` del `.env` | igual que `.env` | `~/friday/` + actualizar la ruta en `.env` |
| `friday.db` (memorias, historial de chat, métricas) | `~/dev/personal/friday/friday.db` | opcional; igual que `.env` (datos personales) | `~/friday/friday.db` (con FRIDAY apagado) |
| `.ir_codes.json` (códigos IR aprendidos) | `~/dev/personal/friday/` | opcional; igual que `.env` | `~/friday/` |
| Acceso SSH a AXIS | `~/.ssh/config` (alias `axis`) + key | **no copiar la key privada**: ver Parte B.3 | `~/.ssh/` en la Mac |

## Parte A — En la PC Windows (WSL)

```bash
cd ~/dev/personal/friday
git status --short                                       # si hay cambios locales: NO descartarlos, preguntar
git fetch origin && git checkout main && git pull        # trae la versión Mac (con este archivo)

# jarvis.wav → repo (es el único binario de voz que se versiona)
cp /mnt/c/Users/gonza/friday/voices/jarvis.wav voices/jarvis.wav
git add voices/jarvis.wav
git commit -m "chore(voice): agregar jarvis.wav para clonar la voz en la Mac"
git push                                                 # ← confirmar con Gonzalo
```

Si `voices/jarvis.wav` aparece como ignorado, el pull no trajo el `.gitignore` nuevo: revisá que estés en
`main` actualizado (debe contener `!voices/jarvis.wav`).

**Secretos: la IA NO los lee ni los imprime** (`cat .env` los dejaría en el transcript). Gonzalo abre
`.env` por su cuenta (`notepad.exe "$(wslpath -w .env)"`) y copia a su gestor de contraseñas los valores
que quiera conservar. La `GEMINI_API_KEY` ni siquiera hace falta copiarla: se ve o se crea de nuevo en
https://aistudio.google.com/apikey.

Opcional, si Gonzalo quiere conservar memorias e historial: apagar FRIDAY (`bash stop.sh`) y copiar
`friday.db` por un medio privado (USB, AirDrop desde otro equipo, zip cifrado). No por git.

Al terminar: sacar `friday-wake.vbs` de `shell:startup` (Win+R → `shell:startup`) y `wsl --shutdown`.

## Parte B — En la Mac

```bash
cd ~/friday && git pull                                  # trae jarvis.wav
```

1. **`.env`**: pegar los valores y pasar a Gemini:
   ```ini
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=...
   ```
   ⚠️ **No copies líneas `GEMINI_MODEL_*` con modelos 2.x**: están deprecados y pisarían los defaults
   (ver [MODELS.md](MODELS.md)).
2. **Voz Jarvis (Pocket TTS)**: el modelo con clonado es *gated*. Aceptar los términos en
   https://huggingface.co/kyutai/pocket-tts y loguearse una vez: `./venv/bin/hf auth login`.
3. **AXIS**: generar una key nueva en la Mac y autorizarla en el droplet (desde una máquina que ya tenga
   acceso, o por la consola de DigitalOcean):
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/axis -C "friday-mac"
   # agregar ~/.ssh/axis.pub a ~/.ssh/authorized_keys del usuario axis en el droplet
   printf 'Host axis\n  HostName 174.138.52.161\n  User axis\n  IdentityFile ~/.ssh/axis\n' >> ~/.ssh/config
   ssh axis 'docker ps --format "{{.Names}}"'            # verificar
   ```
4. **AWS (NEXCOURT en modo cloudwatch)**: `aws configure sso` (o el login que uses). IAM read-only.
5. **Spotify**: rehacer el OAuth en la Mac (más simple que copiar el token): `./venv/bin/friday-spotify-auth`.
6. **Reiniciar el listener** para que tome la voz y la config:
   ```bash
   launchctl kickstart -k gui/$(id -u)/com.friday.wake
   tail -f voices/friday-wake.log     # debe decir "Pocket TTS cargado (voz clonada de jarvis.wav)"
   ```
