@echo off
setlocal
chcp 65001 >nul
title Singh360 Draft

echo.
echo =====================================================================
echo  SINGH360 DRAFT - SAVE + WRITE EXCEL V26
echo  Start Project Home, work locally, then push to Excel from the header
echo =====================================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-v26.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo START FAILED. Review the exact message above.
) else (
  echo SINGH360 DRAFT V26 IS READY.
)
echo.
pause
exit /b %RC%
