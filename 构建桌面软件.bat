@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0desktop\build.ps1"
if errorlevel 1 (
  echo 构建失败 / Build failed
  pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_shortcut.ps1"
if errorlevel 1 (
  echo 无法创建快捷方式，请直接打开 exe。 / Open the exe directly.
)
pause
