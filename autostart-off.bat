@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "app.py" --autostart off
) else (
  python "app.py" --autostart off
)
echo.
pause
