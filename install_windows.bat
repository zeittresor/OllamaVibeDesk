@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "PYTHONUTF8=1"
cd /d "%~dp0"

if not exist "version.txt" (
    echo ERROR: version.txt is missing.
    pause
    exit /b 1
)
set /p "APP_VERSION_NUMBER="<"version.txt"
if not defined APP_VERSION_NUMBER (
    echo ERROR: version.txt is empty.
    pause
    exit /b 1
)
set "APP_VERSION=v%APP_VERSION_NUMBER%"
title OllamaVibeDesk %APP_VERSION% Installer

for /f %%E in ('echo prompt $E^| cmd') do set "ESC=%%E"
set "C_RESET=%ESC%[0m"
set "C_INFO=%ESC%[96m"
set "C_WARN=%ESC%[93m"
set "C_OK=%ESC%[92m"
set "C_ERR=%ESC%[91m"
set "C_DIM=%ESC%[90m"

if not exist "app_data\logs" mkdir "app_data\logs"
set "INSTALL_LOG=app_data\logs\install_%APP_VERSION%.log"
>"%INSTALL_LOG%" echo OllamaVibeDesk %APP_VERSION% installer started %DATE% %TIME%

echo.
echo !C_INFO!  +-------------------------------------------------------------+!C_RESET!
echo !C_INFO!    OLLAMAVIBEDESK  %APP_VERSION%    /    WINDOWS-SETUP!C_RESET!
echo !C_INFO!  +-------------------------------------------------------------+!C_RESET!
echo !C_DIM!    Installation im aktuellen Projektordner!C_RESET!
echo !C_DIM!    Protokoll: %INSTALL_LOG%!C_RESET!
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo !C_ERR!Python 3 was not found.!C_RESET!
    echo !C_WARN!Install Python 3.10 or newer and enable the Python Launcher or PATH option.!C_RESET!
    >>"%INSTALL_LOG%" echo ERROR: Python 3 not found.
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) and sys.maxsize > 2**32 else 1)" >>"%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo !C_ERR!64-bit Python 3.10 or newer is required.!C_RESET!
    >>"%INSTALL_LOG%" echo ERROR: Python version is too old.
    pause
    exit /b 1
)

call :show_step 1 "Release-Dateien pruefen"
%PYTHON_CMD% tools\verify_installation.py --source-only >>"%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo !C_ERR!The release package is incomplete or damaged.!C_RESET!
    echo !C_WARN!See %INSTALL_LOG% for details.!C_RESET!
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    call :show_step 2 "Lokale Python-Umgebung anlegen"
    %PYTHON_CMD% -m venv .venv >>"%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo !C_ERR!Failed to create the virtual environment.!C_RESET!
        pause
        exit /b 1
    )
) else (
    call :show_step 2 "Vorhandene Python-Umgebung wiederverwenden"
)

call :show_step 3 "Python-Pakete installieren"
set "INSTALLED_OFFLINE=0"
".venv\Scripts\python.exe" -m pip check >>"%INSTALL_LOG%" 2>&1
if not errorlevel 1 (
    ".venv\Scripts\python.exe" tools\verify_installation.py --quick >>"%INSTALL_LOG%" 2>&1
    if not errorlevel 1 set "INSTALLED_OFFLINE=1"
)
if "!INSTALLED_OFFLINE!"=="0" if exist "wheelhouse\*.whl" (
    echo !C_DIM!Trying the local offline wheelhouse first...!C_RESET!
    ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse -r requirements.txt >>"%INSTALL_LOG%" 2>&1
    if not errorlevel 1 set "INSTALLED_OFFLINE=1"
)
if "!INSTALLED_OFFLINE!"=="0" (
    echo !C_INFO!Using the online package index...!C_RESET!
    ".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel >>"%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo !C_ERR!Failed to prepare pip.!C_RESET!
        echo !C_WARN!See %INSTALL_LOG% for details.!C_RESET!
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt >>"%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo !C_ERR!Failed to install Python packages.!C_RESET!
        echo !C_WARN!See %INSTALL_LOG% for details.!C_RESET!
        pause
        exit /b 1
    )
    if not exist "wheelhouse" mkdir "wheelhouse"
    ".venv\Scripts\python.exe" -m pip download --only-binary=:all: -r requirements.txt -d wheelhouse >>"%INSTALL_LOG%" 2>&1
    if errorlevel 1 echo !C_WARN!The app is installed, but the offline wheelhouse could not be refreshed completely.!C_RESET!
) else (
    echo !C_OK!Dependencies ready locally; no online upgrade required.!C_RESET!
)

call :show_step 4 "Portable Verzeichnisse vorbereiten"
for %%D in (
    "app_data" "app_data\audio" "app_data\cache" "app_data\chats"
    "app_data\config_profiles" "app_data\debug_logs"
    "app_data\knowledge_base" "app_data\logs"
    "app_data\tts" "app_data\auto_answer\phrases" "app_data\auto_answer\topic_words"
    "app_data\auto_answer\question_replies" "app_data\auto_answer\eliza"
    "app_data\personalities" "app_data\personalities\user" "app_data\personalities\assistant"
    "app_data\speech" "app_data\speech\crispasr"
    "OUTPUTS\audio\tts" "OUTPUTS\audio\recordings" "OUTPUTS\chat_exports"
    "OUTPUTS\code_blocks" "OUTPUTS\projects\workspaces" "OUTPUTS\projects\zips"
) do if not exist "%%~D" mkdir "%%~D"

