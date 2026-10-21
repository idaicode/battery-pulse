@echo off
rem Build a GitHub-Release-ready zip:
rem   release\BatteryPulse-v<version>-win64.zip
rem Requires build.bat to have created .venv at least once.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [!] .venv not found. Run build.bat first.
  exit /b 1
)

rem Version comes from core\__init__.py only - single source of truth.
"%PY%" -c "from core import __version__; print(__version__)" > "%TEMP%\bp_ver.txt"
set /p VERSION=<"%TEMP%\bp_ver.txt"
del /q "%TEMP%\bp_ver.txt" 2>nul
if not defined VERSION (
  echo [!] Cannot read __version__ from core\__init__.py
  exit /b 1
)
echo [1/4] version %VERSION%

echo [2/4] building exe...
"%PY%" -m PyInstaller --noconfirm --clean battery-monitor.spec || goto fail

echo [3/4] compressing...
if not exist "release" mkdir release
set "ZIP=release\BatteryPulse-v%VERSION%-win64.zip"
if exist "%ZIP%" del /q "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\BatteryPulse\*' -DestinationPath '%ZIP%' -CompressionLevel Optimal" || goto fail

echo [4/4] done
for %%f in ("%ZIP%") do echo     %%~ff  %%~zf bytes
echo.
echo Upload: GitHub repo -^> Releases -^> Draft a new release -^> tag v%VERSION% -^> attach the zip above.
exit /b 0

:fail
echo.
echo Build failed. See the error above.
exit /b 1
