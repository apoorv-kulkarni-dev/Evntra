@echo off
title Evntra Public Internet Tunnel
cd /d "%~dp0"

echo ===================================================
echo        EVNTRA — LIVE WORLDWIDE ACCESS
echo ===================================================
echo.
python run_launcher.py --server-only

echo.
echo Generating your secure public HTTPS link...
echo Anyone in the world can open this link on mobile or PC.
echo.
npx localtunnel --port 5000
pause
