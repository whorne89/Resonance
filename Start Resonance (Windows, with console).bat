@echo off
title Resonance - Voice to Text
color 0A

echo.
echo ================================================
echo          RESONANCE - Voice to Text
echo ================================================
echo.
echo Starting application...
echo.
echo HOTKEY: Ctrl+Alt+R (hold while speaking)
echo.
echo The gray circle icon will appear in your
echo system tray (bottom-right corner).
echo.
echo RIGHT-CLICK icon to change hotkey in Settings
echo.
echo First transcription: ~5-10 seconds (loading)
echo After that: 1-2 seconds per transcription
echo.
echo ================================================
echo.

cd /d "%~dp0"

REM Use local cache to avoid OneDrive hardlink issues
set UV_CACHE_DIR=%~dp0.uv-cache

uv sync
uv run python src\main.py

echo.
echo ================================================
echo Application stopped.
echo ================================================
pause
exit /b 0

:error
echo.
echo ================================================
echo Failed to start Resonance
echo ================================================
pause
exit /b 1
