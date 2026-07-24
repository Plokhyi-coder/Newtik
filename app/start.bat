@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   Newtik - setup and launch
echo ============================================
echo.

cd /d "%~dp0"

REM --- Step 1: make sure ffmpeg is reachable for THIS process ---
where ffmpeg >nul 2>nul
if %errorlevel%==0 (
    echo [OK] ffmpeg found in PATH.
) else (
    echo [..] ffmpeg not found in PATH, looking for a WinGet install...
    set "FFMPEG_EXE="
    for /f "delims=" %%F in ('where /r "%LOCALAPPDATA%\Microsoft\WinGet\Packages" ffmpeg.exe 2^>nul') do (
        set "FFMPEG_EXE=%%F"
    )

    if defined FFMPEG_EXE (
        for %%D in ("!FFMPEG_EXE!") do set "FFMPEG_BIN=%%~dpD"
        echo [OK] Found ffmpeg at: !FFMPEG_BIN!
        set "PATH=%PATH%;!FFMPEG_BIN!"
    ) else (
        echo [..] ffmpeg not installed yet. Installing via winget, this downloads ~250 MB...
        winget install --id=Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
        echo.
        echo [..] Locating the freshly installed ffmpeg...
        set "FFMPEG_EXE="
        for /f "delims=" %%F in ('where /r "%LOCALAPPDATA%\Microsoft\WinGet\Packages" ffmpeg.exe 2^>nul') do (
            set "FFMPEG_EXE=%%F"
        )
        if defined FFMPEG_EXE (
            for %%D in ("!FFMPEG_EXE!") do set "FFMPEG_BIN=%%~dpD"
            set "PATH=%PATH%;!FFMPEG_BIN!"
            echo [OK] ffmpeg ready for this session at: !FFMPEG_BIN!
        ) else (
            echo [FAIL] Could not find ffmpeg.exe after installing.
            echo        Try rebooting your PC once, then run this script again.
            pause
            exit /b 1
        )
    )
)

ffmpeg -version >nul 2>nul
if not %errorlevel%==0 (
    echo [FAIL] ffmpeg still does not run. Reboot your PC once and try again.
    pause
    exit /b 1
)

REM --- Step 2: make sure Python is available ---
where python >nul 2>nul
if not %errorlevel%==0 (
    echo [FAIL] Python not found.
    echo        Install Python 3.11+ from python.org - check "Add python.exe to PATH"
    echo        during setup - then run this script again.
    pause
    exit /b 1
)
echo [OK] Python found.

REM --- Step 3: create the virtual environment once ---
if not exist "venv\Scripts\activate.bat" (
    echo [..] Creating virtual environment ^(first run only^)...
    python -m venv venv
)

call venv\Scripts\activate.bat

REM --- Step 4: install/update dependencies, but only if requirements.txt
REM     actually changed since last time - this is what made every launch
REM     take minutes: pip re-checking every package even with nothing to do.
set "REQ_HASH_FILE=venv\.requirements_hash.txt"
set "NEW_HASH="
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile requirements.txt SHA256 2^>nul') do (
    if not defined NEW_HASH set "NEW_HASH=%%H"
)

set "OLD_HASH="
if exist "%REQ_HASH_FILE%" set /p OLD_HASH=<"%REQ_HASH_FILE%"

set "SKIP_INSTALL=0"
if defined NEW_HASH if "!NEW_HASH!"=="!OLD_HASH!" set "SKIP_INSTALL=1"

if "!SKIP_INSTALL!"=="1" (
    echo [OK] Dependencies already up to date, skipping install.
) else (
    echo [..] Installing dependencies - first run can take a few minutes...
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt
    if not %errorlevel%==0 (
        echo [FAIL] pip install failed, see the errors above.
        pause
        exit /b 1
    )
    if defined NEW_HASH echo !NEW_HASH!>"%REQ_HASH_FILE%"
)

REM --- Step 5: launch the app ---
echo.
echo [OK] Everything is ready. Launching Newtik...
echo.
python main.py

echo.
echo Newtik closed.
pause
