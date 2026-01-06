@echo off
REM BLine Windows Build Script (Batch)
REM This is a simple wrapper that calls the PowerShell script

echo ========================================
echo Building BLine for Windows
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.11 or higher from python.org
    pause
    exit /b 1
)

REM Run the PowerShell build script
powershell -ExecutionPolicy Bypass -File "%~dp0build-windows.ps1" %*

if errorlevel 1 (
    echo.
    echo Build failed!
    pause
    exit /b 1
)

echo.
pause
