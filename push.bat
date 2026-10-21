@echo off
rem One-click commit + push for daily edits.
rem   push.bat                     -> auto message with timestamp
rem   push.bat "fix: xxx"          -> custom message
setlocal
cd /d "%~dp0"

set "MSG=%~1"
if "%MSG%"=="" set "MSG=chore: auto commit %DATE% %TIME%"

git add -A
git diff --cached --quiet
if %errorlevel%==0 (
  echo [i] Nothing to commit. Working tree clean.
  exit /b 0
)

echo [1/2] committing...
git commit -m "%MSG%" || goto fail

echo [2/2] pushing to origin...
git push || goto fail

echo.
echo Done. Changes are on GitHub.
exit /b 0

:fail
echo.
echo Failed. Read the message above.
exit /b 1
