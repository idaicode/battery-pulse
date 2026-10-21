@echo off
rem 写 HKCU\...\Run，开机用 pythonw --tray 静默拉起，不闪黑框
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "app.py" --autostart on
) else (
  python "app.py" --autostart on
)
echo.
pause
