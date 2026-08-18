@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OllamaVibeDesk - CrispASR Setup

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo [FEHLER] Windows PowerShell wurde nicht gefunden.
  pause
  exit /b 1
)

set "VARIANT=legacy"
set "QUIET=0"
if /I "%~1"=="cpu" set "VARIANT=cpu"
if /I "%~1"=="vulkan" set "VARIANT=vulkan"
if /I "%~1"=="cuda" set "VARIANT=cuda"
if /I "%~2"=="quiet" set "QUIET=1"

echo Installiere CrispASR fuer Windows ^(%VARIANT%^) ...
echo Der Standard "legacy" setzt AVX2 nicht voraus.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_crispasr.ps1" -Variant "%VARIANT%"
if errorlevel 1 (
  echo.
  echo [FEHLER] CrispASR konnte nicht installiert werden.
  if "%QUIET%"=="0" pause
  exit /b 1
)

echo.
echo [OK] Sprachlaufzeit installiert.
if "%QUIET%"=="0" pause
exit /b 0
