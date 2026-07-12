@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File ".\_finalize_tools\finalize_workspace.ps1"
if errorlevel 1 (
  echo.
  echo FINALIZE FAILED. Nothing in the archive folder was deleted.
  pause
  exit /b 1
)

set "ARCHIVE="
if exist ".finalizer_archive_path" set /p ARCHIVE=<".finalizer_archive_path"
if defined ARCHIVE (
  if exist ".\_finalize_tools" move /Y ".\_finalize_tools" "%ARCHIVE%\finalizer_tools" >nul
  del /Q ".finalizer_archive_path" >nul 2>&1
  echo Finalizer support files moved to %ARCHIVE%
  start "" cmd /c "timeout /t 2 /nobreak >nul & move /Y \"%~f0\" \"%ARCHIVE%\FINALIZE_WORKSPACE_AND_PUBLISH.bat\" >nul"
)
exit /b 0
