@echo off
title ShadowMind Starter
echo.
echo  ==========================================
echo   SHADOWMIND: STEALTH ASSISTANT IS STARTING
echo  ==========================================
echo.

:: Check if venv exists and activate it
if not exist venv\Scripts\activate.bat (
    echo [!] Virtual environment venv not found. Creating it now...
    python -m venv venv
    if errorlevel 1 (
        echo [X] Failed to create virtual environment. Please verify Python is installed on your system PATH.
        pause
        exit /b 1
    )
    echo [✓] Activating Virtual Environment...
    call venv\Scripts\activate.bat
    echo [✓] Upgrading pip and installing project dependencies...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [X] Failed to install dependencies.
        pause
        exit /b 1
    )
) else (
    echo [✓] Activating Virtual Environment...
    call venv\Scripts\activate.bat
)

echo [✓] Launching ShadowMind...
python main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] ShadowMind crashed or closed with error.
    pause
)
