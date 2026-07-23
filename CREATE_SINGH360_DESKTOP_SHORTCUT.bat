@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0"
set "TARGET=%ROOT%START_SINGH360_LOCAL.bat"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Singh360 Draft - Local.lnk'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%ROOT%'; $s.IconLocation='%SystemRoot%\System32\SHELL32.dll,14'; $s.Save()"
if errorlevel 1 (
  echo Shortcut creation failed.
  pause
  exit /b 1
)
echo Desktop shortcut created: Singh360 Draft - Local
pause
