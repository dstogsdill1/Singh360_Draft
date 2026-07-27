@echo off
setlocal
chcp 65001 >nul
title Singh360 Draft
cd /d "%~dp0"

set "SINGH360_PORT=8766"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "& '%~dp0scripts\singh360_launcher.ps1' -Action Start -Port 8766"
if errorlevel 1 goto :failed

exit /b 0

:failed
echo.
echo Singh360 Draft failed to start. Review the message above and the latest
echo file under .docs\runtime_logs.
if not defined SINGH360_LAUNCHER_NO_PAUSE pause
exit /b 1
