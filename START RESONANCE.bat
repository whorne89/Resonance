@echo off
cd /d "%~dp0"

REM Use local cache to avoid OneDrive hardlink issues
set UV_CACHE_DIR=%~dp0.uv-cache

uv sync
start /B uv run pythonw src\main.py
