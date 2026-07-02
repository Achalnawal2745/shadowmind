@echo off
title ShadowMind Compiler
echo.
echo  ============================================
echo   COMPILING SHADOWMIND TO STEALTH BINARY
echo  ============================================
echo.

:: Check and activate virtual environment
if exist venv\Scripts\activate.bat (
    echo [✓] Activating Virtual Environment...
    call venv\Scripts\activate.bat
) else (
    echo [!] Warning: venv not found. Using system environment.
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

:: Copy config.json to dist directory so it's ready to use next to the exe
echo [✓] Copying config.json to dist/ folder...
if not exist dist mkdir dist
copy config.json dist\config.json /Y

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
