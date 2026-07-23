@echo off
setlocal
title Stop Singh360 Draft
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=8766; Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; Get-Process -Name ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; Write-Host 'Singh360 server and ngrok stopped.' -ForegroundColor Green"
echo.
pause
