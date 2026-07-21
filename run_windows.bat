@echo off
setlocal EnableExtensions
set "APP_VERSION=v2.0"
title OllamaVibeDesk %APP_VERSION%
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo The local virtual environment was not found.
    echo Please run install_windows.bat first.
    pause
    exit /b 1
)

for %%D in (
    "app_data"
    "app_data\audio"
    "app_data\cache"
    "app_data\chats"
    "app_data\debug_logs"
    "app_data\generated_code"
    "app_data\knowledge_base"
    "app_data\logs"
) do if not exist "%%~D" mkdir "%%~D"

set "HF_HOME=%CD%\app_data\cache\hf_home"
set "TRANSFORMERS_CACHE=%CD%\app_data\cache\transformers"
set "PYTHONUTF8=1"

set "OLLAMA_APP=%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
if errorlevel 1 (
    if exist "%OLLAMA_APP%" start "Ollama" "%OLLAMA_APP%"
    if not exist "%OLLAMA_APP%" if exist "%OLLAMA_EXE%" start "Ollama" "%OLLAMA_EXE%" serve
)

if /I "%~1"=="--here" goto run_here
start "OllamaVibeDesk %APP_VERSION%" /min cmd /c call "%~f0" --here
exit /b 0

:run_here
call ".venv\Scripts\python.exe" -m app.main
if errorlevel 1 (
    echo.
    echo OllamaVibeDesk ended with an error. Check app_data\debug_logs and app_data\logs.
    pause
)
endlocal
