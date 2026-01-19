@echo off
REM This script checks if uv is installed and auto-installs it if needed

REM Check if uv is already installed
where uv >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    REM uv is installed, exit successfully
    exit /b 0
)

REM uv is not installed - show popup and install
echo uv package manager not found. Installing automatically...

REM Show popup notification using PowerShell
powershell -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('uv package manager is not installed and is required to run Resonance.', 'Installing uv', 'OK', 'Information')" >nul 2>nul

REM If PowerShell message box fails, fall back to echo
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ================================================
    echo  UV PACKAGE MANAGER NOT FOUND
    echo ================================================
    echo.
    echo Installing uv automatically...
    echo This is required to run Resonance.
    echo.
)

REM Install uv using the official PowerShell installer
echo Installing uv via PowerShell...
powershell -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ================================================
    echo  ERROR: Failed to install uv automatically
    echo ================================================
    echo.
    echo Please install uv manually using one of these methods:
    echo.
    echo 1. PowerShell ^(as Administrator^):
    echo    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo.
    echo 2. Using pip:
    echo    pip install uv
    echo.
    echo 3. Download from: https://docs.astral.sh/uv/
    echo.
    pause
    exit /b 1
)

REM Refresh PATH for current session
echo Refreshing PATH...
call refreshenv >nul 2>nul

REM Check if uv is now available
where uv >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ================================================
    echo  UV INSTALLED - PLEASE RESTART
    echo ================================================
    echo.
    echo uv has been installed successfully, but you need to
    echo close this window and run the batch file again.
    echo.
    echo ^(This is needed to refresh the PATH environment^)
    echo.
    pause
    exit /b 1
)

echo uv installed successfully!
exit /b 0
