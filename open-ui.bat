@echo off
rem 把已在运行的桌面面板叫到前台；没在运行就先拉起来。
cd /d "%~dp0"

powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Method POST -Uri 'http://127.0.0.1:8731/api/show' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel%==0 (
  exit /b
)
call "%~dp0start.bat"
