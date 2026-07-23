@echo off
setlocal
title Singh360 Draft - Live
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-live.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo Singh360 did not start. The exact error is shown above.
)
echo.
pause
exit /b %RC%
