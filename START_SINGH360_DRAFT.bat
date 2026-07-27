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
if not exist node_modules call npm.cmd ci || (popd & goto :failed)
call npm.cmd run build || (popd & goto :failed)
popd

if not exist ".docs\runtime_logs" mkdir ".docs\runtime_logs"
if not exist ".docs\runtime" mkdir ".docs\runtime"
for /f %%P in ('powershell.exe -NoProfile -Command "(Get-Date).ToString('yyyyMMdd-HHmmss')"') do set "STAMP=%%P"
set "SINGH360_PORT=8766"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=8766; $repo=(Get-Location).Path; $python=(Resolve-Path '.venv\Scripts\python.exe').Path; $pidFile=Join-Path $repo '.docs\runtime\singh360-draft.pid'; $listener=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($listener) { $recorded=if(Test-Path $pidFile){(Get-Content $pidFile -Raw).Trim()}else{''}; $proc=Get-CimInstance Win32_Process -Filter ('ProcessId='+$listener.OwningProcess) -ErrorAction SilentlyContinue; $isOurs=($recorded -eq [string]$listener.OwningProcess) -and $proc -and ($proc.CommandLine -match [regex]::Escape($python)) -and ($proc.CommandLine -match '(^|[ /\\])server\.py(\s|$)'); if(-not $isOurs){Write-Host ('ERROR: Port 8766 is already owned by PID '+$listener.OwningProcess+', not the recorded Singh360 Draft server.') -ForegroundColor Red; exit 1}; Start-Process 'http://127.0.0.1:8766/app'; Write-Host ('Singh360 Draft already running as PID '+$listener.OwningProcess+'.') -ForegroundColor Green; exit 0}; if(Test-Path $pidFile){Remove-Item $pidFile -Force}; $stdout=Join-Path $repo '.docs\runtime_logs\singh360-draft-%STAMP%.out.log'; $stderr=Join-Path $repo '.docs\runtime_logs\singh360-draft-%STAMP%.err.log'; $env:SINGH360_PORT='8766'; $proc=Start-Process -FilePath $python -ArgumentList 'server.py' -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru; $deadline=(Get-Date).AddSeconds(45); do { Start-Sleep -Milliseconds 500; $ready=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 } until ($ready -or $proc.HasExited -or (Get-Date) -gt $deadline); $listenerProc=if($ready){Get-CimInstance Win32_Process -Filter ('ProcessId='+$ready.OwningProcess) -ErrorAction SilentlyContinue}else{$null}; $isOurs=$listenerProc -and ($listenerProc.ParentProcessId -eq $proc.Id) -and ($listenerProc.CommandLine -match [regex]::Escape($python)) -and ($listenerProc.CommandLine -match '(^|[ /\\])server\.py(\s|$)'); if(-not $isOurs){if($ready){Stop-Process -Id $ready.OwningProcess -Force -ErrorAction SilentlyContinue}; if(-not $proc.HasExited){Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue}; exit 1}; Set-Content -Path $pidFile -Value $ready.OwningProcess -NoNewline; Start-Process 'http://127.0.0.1:8766/app'"
if errorlevel 1 goto :failed

echo Singh360 Draft is running at http://127.0.0.1:8766/app
exit /b 0

:failed
echo.
echo Singh360 Draft failed to start. Review the message above and the latest
echo file under .docs\runtime_logs.
pause
exit /b 1
