@echo off
setlocal
title Stop Singh360 Draft
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=8766; $pids=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; if ($pids) { $pids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; Write-Host 'Singh360 Draft stopped.' -ForegroundColor Green } else { Write-Host 'Singh360 Draft is not running.' -ForegroundColor Yellow }"
echo.
pause
