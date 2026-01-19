@echo off
cd /d "%~dp0"
uv sync
start /B uv run pythonw src\main.py
