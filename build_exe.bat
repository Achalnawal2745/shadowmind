@echo off
title ShadowMind Compiler
echo.
echo  ============================================
echo   COMPILING SHADOWMIND TO STEALTH BINARY
echo  ============================================
echo.

:: Check and activate virtual environment
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


echo.
echo [✓] Starting Compilation (this will take 1-2 minutes)...
echo     Output will be saved as "IntelAudioService.exe" in the "dist" folder.
echo.

:: Compile with PyInstaller
pyinstaller --onefile --noconsole --name="IntelAudioService" main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Compilation failed. Please check the log above.
    pause
    exit /b %ERRORLEVEL%
)

:: Copy config.json to dist directory only if it doesn't already exist
if not exist dist mkdir dist
if not exist dist\config.json (
    echo [✓] Copying default config.json to dist/ folder...
    copy config.json dist\config.json /Y
) else (
    echo [✓] Key Preservation: dist\config.json already exists, keeping your current API keys intact.
)

echo.
echo  ============================================
echo   COMPILATION COMPLETED SUCCESSFULLY!
echo  ============================================
echo   Your stealth assistant is ready in:
echo   dist\IntelAudioService.exe
echo.
echo   How to run:
echo   Double-click dist\IntelAudioService.exe
echo   (No windows will pop up, it runs in background!)
echo.
echo   Keys: Ctrl+Q (Exit) / Alt+X (Panic Button)
echo  ============================================
echo.
pause
