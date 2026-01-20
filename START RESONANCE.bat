@echo off
cd /d "%~dp0"

REM Use local cache to avoid OneDrive hardlink issues
set UV_CACHE_DIR=%~dp0.uv-cache

REM Only sync on first run (when .venv doesn't exist)
if not exist ".venv" (
    uv sync
)

start /B uv run pythonw src\main.py
