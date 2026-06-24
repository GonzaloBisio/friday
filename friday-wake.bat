@echo off
REM FRIDAY Wake - prueba manual VISIBLE (con logs en pantalla).
REM El autostart OCULTO usa friday-wake.vbs en la carpeta de Inicio.

REM Sincroniza la ultima version del repo (si WSL esta accesible) y ejecuta la copia local.
copy /Y "\\wsl$\Ubuntu\home\gonzalo\dev\personal\friday\friday\voice\windows_wake.py" "C:\Users\gonza\friday\windows_wake.py" >nul 2>&1

REM py -3.12 fuerza Python 3.12 (el 3.14 no tiene wheels de pyaudio)
py -3.12 "C:\Users\gonza\friday\windows_wake.py"

pause
o