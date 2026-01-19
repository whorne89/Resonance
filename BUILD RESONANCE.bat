@echo off
title Building Resonance Executable
color 0B

echo.
echo ================================================
echo     BUILDING RESONANCE EXECUTABLE
echo ================================================
echo.
echo This will create a standalone .exe file that:
echo - Shows "Resonance" instead of Python
echo - Runs without a console window
echo - Can be double-clicked to start
echo.
echo Installing dependencies with uv...
uv sync
echo.
echo ================================================
echo Building executable...
echo ================================================
echo.
uv run pyinstaller build_exe.spec --clean --noconfirm
echo.
echo ================================================
echo BUILD COMPLETE!
echo ================================================
echo.
echo The executable is located at:
echo dist\Resonance\Resonance.exe
echo.
echo You can create a shortcut to this file and
echo place it anywhere (Desktop, Start Menu, etc.)
echo.
pause
