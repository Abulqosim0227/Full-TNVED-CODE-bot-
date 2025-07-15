@echo off
echo ================================================
echo 🔥 TNVED BOT - PRODUCTION MODE
echo 💀 Ctrl+C will IMMEDIATELY kill the bot
echo 🚀 Perfect for server deployment
echo ================================================

REM Set production environment variables
set PRODUCTION_MODE=true
set IMMEDIATE_SHUTDOWN=true
set PYTHONUNBUFFERED=1
set PYTHONDONTWRITEBYTECODE=1

echo 🚀 Starting bot in production mode...
python bot.py

echo 🏁 Production bot stopped
pause 