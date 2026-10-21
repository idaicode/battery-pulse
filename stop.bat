@echo off
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Method POST -Uri 'http://127.0.0.1:8731/api/shutdown' | Out-Null; Write-Host 'Battery Pulse stopped.' } catch { Write-Host 'Battery Pulse is not running.' }"
