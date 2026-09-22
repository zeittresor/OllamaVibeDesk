@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "requirements.txt" (
    echo requirements.txt was not found.
    exit /b 1
)

set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=py -3"
)
if not defined PYTHON_EXE (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    echo Python 3.10 or newer was not found.
    exit /b 1
)

if not exist "wheelhouse" mkdir "wheelhouse"
echo Downloading all application dependencies into wheelhouse ...
%PYTHON_EXE% -m pip download --only-binary=:all: -r requirements.txt -d wheelhouse
if errorlevel 1 (
    echo No complete compatible binary wheelhouse could be built for this Python/platform.
    echo Use supported 64-bit Python; no automatic source compilation is attempted.
    exit /b 1
)
if errorlevel 1 exit /b 1

echo Wheelhouse completed successfully.
endlocal
