@echo off
title TNVED Bot Manager
cd /d "%~dp0"

echo.
echo ========================================
echo         TNVED Bot Manager
echo ========================================
echo.

:menu
echo Choose an option:
echo   1. Restart Bot
echo   2. Stop Bot  
echo   3. Start Bot
echo   4. Check Status
echo   5. Monitor Bot (Auto-restart)
echo   6. View Recent Logs
echo   7. Exit
echo.

set /p choice="Enter your choice (1-7): "

if "%choice%"=="1" goto restart
if "%choice%"=="2" goto stop  
if "%choice%"=="3" goto start
if "%choice%"=="4" goto status
if "%choice%"=="5" goto monitor
if "%choice%"=="6" goto logs
if "%choice%"=="7" goto exit

echo Invalid choice. Please try again.
echo.
goto menu

:restart
echo.
echo Restarting TNVED Bot...
..\venv\Scripts\python.exe restart_bot.py restart
echo.
pause
goto menu

:stop
echo.
echo Stopping TNVED Bot...
..\venv\Scripts\python.exe restart_bot.py stop
echo.
pause
goto menu

:start
echo.
echo Starting TNVED Bot...
..\venv\Scripts\python.exe restart_bot.py start
echo.
pause
goto menu

:status
echo.
echo Checking bot status...
..\venv\Scripts\python.exe restart_bot.py status
echo.
pause
goto menu

:monitor
echo.
echo Starting bot monitoring (press Ctrl+C to stop)...
..\venv\Scripts\python.exe restart_bot.py monitor
echo.
pause
goto menu

:logs
echo.
echo Recent bot logs:
echo ==================
if exist bot.log (
    more bot.log
) else (
    echo No log file found.
)
echo.
pause
goto menu

:exit
echo.
echo Goodbye!
exit 