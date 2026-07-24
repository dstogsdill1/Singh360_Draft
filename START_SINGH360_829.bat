@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "PORT=8766"
set "PROJECT_ID=b0904c99f2404524"
set "URL=http://127.0.0.1:%PORT%/app?project=%PROJECT_ID%&mode=editor"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "LOGDIR=%ROOT%.docs\startup_logs"
set "SERVER_OUT=%LOGDIR%\singh360-829-server.stdout.log"
set "SERVER_ERR=%LOGDIR%\singh360-829-server.stderr.log"
set "LAUNCH_LOG=%LOGDIR%\singh360-829-launch.log"

if not exist "%PYTHON%" (
  echo ERROR: Project Python was not found: "%PYTHON%"
  pause
  exit /b 10
)
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
echo [%DATE% %TIME%] Starting Singh360 829 verification.>>"%LAUNCH_LOG%"

rem Stop only a listener whose command line proves it belongs to this repo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $root=[IO.Path]::GetFullPath('%ROOT%');" ^
  "$listeners=@(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue);" ^
  "foreach($listener in $listeners){" ^
  "  $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$listener.OwningProcess);" ^
  "  $cmd=[string]$p.CommandLine;" ^
  "  if(-not ($cmd.Contains($root) -and $cmd -match '(?i)server\.py')){ throw ('Port %PORT% belongs to an unrelated process. Nothing was stopped. PID '+$listener.OwningProcess+' '+$cmd) };" ^
  "  Stop-Process -Id $listener.OwningProcess -Force;" ^
  "  Add-Content -LiteralPath '%LAUNCH_LOG%' ('Stopped prior verified repo listener PID '+$listener.OwningProcess);" ^
  "}; Start-Sleep -Milliseconds 500"
if errorlevel 1 (
  echo ERROR: Port %PORT% could not be safely prepared. See:
  echo   "%LAUNCH_LOG%"
  pause
  exit /b 20
)

set "SINGH360_PORT=%PORT%"
set "PYTHONUNBUFFERED=1"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$p=Start-Process -FilePath '%PYTHON%' -ArgumentList 'server.py' -WorkingDirectory '%ROOT%' -WindowStyle Hidden -RedirectStandardOutput '%SERVER_OUT%' -RedirectStandardError '%SERVER_ERR%' -PassThru;" ^
  "Add-Content -LiteralPath '%LAUNCH_LOG%' ('Started server PID '+$p.Id)"
if errorlevel 1 (
  echo ERROR: Singh360 server did not start. See:
  echo   "%SERVER_ERR%"
  pause
  exit /b 30
)

rem Wait for health, then verify the canonical project before opening the editor.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $base='http://127.0.0.1:%PORT%'; $deadline=(Get-Date).AddSeconds(120);" ^
  "do { try { $health=Invoke-RestMethod -Uri ($base+'/api/health') -TimeoutSec 5; if($health.ok){break} } catch {}; Start-Sleep -Milliseconds 500 } while((Get-Date) -lt $deadline);" ^
  "if(-not $health.ok){throw 'Health check did not become ready within 120 seconds.'};" ^
  "$project=Invoke-RestMethod -Uri ($base+'/api/projects/%PROJECT_ID%') -TimeoutSec 120;" ^
  "$published=@($project.pages | Where-Object { $_.include -ne $false });" ^
  "if($published.Count -ne 96){throw ('Expected 96 published pages; found '+$published.Count)};" ^
  "if($published[0].sheetCode -ne 'EMS 1.0' -or $published[1].sheetCode -ne 'EMS 2.0'){throw 'Cover / Sheet Index order verification failed.'};" ^
  "$source=@($published | Where-Object { $_.sheetCode -match '^(?i:SRC\b|TEMPLATE$)' }); if($source.Count){throw 'Source-only pages are still published.'};" ^
  "if($project.workbookSync.status -ne 'in_sync'){throw ('Workbook status is '+$project.workbookSync.status)};" ^
  "Add-Content -LiteralPath '%LAUNCH_LOG%' ('Verified health, workbook authority, and '+$published.Count+' published pages.');"
if errorlevel 1 (
  echo ERROR: Server started, but the 829 verification failed.
  echo   Launch log: "%LAUNCH_LOG%"
  echo   Server log: "%SERVER_ERR%"
  pause
  exit /b 40
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url='http://127.0.0.1:%PORT%/app?project=%PROJECT_ID%&mode=editor';" ^
  "Add-Content -LiteralPath '%LAUNCH_LOG%' ('Verified and opening '+$url);" ^
  "Start-Process $url;" ^
  "Write-Host 'Singh360 829 is ready.'; Write-Host $url"
exit /b 0
