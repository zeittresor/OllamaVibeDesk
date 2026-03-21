@echo off
setlocal
title OllamaVibeDesk Installer

cd /d "%~dp0"

echo ============================================
echo   OllamaVibeDesk - Windows Installer
echo ============================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo Python launcher "py" wurde nicht gefunden.
    echo Bitte installiere Python 3.10+ und aktiviere "Add Python to PATH" bzw. den Python Launcher.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/4] Erstelle virtuelle Umgebung...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo Fehler beim Erstellen der virtuellen Umgebung.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Virtuelle Umgebung existiert bereits.
)

echo [2/4] Aktualisiere pip...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo Fehler beim Aktualisieren von pip.
    pause
    exit /b 1
)

echo [3/4] Installiere Abhaengigkeiten...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Fehler beim Installieren der Python-Pakete.
    pause
    exit /b 1
)

if not exist "app_data" mkdir "app_data"
if not exist "app_dataudio" mkdir "app_dataudio"
if not exist "app_data\cache" mkdir "app_data\cache"
if not exist "app_data\chats" mkdir "app_data\chats"

echo [4/4] Installation abgeschlossen.
echo.
echo Die App wird in 10 Sekunden automatisch gestartet.
echo Druecke N, um den ersten Start abzubrechen.
choice /C YN /N /T 10 /D Y /M "Automatisch mit run_windows.bat starten? [Y/N]"
if errorlevel 2 goto end_install
call run_windows.bat
:end_install
endlocal
