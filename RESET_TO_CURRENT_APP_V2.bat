@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" ".\_repo_reset_v2\reset_repo_v2.py"
) else (
  python ".\_repo_reset_v2\reset_repo_v2.py"
)
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo V2 reset failed. The script attempted to restore its backup.
)
pause
exit /b %RC%
