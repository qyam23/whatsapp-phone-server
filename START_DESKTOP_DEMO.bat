@echo off
setlocal
cd /d "%~dp0"

set "VENV_PY=%CD%\.desktop_venv\Scripts\python.exe"
if exist "%VENV_PY%" goto configured

set "BASE_PY="
set "BASE_ARGS="
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  set "BASE_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)
if not defined BASE_PY (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "BASE_PY=py"
    set "BASE_ARGS=-3"
  )
)
if not defined BASE_PY (
  where python >nul 2>nul
  if not errorlevel 1 set "BASE_PY=python"
)
if not defined BASE_PY (
  echo Python 3 was not found. Install Python 3 and run this file again.
  pause
  exit /b 1
)

echo Creating the private desktop environment...
"%BASE_PY%" %BASE_ARGS% -m venv ".desktop_venv"
if errorlevel 1 goto failed

echo Installing the application requirements...
"%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed

:configured
if not exist ".env.desktop" (
  echo First-time desktop setup:
  "%VENV_PY%" scripts\setup_desktop.py
  if errorlevel 1 goto failed
)

"%VENV_PY%" scripts\run_desktop.py
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo Desktop simulation could not start. Review the message above.
pause
exit /b 1
