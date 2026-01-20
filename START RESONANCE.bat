@echo off
cd /d "%~dp0"

REM Use local cache to avoid OneDrive hardlink issues
set UV_CACHE_DIR=%~dp0.uv-cache

uv sync --no-audit
start /B uv run pythonw src\main.py
