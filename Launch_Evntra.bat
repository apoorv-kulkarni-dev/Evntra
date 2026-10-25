@echo off
title Evntra Platform Launcher
cd /d "%~dp0"
python run_launcher.py
if %errorlevel% neq 0 (
    echo.
    echo If Python is not in your PATH, launching default browser...
    start http://localhost:5000/
    pause
)
exit
