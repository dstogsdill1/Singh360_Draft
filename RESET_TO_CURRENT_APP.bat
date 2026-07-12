@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" ".\_repo_reset\reset_repo.py"
) else (
  python ".\_repo_reset\reset_repo.py"
)
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo Reset failed. The script attempted to restore its backup.
)
pause
exit /b %RC%
