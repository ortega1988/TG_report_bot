@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Testing telegram-bot-api.exe...
echo.

if not exist "telegram-bot-api\telegram-bot-api.exe" (
    echo ERROR: telegram-bot-api.exe not found!
    pause
    exit /b 1
)

echo Running: telegram-bot-api.exe --help
echo ========================================
"telegram-bot-api\telegram-bot-api.exe" --help
echo.
echo ========================================
echo Exit code: %errorlevel%
echo.
pause
