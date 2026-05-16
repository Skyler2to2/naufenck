@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=python"
REM Force use system python because .venv is corrupted in this environment
echo [INFO] Using system python for stability.

if "%PORT%"=="" set "PORT=8501"
if "%HOST%"=="" set "HOST=0.0.0.0"

set "PYTHONUTF8=1"

echo [INFO] Starting YTMetrics using %PYTHON_CMD%...
"%PYTHON_CMD%" -m streamlit run YTMetrics.py --server.port %PORT% --server.address %HOST% --server.headless true --browser.gatherUsageStats false
