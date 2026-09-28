@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title TradeLABtr Stock Screener
chcp 65001 >nul

echo.
echo === TradeLABtr Stock Screener ===
echo Klasor: %CD%
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [HATA] .venv yok. Once sunucuda sunlari calistirin:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo   copy .env.example .env
  echo.
  pause
  exit /b 1
)

if not exist ".env" (
  echo [.env yok] .env.example kopyalaniyor...
  copy /y ".env.example" ".env" >nul
)

REM VPS: disaridan erisim. .env icinde HOST varsa o gecerli (python load_dotenv override etmez).
if not defined HOST set HOST=0.0.0.0
if not defined PORT set PORT=8000
set PYTHONUNBUFFERED=1

echo Python: .venv\Scripts\python.exe
echo Adres : http://%HOST%:%PORT%
echo Log   : storage\server.log
echo Pencereyi kapatirsaniz tarama durur.
echo.

".venv\Scripts\python.exe" -u run.py
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
  echo [HATA] Sunucu cikis kodu %ERR%
  echo Ayrinti icin storage\server.log dosyasina bakin.
)
pause
exit /b %ERR%
