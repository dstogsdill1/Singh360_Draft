@echo off
setlocal
title Starting Singh360 Draft
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-live.ps1"
if errorlevel 1 (
  echo.
  echo Singh360 did not start. The exact error is shown above.
  pause
)
