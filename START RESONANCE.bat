@echo off
cd /d "%~dp0"

REM Check if uv is installed, auto-install if needed
call check_uv.bat
if %ERRORLEVEL% NEQ 0 exit /b 1

uv sync --link-mode=copy
start /B uv run pythonw src\main.py
