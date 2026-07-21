@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "APP_VERSION=v2.0"
title OllamaVibeDesk %APP_VERSION% Installer

cd /d "%~dp0"

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

echo !C_INFO!============================================!C_RESET!
echo !C_INFO!  OllamaVibeDesk %APP_VERSION% - Windows Installer!C_RESET!
echo !C_INFO!============================================!C_RESET!
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo !C_ERR!Python launcher "py" was not found.!C_RESET!
    echo !C_WARN!Please install Python 3.10+ and enable the Python Launcher.!C_RESET!
    >>"%INSTALL_LOG%" echo ERROR: Python launcher not found.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo !C_INFO![1/5] Creating local virtual environment...!C_RESET!
    >>"%INSTALL_LOG%" echo STEP 1: Creating venv.
    py -3 -m venv .venv >>"%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo !C_ERR!Failed to create the virtual environment.!C_RESET!
        pause
        exit /b 1
    )
) else (
    echo !C_DIM![1/5] Local virtual environment already exists.!C_RESET!
)

echo !C_INFO![2/5] Preparing pip and build tools...!C_RESET!
>>"%INSTALL_LOG%" echo STEP 2: Updating pip/setuptools/wheel.
call ".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel >>"%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo !C_ERR!Failed to prepare pip.!C_RESET!
    pause
    exit /b 1
)

if not exist "wheelhouse" mkdir "wheelhouse"
set "INSTALLED_OFFLINE=0"
for %%W in (wheelhouse\*.whl) do (
    if exist "%%W" set "WHEELS_AVAILABLE=1"
)
if defined WHEELS_AVAILABLE (
    echo !C_INFO![3/5] Trying offline dependency installation from wheelhouse...!C_RESET!
    >>"%INSTALL_LOG%" echo STEP 3: Trying offline wheelhouse install.
    call ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse -r requirements.txt >>"%INSTALL_LOG%" 2>&1
    if not errorlevel 1 set "INSTALLED_OFFLINE=1"
)
if "!INSTALLED_OFFLINE!"=="0" (
    echo !C_INFO![3/5] Installing dependencies and refreshing wheelhouse...!C_RESET!
    >>"%INSTALL_LOG%" echo STEP 3: Online dependency install.
    call ".venv\Scripts\python.exe" -m pip install -r requirements.txt >>"%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo !C_ERR!Failed to install Python packages.!C_RESET!
        echo !C_WARN!See %INSTALL_LOG% for details.!C_RESET!
        pause
        exit /b 1
    )
    call ".venv\Scripts\python.exe" -m pip download -r requirements.txt -d wheelhouse >>"%INSTALL_LOG%" 2>&1
    if errorlevel 1 echo !C_WARN!Dependencies are installed, but the offline wheelhouse could not be refreshed.!C_RESET!
) else (
    echo !C_OK!Dependencies installed from the local wheelhouse.!C_RESET!
)

echo !C_INFO![4/5] Preparing portable application directories...!C_RESET!
for %%D in (
    "app_data"
    "app_data\audio"
    "app_data\cache"
    "app_data\chats"
    "app_data\config_profiles"
    "app_data\debug_logs"
    "app_data\exports"
    "app_data\generated_code"
    "app_data\knowledge_base"
    "app_data\logs"
    "app_data\tts"
    "app_data\auto_answer\phrases"
    "app_data\auto_answer\topic_words"
    "app_data\auto_answer\question_replies"
    "app_data\auto_answer\eliza"
) do if not exist "%%~D" mkdir "%%~D"

if not exist "app_data\cache\tiddlywiki_empty.html" (
    echo !C_INFO![5/5] Caching a blank TiddlyWiki template for offline reuse...!C_RESET!
    >>"%INSTALL_LOG%" echo STEP 5: Downloading TiddlyWiki empty template.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'https://tiddlywiki.com/empty.html' -OutFile 'app_data\cache\tiddlywiki_empty.html' -UseBasicParsing; exit 0 } catch { exit 1 }" >>"%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo !C_WARN!The blank TiddlyWiki template could not be downloaded right now.!C_RESET!
        echo !C_WARN!The app remains usable and will create a small fallback brain.html.!C_RESET!
    ) else (
        echo !C_OK!Blank TiddlyWiki template cached successfully.!C_RESET!
    )
) else (
    echo !C_DIM![5/5] Blank TiddlyWiki template is already cached.!C_RESET!
)

>>"%INSTALL_LOG%" echo Installation completed %DATE% %TIME%.
echo.
echo !C_OK!Installation complete. Log: %INSTALL_LOG%!C_RESET!
echo !C_WARN!The app starts automatically in 10 seconds. Press N to cancel.!C_RESET!
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
