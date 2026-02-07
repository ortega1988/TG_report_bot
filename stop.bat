@echo off
echo Stopping services...

:: Stop Python bot
taskkill /f /im python.exe 2>nul

:: Stop Telegram Bot API
taskkill /fi "WINDOWTITLE eq Telegram Bot API" 2>nul
taskkill /f /im telegram-bot-api.exe 2>nul

echo Done.
