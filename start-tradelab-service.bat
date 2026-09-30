@echo off
REM Headless / Task Scheduler entry — no browser, no pause.
REM Prefer install-windows-task.ps1 (watchdog every 5 min).
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

if not exist ".venv\Scripts\python.exe" (
  echo [HATA] .venv yok
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ensure-tradelab-running.ps1"
exit /b %ERRORLEVEL%
