@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" ".\_repo_reset_v3\reset_repo_v3.py"
) else (
  python ".\_repo_reset_v3\reset_repo_v3.py"
)

set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo V3 reset failed. The script attempted to restore its backup.
  pause
  exit /b %RC%
)

if exist ".reset_v3_success" (
  set "ARCHIVE="
  if exist ".reset_v3_archive_path" set /p ARCHIVE=<".reset_v3_archive_path"
  if defined ARCHIVE (
    if exist ".\_repo_reset_v3" move /Y ".\_repo_reset_v3" "%ARCHIVE%\repo_reset_v3_tools" >nul
    del /Q ".reset_v3_success" ".reset_v3_archive_path" >nul 2>&1
    echo V3 support files moved to %ARCHIVE%
    start "" cmd /c "timeout /t 2 /nobreak >nul & move /Y \"%~f0\" \"%ARCHIVE%\RESET_TO_CURRENT_APP_V3.bat\" >nul"
  )
)

echo.
echo Finished.
pause
exit /b 0
