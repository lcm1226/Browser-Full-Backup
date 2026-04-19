[CmdletBinding()]
param(
    [string]$PythonPath,
    [switch]$NoLaunch,
    [switch]$SkipInstall,
    [switch]$ForceReinstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvRoot = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$requirementsPath = Join-Path $projectRoot "requirements.txt"
$mainScript = Join-Path $projectRoot "main.py"

function Write-Step {
    param([string]$Message)
    Write-Host "[Chromium Backup Tool] $Message" -ForegroundColor Cyan
}

function Find-WindowsPython {
    $candidates = New-Object System.Collections.Generic.List[string]

    if ($PythonPath) {
        if (-not (Test-Path -LiteralPath $PythonPath)) {
            throw "The Python path you provided does not exist: $PythonPath"
        }
        $candidates.Add((Resolve-Path $PythonPath).Path)
    }

    foreach ($commandName in @("py", "python")) {
        try {
            $command = Get-Command $commandName -ErrorAction Stop
            if ($command.Source) {
                $candidates.Add($command.Source)
            }
        } catch {
        }
    }

    $commonRoots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        "C:\Python312",
        "C:\Python311",
        "C:\Program Files\Python312",
        "C:\Program Files\Python311"
    )

    foreach ($root in $commonRoots) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }

        Get-ChildItem -LiteralPath $root -Recurse -Filter python.exe -ErrorAction SilentlyContinue |
            ForEach-Object {
                $candidates.Add($_.FullName)
            }
    }

    $uniqueCandidates = $candidates | Select-Object -Unique
    foreach ($candidate in $uniqueCandidates) {
        try {
            $versionOutput = & $candidate --version 2>&1
            if ($LASTEXITCODE -eq 0 -or $versionOutput -match "^Python\s+\d") {
                return $candidate
            }
        } catch {
        }
    }

    throw @"
Could not find a Windows Python installation.

Recommended next steps:
1. Install Python 3.11 or newer for Windows
2. Enable 'Add python.exe to PATH' during install
3. Or run this script with -PythonPath 'C:\full\path\to\python.exe'
"@
}

function Ensure-Venv {
    $pythonExe = Find-WindowsPython

    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Step "Creating the .venv virtual environment."
        & $pythonExe -m venv $venvRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create the virtual environment."
        }
    } else {
        Write-Step "Using the existing .venv virtual environment."
    }

    if ($ForceReinstall) {
        Write-Step "Reinstalling dependencies."
        & $venvPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to upgrade pip."
        }
        & $venvPython -m pip install --upgrade --force-reinstall -r $requirementsPath
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to reinstall dependencies."
        }
        return
    }

    if ($SkipInstall) {
        Write-Step "Skipping dependency installation."
        return
    }

    Write-Step "Installing required Python packages."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }
    & $venvPython -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install dependencies."
    }
}

if (-not (Test-Path -LiteralPath $mainScript)) {
    throw "main.py was not found. Make sure you are running this script from the project folder."
}

Write-Step "Preparing the Windows Python environment."
Ensure-Venv

if ($NoLaunch) {
    Write-Step "Environment setup is complete. Skipping app launch."
    return
}

$launcher = if (Test-Path -LiteralPath (Join-Path $venvRoot "Scripts\\pythonw.exe")) {
    Join-Path $venvRoot "Scripts\\pythonw.exe"
} else {
    $venvPython
}

Write-Step "Launching the application."
Start-Process -FilePath $launcher -ArgumentList @($mainScript) -WorkingDirectory $projectRoot
