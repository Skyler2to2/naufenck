param(
    [string]$PackageName = "YTMetrics_client_package",
    [switch]$SkipPythonDeps
)

$ErrorActionPreference = "Stop"

$sourceRoot = $PSScriptRoot
$outputRoot = Join-Path $sourceRoot "delivery-output"
$stageRoot = Join-Path $outputRoot $PackageName
$wheelDir = Join-Path $stageRoot "vendor\wheels"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$zipPath = Join-Path $outputRoot ($PackageName + "_" + $timestamp + ".zip")

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
if (Test-Path $stageRoot) {
    Remove-Item -Recurse -Force $stageRoot
}
New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null

$excludeDirs = @(
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".code-review-graph",
    ".tmp-html-anything",
    "delivery-output",
    "vendor"
)

$excludeFiles = @(
    "*.pyc",
    "*.pyo",
    "*.log",
    ".ytmetrics_runtime.json",
    "dynamic_scrape.json",
    "scraped_comments.json",
    "客户部署说明.md",
    "YTMetrics_问题解决手册.docx"
)

$robocopyArgs = @(
    $sourceRoot,
    $stageRoot,
    "/E",
    "/R:2",
    "/W:1",
    "/NFL",
    "/NDL",
    "/NJH",
    "/NJS",
    "/NP"
)

if ($excludeDirs.Count -gt 0) {
    $robocopyArgs += "/XD"
    $robocopyArgs += ($excludeDirs | ForEach-Object { Join-Path $sourceRoot $_ })
}

if ($excludeFiles.Count -gt 0) {
    $robocopyArgs += "/XF"
    $robocopyArgs += $excludeFiles
}

Write-Host "[1/4] Copying source files into staging folder..."
& robocopy @robocopyArgs | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "robocopy failed with exit code: $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null

if (-not $SkipPythonDeps) {
    Write-Host "[2/4] Downloading offline Python dependencies..."
    New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null
    python -m pip download -r (Join-Path $sourceRoot "requirements-customer.txt") -d $wheelDir
} else {
    Write-Host "[2/4] Skipping bundled Python dependencies by request."
    if (Test-Path (Join-Path $stageRoot "vendor")) {
        Remove-Item -Recurse -Force (Join-Path $stageRoot "vendor")
    }
}

Write-Host "[3/4] Skipping bundled Chromium browser by request."

Write-Host "[4/4] Creating final zip archive..."
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
Compress-Archive -Path $stageRoot -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "[OK] Package created:"
Write-Host $zipPath
