@echo off
title 3D Home Tour - Server
echo.
echo   Starting 3D Home Tour...
echo.

:: Try python, py, python3
where python >nul 2>&1
if %errorlevel% equ 0 (
    python "%~dp0server.py" %*
    goto :end
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py "%~dp0server.py" %*
    goto :end
)

where python3 >nul 2>&1
if %errorlevel% equ 0 (
    python3 "%~dp0server.py" %*
    goto :end
)

echo.
echo   [ERROR] Python not found!
echo   Install Python from https://www.python.org/downloads/
echo   Make sure to check "Add Python to PATH" during install.
echo.

:end
pause
