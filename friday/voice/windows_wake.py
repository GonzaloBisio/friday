"""
FRIDAY Wake — Windows native.
Escucha "FRIDAY" por micrófono, saluda con voz, lanza el sistema en WSL.

Requiere: pip install SpeechRecognition pyaudio gTTS
"""

import subprocess
import sys
import tempfile
import os
import random
from datetime import datetime


GREETINGS = {
    "morning": [
        "Buenos días, Gon. FRIDAY en línea.",
        "Buen día, Gonzalo. Sistema iniciado.",
    ],
    "afternoon": [
        "Buenas tardes, Gon. FRIDAY activo.",
        "Buenas tardes, Gonzalo. ¿En qué te ayudo?",
    ],
    "night": [
        "Buenas noches, Gon. FRIDAY listo.",
        "Buenas noches, Gonzalo. Modo nocturno activo.",
    ],
}


def get_greeting():
    h = datetime.now().hour
    if 6 <= h < 12:
        tod = "morning"
    elif 12 <= h < 19:
        tod = "afternoon"
    else:
        tod = "night"
    return random.choice(GREETINGS[tod])


def speak(text):
    """Genera MP3 con gTTS y lo reproduce en Windows."""
    from gtts import gTTS
    mp3_path = os.path.join(tempfile.gettempdir(), "friday_greeting.mp3")
    tts = gTTS(text=text, lang="es", slow=False)
    tts.save(mp3_path)
    # Windows: usar PowerShell para reproducir (evita dependencias)
    subprocess.run([
        "powershell", "-c",
        f'(New-Object Media.SoundPlayer "{mp3_path}").PlaySync()'
    ], capture_output=True)


def launch_friday():
    """Lanza FRIDAY en WSL."""
    subprocess.Popen([
        "wsl", "-d", "Ubuntu", "--",
        "bash", "-c",
        "cd /home/gonzalo/dev/personal/friday && ./venv/bin/friday"
    ])


def main():
    print("=" * 50)
    print("  FRIDAY WAKE — Escuchando...")
    print("  Decí 'FRIDAY' para activar")
    print("  Ctrl+C para salir")
    print("=" * 50)

    import speech_recognition as sr
    r = sr.Recognizer()

    # Ajustar ruido ambiente una vez al inicio
    try:
        with sr.Microphone() as source:
            print("Calibrando micrófono... (2 seg)")
            r.adjust_for_ambient_noise(source, duration=2)
            print("¡Listo! Escuchando wake word 'FRIDAY'...")
    except Exception as e:
        print(f"Error de micrófono: {e}")
        print("¿Tenés un micrófono conectado?")
        input("Presioná Enter para salir...")
        return

    while True:
        try:
            with sr.Microphone() as source:
                audio = r.listen(source, phrase_time_limit=3)

            text = r.recognize_google(audio, language="es-ES").lower()
            print(f"  → {text}")

            if "friday" in text or "fráiday" in text or "feri" in text:
                print("\n🎤 WAKE WORD DETECTADO!")
                greeting = get_greeting()
                print(f"  FRIDAY: {greeting}")
                speak(greeting)
                launch_friday()
                print("  Sistema lanzado. Seguí escuchando...\n")

        except sr.UnknownValueError:
            pass  # No entendió, seguir escuchando
        except sr.RequestError as e:
            print(f"  Error de red: {e}")
        except KeyboardInterrupt:
            print("\nChau!")
            break
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    main()
