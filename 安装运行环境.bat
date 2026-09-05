@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
if errorlevel 1 (
  echo 安装失败。请检查以上错误。 / Setup failed. Check the error above.
  pause
  exit /b 1
)
echo 安装完成 / Setup complete
pause
