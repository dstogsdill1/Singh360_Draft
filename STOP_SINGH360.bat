@echo off
setlocal
title Stop Singh360 Draft
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root='%~dp0'; $runtime=Join-Path $root '.docs\runtime'; foreach($name in @('singh360-server.pid','singh360-ngrok.pid')) { $file=Join-Path $runtime $name; if(Test-Path $file) { $raw=Get-Content $file | Select-Object -First 1; $id=0; if([int]::TryParse([string]$raw,[ref]$id)) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }; Remove-Item $file -Force -ErrorAction SilentlyContinue } }; Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; Write-Host 'Singh360 stopped.' -ForegroundColor Green"
pause
