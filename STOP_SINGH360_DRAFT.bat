@echo off
setlocal
title Stop Singh360 Draft
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-local.ps1"
exit /b %ERRORLEVEL%
