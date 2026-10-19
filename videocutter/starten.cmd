@echo off
rem Videocutter starten: Server auf diesem Rechner, die App öffnet sich im Browser.
rem Dieses Fenster offen lassen, solange du arbeitest. Schließen beendet den Videocutter.
chcp 65001 >nul
title Videocutter
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python server.py
) else (
  py server.py
)
if errorlevel 1 pause
