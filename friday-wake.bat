@echo off
REM FRIDAY Wake — Doble-click para activar
REM Escucha "FRIDAY" por mic y abre el sistema

cd /d "\\wsl$\Ubuntu\home\gonzalo\dev\personal\friday"
python friday\voice\windows_wake.py
pause