call :show_step 5 "Pakete, Funktionen und GUI pruefen"
".venv\Scripts\python.exe" -m pip check >>"%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo !C_ERR!Installed package dependencies are inconsistent.!C_RESET!
    echo !C_WARN!See %INSTALL_LOG% for details.!C_RESET!
    pause
    exit /b 1
)
set "QT_QPA_PLATFORM=offscreen"
if exist "%WINDIR%\Fonts" set "QT_QPA_FONTDIR=%WINDIR%\Fonts"
".venv\Scripts\python.exe" tools\verify_installation.py >>"%INSTALL_LOG%" 2>&1
set "VERIFY_EXIT=!ERRORLEVEL!"
set "QT_QPA_PLATFORM="
set "QT_QPA_FONTDIR="
if not "!VERIFY_EXIT!"=="0" (
    echo !C_ERR!Installation verification failed; the app will not be started.!C_RESET!
    echo !C_WARN!See %INSTALL_LOG% for details.!C_RESET!
    echo !C_DIM!Letzte Protokollzeilen:!C_RESET!
    powershell -NoProfile -Command "Get-Content -LiteralPath '%INSTALL_LOG%' -Tail 9" 2>nul
    pause
    exit /b 1
)

call :show_step 6 "Empfohlenes Ollama-Modell pruefen"
".venv\Scripts\python.exe" tools\optional_default_model.py --check >>"%INSTALL_LOG%" 2>&1
if errorlevel 2 (
    echo !C_DIM!Local Ollama is unavailable; the model download can be done later.!C_RESET!
) else if errorlevel 1 (
    echo !C_INFO!Recommended: Huihui-Qwen3.8-27B-abliterated Q3_K_M - approx. 13.5 GB.!C_RESET!
    choice /C YN /N /T 10 /D N /M "Download the recommended Ollama model? [Y/N] "
    if errorlevel 2 (
        echo !C_DIM!Model download skipped. The app will use installed models.!C_RESET!
        >>"%INSTALL_LOG%" echo Recommended model declined or prompt timed out.
    ) else (
        echo !C_INFO!Downloading through local Ollama; this may take a while...!C_RESET!
        ".venv\Scripts\python.exe" tools\optional_default_model.py --pull
        if errorlevel 1 (
            echo !C_WARN!The model could not be downloaded. The app remains usable with installed models.!C_RESET!
            >>"%INSTALL_LOG%" echo Recommended model download failed; retry with Ollama later.
        ) else (
            echo !C_OK!Recommended model installed.!C_RESET!
            >>"%INSTALL_LOG%" echo Recommended model installed or already present.
        )
    )
) else (
    echo !C_DIM!Recommended Ollama model is already installed.!C_RESET!
)

call :show_step 7 "Optionale Sprachlaufzeit pruefen"
if exist "app_data\speech\crispasr\runtime\crispasr.exe" (
    echo !C_DIM!CrispASR is already installed.!C_RESET!
) else (
    choice /C YN /N /T 20 /D N /M "Install the AVX2-independent CrispASR CPU runtime now? [Y/N] "
    if errorlevel 2 (
        echo !C_DIM!CrispASR setup skipped. It remains available from Settings.!C_RESET!
    ) else (
        call install_crispasr_windows.bat legacy quiet >>"%INSTALL_LOG%" 2>&1
        if errorlevel 1 (
            echo !C_WARN!CrispASR could not be installed now. The core app remains usable; retry from Settings.!C_RESET!
        ) else (
            echo !C_OK!CrispASR runtime installed.!C_RESET!
        )
    )
)

call :show_step 8 "Optionale Wiki-Vorlage vorbereiten"
".venv\Scripts\python.exe" tools\prepare_tiddlywiki.py --target "app_data\cache\tiddlywiki_empty.html" >>"%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo !C_WARN!The optional TiddlyWiki template could not be prepared. The app remains usable; rerun this installer when online.!C_RESET!
) else (
    echo !C_OK!Blank TiddlyWiki template is cached and validated.!C_RESET!
)

>>"%INSTALL_LOG%" echo Installation completed %DATE% %TIME%.
echo.
echo !C_OK!  +-------------------------------------------------------------+!C_RESET!
echo !C_OK!    INSTALLATION ABGESCHLOSSEN   /   PRUEFUNGEN BESTANDEN!C_RESET!
echo !C_OK!  +-------------------------------------------------------------+!C_RESET!
echo !C_DIM!    Protokoll: %INSTALL_LOG%!C_RESET!
echo !C_WARN!The app starts automatically in 10 seconds. Press N to cancel.!C_RESET!
for /L %%S in (10,-1,1) do (
    <nul set /p "=!ESC![2K!ESC![1G!C_WARN!Autostart in %%S s (N=cancel)!C_RESET!"
    choice /C NS /N /T 1 /D S >nul
    if errorlevel 2 (
        rem Continue countdown.
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
exit /b 0

:show_step
set "STEP_BAR=................................"
if "%~1"=="1" set "STEP_BAR=####............................"
if "%~1"=="2" set "STEP_BAR=########........................"
if "%~1"=="3" set "STEP_BAR=############...................."
if "%~1"=="4" set "STEP_BAR=################................"
if "%~1"=="5" set "STEP_BAR=####################............"
if "%~1"=="6" set "STEP_BAR=########################........"
if "%~1"=="7" set "STEP_BAR=############################...."
if "%~1"=="8" set "STEP_BAR=################################"
echo !C_INFO!  [%~1/8] !C_OK![!STEP_BAR!]!C_RESET!  %~2
>>"%INSTALL_LOG%" echo [%~1/8] %~2
exit /b 0
