[CmdletBinding()]
param(
    [string]$PythonPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript = Join-Path $projectRoot "run_windows.ps1"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$mainScript = Join-Path $projectRoot "main.py"

if (-not (Test-Path -LiteralPath $runScript)) {
    throw "run_windows.ps1를 찾지 못했습니다."
}

Write-Host "[Chromium Backup Tool] Preparing the runtime environment." -ForegroundColor Cyan
if ($PythonPath) {
    powershell -ExecutionPolicy Bypass -File $runScript -PythonPath $PythonPath -NoLaunch
} else {
    powershell -ExecutionPolicy Bypass -File $runScript -NoLaunch
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "The .venv Python executable was not found."
}

Write-Host "[Chromium Backup Tool] Installing PyInstaller." -ForegroundColor Cyan
& $venvPython -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install PyInstaller."
}

Write-Host "[Chromium Backup Tool] Building the exe package." -ForegroundColor Cyan
& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name ChromiumProfileBackupTool `
    $mainScript

if ($LASTEXITCODE -ne 0) {
    throw "Failed to build the exe package."
}

Write-Host "[Chromium Backup Tool] Done: dist\ChromiumProfileBackupTool.exe" -ForegroundColor Green
