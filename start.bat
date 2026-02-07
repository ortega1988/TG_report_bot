@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"

:: Load .env file
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    set "line=%%a"
    if not "!line:~0,1!"=="#" if not "!line!"=="" set "%%a=%%b"
)

echo.
echo ========================================
echo   Bug Report Bot Launcher
echo ========================================
echo.

:: Check if local Telegram API is enabled
if /i not "%TELEGRAM_LOCAL%"=="true" (
    echo [INFO] Using standard Telegram Bot API
    goto :startbot
)

echo [1/3] Checking Telegram Bot API Server...

if not exist "telegram-bot-api\telegram-bot-api.exe" (
    echo.
    echo ERROR: telegram-bot-api.exe not found!
    echo Please download from https://github.com/aiogram/telegram-bot-api/releases
    pause
    exit /b 1
)

if "%TELEGRAM_API_ID%"=="" (
    echo ERROR: TELEGRAM_API_ID is not set in .env
    pause
    exit /b 1
)

if "%TELEGRAM_API_HASH%"=="" (
    echo ERROR: TELEGRAM_API_HASH is not set in .env
    pause
    exit /b 1
)

:: Create data directory
if not exist "data\telegram-files" mkdir "data\telegram-files"

:: Kill any existing process
tasklist /fi "imagename eq telegram-bot-api.exe" 2>nul | find /i "telegram-bot-api.exe" >nul
if %errorlevel%==0 (
    echo Stopping existing telegram-bot-api.exe...
    taskkill /f /im telegram-bot-api.exe >nul 2>&1
    timeout /t 2 /nobreak >nul
)

echo [2/3] Starting Telegram Bot API Server...

:: Start in separate window
start "Telegram Bot API" "telegram-bot-api\telegram-bot-api.exe" --api-id=%TELEGRAM_API_ID% --api-hash=%TELEGRAM_API_HASH% --local --dir=data\telegram-files

:: Wait for port 8081
echo Waiting for API server on port 8081...
set attempts=0

:waitloop
set /a attempts+=1
if %attempts% gtr 15 (
    echo.
    echo ERROR: Telegram Bot API failed to start!
    echo Check the Telegram Bot API window for errors.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
netstat -an 2>nul | find ":8081" | find "LISTENING" >nul
if errorlevel 1 (
    echo   Attempt %attempts%/15...
    goto :waitloop
)

echo [OK] Telegram Bot API started on port 8081

:startbot
echo.
echo [3/3] Starting Bug Report Bot...
echo ========================================
echo.

python bot.py

echo.
echo Bot stopped.

:: Stop API server if it was started
if /i "%TELEGRAM_LOCAL%"=="true" (
    echo Stopping Telegram Bot API Server...
    taskkill /f /im telegram-bot-api.exe >nul 2>&1
)

pause
