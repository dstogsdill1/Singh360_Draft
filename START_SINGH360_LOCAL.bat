@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Singh360 Draft - Start Local
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local.ps1"
if errorlevel 1 (
  echo.
  echo START FAILED. Review the newest log in .docs\runtime.
  pause
  exit /b 1
)
