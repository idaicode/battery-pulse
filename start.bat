@echo off
rem 启动桌面面板（无控制台窗口）。
rem 已经在运行就把面板叫到前台，不会出现第二份实例。
cd /d "%~dp0"

powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Method POST -Uri 'http://127.0.0.1:8731/api/show' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel%==0 (
  exit /b
)

if exist ".venv\Scripts\pythonw.exe" (
  start "" /B ".venv\Scripts\pythonw.exe" "app.py"
) else (
  start "" /B pythonw "app.py"
)
