param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Dependencies are not installed yet. Run install_offline.ps1 or install_offline.bat first."
}

$env:PYTHONUTF8 = "1"

& $venvPython -m streamlit run YTMetrics.py --server.port $Port --server.address $HostAddress --server.headless true --browser.gatherUsageStats false
