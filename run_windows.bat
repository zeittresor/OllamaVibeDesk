@echo off
setlocal
title OllamaVibeDesk

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo The virtual environment was not found.
    echo Please run install_windows.bat first.
    pause
    exit /b 1
)

if not exist "app_data" mkdir "app_data"
if not exist "app_data\audio" mkdir "app_data\audio"
if not exist "app_data\cache" mkdir "app_data\cache"
if not exist "app_data\chats" mkdir "app_data\chats"

set "HF_HOME=%CD%\app_data\cache\hf_home"
set "TRANSFORMERS_CACHE=%CD%\app_data\cache\transformers"
set "PYTHONUTF8=1"

call ".venv\Scripts\python.exe" -m app.main
endlocal
