@echo off
setlocal
chcp 65001 >nul
title Singh360 Draft
cd /d "%~dp0"

set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Creating the Singh360 Draft Python environment...
  py -3 -m venv .venv || goto :failed
)

"%PYTHON%" -c "import flask, openpyxl, fitz" >nul 2>&1
if errorlevel 1 (
  echo Installing Python dependencies...
  "%PYTHON%" -m pip install -r requirements.txt || goto :failed
)

where npm.cmd >nul 2>&1 || (
  echo ERROR: Node.js/npm is required to build Singh360 Draft.
  goto :failed
)

pushd frontend
if not exist node_modules npm.cmd ci || (popd & goto :failed)
npm.cmd run build || (popd & goto :failed)
popd

if not exist ".docs\runtime_logs" mkdir ".docs\runtime_logs"
for /f %%P in ('powershell.exe -NoProfile -Command "(Get-Date).ToString('yyyyMMdd-HHmmss')"') do set "STAMP=%%P"
set "SINGH360_PORT=8766"
start "Singh360 Draft Server" /min cmd.exe /d /c ""%PYTHON%" server.py 1>>".docs\runtime_logs\singh360-draft-%STAMP%.log" 2>&1"

powershell.exe -NoProfile -Command "$deadline=(Get-Date).AddSeconds(45); do { Start-Sleep -Milliseconds 500; $ready=Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue } until ($ready -or (Get-Date) -gt $deadline); if (-not $ready) { exit 1 }; Start-Process 'http://127.0.0.1:8766/app'"
if errorlevel 1 goto :failed

echo Singh360 Draft is running at http://127.0.0.1:8766/app
exit /b 0

:failed
echo.
echo Singh360 Draft failed to start. Review the message above and the latest
echo file under .docs\runtime_logs.
pause
exit /b 1
