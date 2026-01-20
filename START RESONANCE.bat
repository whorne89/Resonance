@echo off
cd /d "%~dp0"

REM Check if uv is installed, auto-install if needed
call check_uv.bat
if %ERRORLEVEL% NEQ 0 exit /b 1

REM Use local cache to avoid OneDrive hardlink issues
set UV_CACHE_DIR=%~dp0.uv-cache

uv sync --no-audit
start /B uv run pythonw src\main.py
