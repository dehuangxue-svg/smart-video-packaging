@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\download_models.ps1"
if errorlevel 1 echo 下载失败，请检查网络后重试
pause
