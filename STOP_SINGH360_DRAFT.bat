@echo off
setlocal
title Stop Singh360 Draft
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "& '%~dp0scripts\singh360_launcher.ps1' -Action Stop -Port 8766"
if errorlevel 1 (
  echo.
  if not defined SINGH360_LAUNCHER_NO_PAUSE pause
  exit /b 1
)
exit /b 0
