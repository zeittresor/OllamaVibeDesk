@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run install_windows.bat first. The release build requires the verified environment.
    exit /b 1
)
".venv\Scripts\python.exe" tools\build_release.py
if errorlevel 1 (
    echo Release build or tests failed.
    exit /b 1
)
echo Release ZIP and checksum are in the release folder.
exit /b 0
