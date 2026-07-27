@echo off
cd /d "%~dp0..\.."

for /f %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)"') do (
  taskkill /PID %%P /F >nul 2>&1
)

start "" pythonw app\server.py
