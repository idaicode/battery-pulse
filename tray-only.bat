@echo off
rem 只起托盘，不创建桌面窗口（最省内存的模式）。
rem 适合开机自启：托盘右键 -> 打开面板 时才真正需要窗口。
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
  start "" /B ".venv\Scripts\pythonw.exe" "app.py" --tray
) else (
  start "" /B pythonw "app.py" --tray
)
