@echo off
setlocal
cd /d "%~dp0"

set "VENV_PY=%CD%\.desktop_venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo Run START_DESKTOP_DEMO.bat once before changing the settings.
  pause
  exit /b 1
)

"%VENV_PY%" scripts\setup_desktop.py --force
if errorlevel 1 (
  echo.
  echo Settings were not changed.
  pause
  exit /b 1
)

echo.
echo AI settings saved. Restart the desktop simulation to apply them.
pause
