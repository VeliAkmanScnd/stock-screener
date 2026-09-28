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

REM VPS tarayicidan erisim icin her zaman tum arayuzlere baglan.
REM .env icinde HOST=127.0.0.1 kalsa bile bu pencere disari acar.
set HOST=0.0.0.0
if not defined PORT set PORT=8000
set PYTHONUNBUFFERED=1

echo Python: .venv\Scripts\python.exe
echo Bind  : %HOST%:%PORT%
echo Log   : storage\server.log
echo.

echo Eski surec varsa durduruluyor (git pull sonrasi yeni kod icin)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\free-listen-port.ps1" %PORT%
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

echo.
echo Tarayiciyi acin:
echo   Bu VPS:     http://127.0.0.1:%PORT%/login
echo   (localhost YAZMAYIN — Windows IPv6'ya gidip sayfayi acmayabilir)
echo   Baska PC:   http://SUNUCU_IPv4:%PORT%/login
echo   http kullanin, https degil. Portu atlamayin.
echo.
echo Windows Firewall ^(Yonetici CMD^):
echo   netsh advfirewall firewall add rule name="TradeLABtr" dir=in action=allow protocol=TCP localport=%PORT%
echo.
echo Pencereyi kapatirsaniz tarama durur.
echo.

REM Sunucu ayaga kalkinca dogru adresi ac (localhost degil).
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:%PORT%/login"

".venv\Scripts\python.exe" -u run.py
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
  echo [HATA] Sunucu cikis kodu %ERR%
  echo Ayrinti icin storage\server.log dosyasina bakin.
  echo Port doluysa bu pencereyi kapatip start-tradelab.bat'i tekrar calistirin.
)
pause
exit /b %ERR%
