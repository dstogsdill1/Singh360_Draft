@echo off
setlocal
title Stop Singh360 Draft
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=8766; $repo=(Get-Location).Path; $python=Join-Path $repo '.venv\Scripts\python.exe'; $pidFile=Join-Path $repo '.docs\runtime\singh360-draft.pid'; if(-not (Test-Path $pidFile)){Write-Host 'Singh360 Draft is not running (no Singh360 PID file).' -ForegroundColor Yellow; exit 0}; $serverPidText=(Get-Content $pidFile -Raw).Trim(); if($serverPidText -notmatch '^\d+$'){Write-Host 'ERROR: Singh360 PID file is invalid; no process was stopped.' -ForegroundColor Red; exit 1}; $serverPid=[int]$serverPidText; $proc=Get-CimInstance Win32_Process -Filter ('ProcessId='+$serverPid) -ErrorAction SilentlyContinue; $listener=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Where-Object OwningProcess -eq $serverPid | Select-Object -First 1; $isOurs=$proc -and $listener -and ($proc.CommandLine -match [regex]::Escape($python)) -and ($proc.CommandLine -match '(^|[ /\\])server\.py(\s|$)'); if(-not $isOurs){Write-Host ('ERROR: Recorded PID '+$serverPid+' is not the Singh360 Draft listener on port 8766; no process was stopped.') -ForegroundColor Red; exit 1}; Stop-Process -Id $serverPid -Force -ErrorAction Stop; $deadline=(Get-Date).AddSeconds(10); do{Start-Sleep -Milliseconds 200; $alive=Get-Process -Id $serverPid -ErrorAction SilentlyContinue}until(-not $alive -or (Get-Date) -gt $deadline); if($alive){Write-Host ('ERROR: Singh360 Draft PID '+$serverPid+' did not stop.') -ForegroundColor Red; exit 1}; Remove-Item $pidFile -Force; Write-Host ('Singh360 Draft PID '+$serverPid+' stopped.') -ForegroundColor Green"
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
echo.
pause
