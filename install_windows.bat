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
    echo Python launcher "py" was not found.
    echo Please install Python 3.10+ and enable "Add Python to PATH" or the Python Launcher.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Virtual environment already exists.
)

echo [2/4] Updating pip...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo Failed to update pip.
    pause
    exit /b 1
)

echo [3/4] Installing dependencies...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install Python packages.
    pause
    exit /b 1
)

if not exist "app_data" mkdir "app_data"
if not exist "app_data\audio" mkdir "app_data\audio"
if not exist "app_data\cache" mkdir "app_data\cache"
if not exist "app_data\chats" mkdir "app_data\chats"

echo [4/4] Installation complete.
echo.
echo The app will start automatically soon.
echo Press N during the countdown to cancel the first launch.
for /L %%S in (10,-1,1) do (
    echo Starting automatically with run_windows.bat in %%S seconds... Press N to cancel.
    choice /C NS /N /T 1 /D S >nul
    if errorlevel 1 if not errorlevel 2 (
        echo.
        echo First launch canceled.
        goto end_install
    )
)
echo.
call run_windows.bat
:end_install
endlocal
