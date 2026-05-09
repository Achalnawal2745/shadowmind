@echo off
title ShadowMind Starter
echo.
echo  ==========================================
echo   SHADOWMIND: STEALTH ASSISTANT IS STARTING
echo  ==========================================
echo.

:: Check if venv exists and activate it
if exist venv\Scripts\activate.bat (
    echo [✓] Activating Virtual Environment...
    call venv\Scripts\activate.bat
) else (
    echo [!] Warning: venv not found. Running with system python.
)

echo [✓] Launching ShadowMind...
python main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] ShadowMind crashed or closed with error.
    pause
)
