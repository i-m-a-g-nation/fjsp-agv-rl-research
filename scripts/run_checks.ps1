$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnvPath = if ($env:FJSP_CONDA_ENV) { $env:FJSP_CONDA_ENV } else { Join-Path $ProjectRoot ".conda-env" }
$PythonExe = Join-Path $EnvPath "python.exe"
$Stamp = Get-Date -Format "yyyyMMddTHHmmss"
Set-Location $ProjectRoot

if (!(Test-Path $PythonExe)) {
    Write-Host "Python executable not found: $PythonExe"
    Write-Host "Run first: powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1"
    exit 1
}

function Invoke-Check([string]$Title, [string[]]$Arguments) {
    Write-Host ""
    Write-Host "==> $Title"
    & $PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Title failed with exit code $LASTEXITCODE" }
}

$env:PYTHONDONTWRITEBYTECODE = "1"
Invoke-Check "Dedicated Python" @("-c", "import sys; print(sys.executable)")
Invoke-Check "pytest with coverage" @("-m", "pytest", "--cov=fjsp_lab", "--cov-report=term-missing", "--cov-fail-under=80")
Invoke-Check "Phase 1 experiment" @("experiments\p1_static_fjsp.py", "--time-limit", "2", "--output-dir", "experiments\runs\check-p1-$Stamp")
Invoke-Check "Phase 2A protocol" @("experiments\p2_dynamic_protocol.py", "--output-dir", "experiments\runs\check-p2-$Stamp")

git diff --check
if ($LASTEXITCODE -ne 0) { throw "git diff --check failed" }
Write-Host ""
Write-Host "All checks passed."
