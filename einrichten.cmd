@echo off
rem Doppelklick: prueft, ob auf diesem Rechner alles fuer das Videoschnitt-Paket da ist. Installiert nichts.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0einrichten.ps1" %*
echo.
pause
