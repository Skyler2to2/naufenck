param()

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Get-PythonCommand {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py -3.13"
    }
    throw "Python was not found. Install Python 3.13 x64 and enable Add Python to PATH."
}

$pythonCmd = Get-PythonCommand

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[INFO] Creating virtual environment..."
    Invoke-Expression "$pythonCmd -m venv .venv"
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (Test-Path "vendor\wheels") {
    Write-Host "[INFO] Installing from bundled wheels..."
    & $venvPython -m pip install --no-index --find-links (Join-Path $PSScriptRoot "vendor\wheels") -r requirements-customer.txt
} else {
    Write-Host "[WARN] Wheel bundle not found, falling back to online install..."
    & $venvPython -m pip install -r requirements-customer.txt
}

Write-Host "[OK] Dependency installation finished."
Write-Host "[INFO] If browser fallback is needed, the app will try to use local Chrome or Chromium automatically."
