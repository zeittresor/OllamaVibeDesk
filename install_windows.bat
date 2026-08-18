@echo off
setlocal EnableExtensions EnableDelayedExpansion
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

echo !C_INFO!=================================================!C_RESET!
echo !C_INFO!  OllamaVibeDesk %APP_VERSION% - Windows Installer!C_RESET!
echo !C_INFO!=================================================!C_RESET!
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

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >>"%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo !C_ERR!Python 3.10 or newer is required.!C_RESET!
    >>"%INSTALL_LOG%" echo ERROR: Python version is too old.
    pause
    exit /b 1
)

echo !C_INFO![1/7] Validating the release files...!C_RESET!
%PYTHON_CMD% tools\verify_installation.py --source-only >>"%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo !C_ERR!The release package is incomplete or damaged.!C_RESET!
    echo !C_WARN!See %INSTALL_LOG% for details.!C_RESET!
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo !C_INFO![2/7] Creating the project-local virtual environment...!C_RESET!
    %PYTHON_CMD% -m venv .venv >>"%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo !C_ERR!Failed to create the virtual environment.!C_RESET!
        pause
        exit /b 1
    )
) else (
    echo !C_DIM![2/7] Reusing the existing local virtual environment.!C_RESET!
)

echo !C_INFO![3/7] Installing application dependencies...!C_RESET!
set "INSTALLED_OFFLINE=0"
if exist "wheelhouse\*.whl" (
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
    echo !C_OK!Dependencies installed from the offline wheelhouse.!C_RESET!
)

echo !C_INFO![4/7] Preparing portable application directories...!C_RESET!
for %%D in (
    "app_data" "app_data\audio" "app_data\cache" "app_data\chats"
    "app_data\config_profiles" "app_data\debug_logs" "app_data\exports"
    "app_data\generated_code" "app_data\knowledge_base" "app_data\logs"
    "app_data\tts" "app_data\auto_answer\phrases" "app_data\auto_answer\topic_words"
    "app_data\auto_answer\question_replies" "app_data\auto_answer\eliza"
    "app_data\personalities" "app_data\personalities\user" "app_data\personalities\assistant"
    "app_data\speech" "app_data\speech\crispasr"
) do if not exist "%%~D" mkdir "%%~D"

echo !C_INFO![5/7] Verifying installed packages and GUI startup...!C_RESET!
".venv\Scripts\python.exe" -m pip check >>"%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo !C_ERR!Installed package dependencies are inconsistent.!C_RESET!
    echo !C_WARN!See %INSTALL_LOG% for details.!C_RESET!
    pause
    exit /b 1
)
set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" tools\verify_installation.py >>"%INSTALL_LOG%" 2>&1
set "QT_QPA_PLATFORM="
if errorlevel 1 (
    echo !C_ERR!Installation verification failed; the app will not be started.!C_RESET!
    echo !C_WARN!See %INSTALL_LOG% for details.!C_RESET!
    pause
    exit /b 1
)

echo !C_INFO![6/7] Optional VibeVoice ASR/GGUF-TTS runtime...!C_RESET!
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

echo !C_INFO![7/7] Preparing the optional local wiki template...!C_RESET!
if not exist "app_data\cache\tiddlywiki_empty.html" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'https://tiddlywiki.com/empty.html' -OutFile 'app_data\cache\tiddlywiki_empty.html' -UseBasicParsing; exit 0 } catch { exit 1 }" >>"%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo !C_WARN!The optional TiddlyWiki template could not be downloaded. The app remains usable.!C_RESET!
    ) else (
        echo !C_OK!Blank TiddlyWiki template cached successfully.!C_RESET!
    )
) else (
    echo !C_DIM!The local TiddlyWiki template is already cached.!C_RESET!
)

>>"%INSTALL_LOG%" echo Installation completed %DATE% %TIME%.
echo.
echo !C_OK!Installation and verification completed. Log: %INSTALL_LOG%!C_RESET!
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
