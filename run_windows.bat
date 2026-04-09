@echo off
setlocal EnableExtensions

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
if not exist "app_data\logs" mkdir "app_data\logs"

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

rem Start the GUI with a minimized helper console instead of closing it accidentally.
if /I "%~1"=="--here" goto run_here

start "OllamaVibeDesk" /min cmd /c call "%~f0" --here
exit /b 0

:run_here
call ".venv\Scripts\python.exe" -m app.main
endlocal
