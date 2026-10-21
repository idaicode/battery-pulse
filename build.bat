@echo off
rem 打包成独立程序（dist\BatteryPulse\ 目录，双击 BatteryPulse.exe 运行）
rem 产物不依赖本机 Python，可整个目录拷到别的 Windows 10/11 上用。
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 创建虚拟环境...
  python -m venv .venv || goto :fail
)

echo [2/3] 安装依赖...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt pyinstaller || goto :fail

echo [3/3] 打包...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean battery-monitor.spec || goto :fail

echo.
echo 完成：dist\BatteryPulse\BatteryPulse.exe
echo 可以把 dist\BatteryPulse 整个目录移到任意位置，双击 exe 即可。
pause
exit /b 0

:fail
echo.
echo 打包失败，看上面的报错。
pause
exit /b 1
