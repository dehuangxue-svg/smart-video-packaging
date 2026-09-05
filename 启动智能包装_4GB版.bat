@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1"
if errorlevel 1 (
  echo.
  echo 剪辑智能包装无法启动。
  echo Error log: %~dp0data\logs\server-error.log
  pause
  exit /b 1
)
exit /b 0
