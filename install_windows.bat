@echo off
setlocal EnableExtensions EnableDelayedExpansion
title OllamaVibeDesk Installer

cd /d "%~dp0"

for /f %%E in ('echo prompt $E^| cmd') do set "ESC=%%E"
set "C_RESET=%ESC%[0m"
set "C_INFO=%ESC%[96m"
set "C_WARN=%ESC%[93m"
set "C_OK=%ESC%[92m"
set "C_ERR=%ESC%[91m"
set "C_DIM=%ESC%[90m"

echo !C_INFO!============================================!C_RESET!
echo !C_INFO!  OllamaVibeDesk - Windows Installer!C_RESET!
echo !C_INFO!============================================!C_RESET!
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo !C_ERR!Python launcher "py" was not found.!C_RESET!
    echo !C_WARN!Please install Python 3.10+ and enable "Add Python to PATH" or the Python Launcher.!C_RESET!
    pause
    exit /b 1
)

if not exist ".venv" (
    echo !C_INFO![1/4] Creating virtual environment...!C_RESET!
    py -3 -m venv .venv
    if errorlevel 1 (
        echo !C_ERR!Failed to create the virtual environment.!C_RESET!
        pause
        exit /b 1
    )
) else (
    echo !C_DIM![1/4] Virtual environment already exists.!C_RESET!
)

echo !C_INFO![2/4] Updating pip...!C_RESET!
call ".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo !C_ERR!Failed to update pip.!C_RESET!
    pause
    exit /b 1
)

echo !C_INFO![3/4] Installing dependencies...!C_RESET!
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo !C_ERR!Failed to install Python packages.!C_RESET!
    pause
    exit /b 1
)

if not exist "app_data" mkdir "app_data"
if not exist "app_data\audio" mkdir "app_data\audio"
if not exist "app_data\cache" mkdir "app_data\cache"
if not exist "app_data\chats" mkdir "app_data\chats"
if not exist "app_data\logs" mkdir "app_data\logs"

echo !C_OK![4/4] Installation complete.!C_RESET!
echo.
echo !C_WARN!The app will start automatically soon. Press N to cancel the first launch.!C_RESET!
for /L %%S in (10,-1,1) do (
    <nul set /p "=!ESC![2K!ESC![1G!C_WARN!Autostart in %%S s (N=cancel)!C_RESET!"
    choice /C NS /N /T 1 /D S >nul
    if errorlevel 2 (
        rem continue countdown
    ) else (
        echo.
        echo !C_DIM!First launch canceled.!C_RESET!
        goto end_install
    )
)
echo.
call run_windows.bat
:end_install
endlocal
