@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
  where py >nul 2>nul && set "PYTHON_CMD=py -3.13"
)

if not defined PYTHON_CMD (
  echo [ERROR] Python was not found. Install Python 3.13 x64 and enable Add Python to PATH.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Creating virtual environment...
  call %PYTHON_CMD% -m venv .venv
  if errorlevel 1 exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1

if exist "vendor\wheels\*.whl" (
  echo [INFO] Installing from bundled wheels...
  python -m pip install --no-index --find-links="%cd%\vendor\wheels" -r requirements-customer.txt
) else (
  echo [WARN] Wheel bundle not found, falling back to online install...
  python -m pip install -r requirements-customer.txt
)
if errorlevel 1 exit /b 1

echo [OK] Dependency installation finished.
echo [INFO] If browser fallback is needed, the app will try to use local Chrome or Chromium automatically.
echo [NEXT] Run start_ytmetrics.bat to launch the app.
exit /b 0
