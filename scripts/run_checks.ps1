param([switch]$Heavy)
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DefaultEnvPath = Join-Path $ProjectRoot ".conda-env"
$EnvPath = if ($env:FJSP_CONDA_ENV) { $env:FJSP_CONDA_ENV } else { $DefaultEnvPath }
$PythonExe = Join-Path $EnvPath "python.exe"
$TempResults = Join-Path ([System.IO.Path]::GetTempPath()) ("fjsp-check-results-" + [System.Guid]::NewGuid().ToString("N"))

Set-Location $ProjectRoot

if (!(Test-Path $PythonExe)) {
    Write-Host "Python executable not found: $PythonExe"
    Write-Host "Please run first:"
    Write-Host "powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1"
    exit 1
}

function Invoke-Check {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host ""
    Write-Host "==> $Title"
    & $PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Title failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Project root: $ProjectRoot"
Write-Host "Python executable: $PythonExe"
Write-Host "Temporary result directory: $TempResults"

Invoke-Check "Verify dedicated Python" @("-c", "import sys; print(sys.executable)")
$ExperimentArguments = @("scripts\check_experiments.py", "--output-dir", $TempResults)
if ($Heavy) { $ExperimentArguments += "--heavy" }
Invoke-Check "Run shared local/CI experiment checks" $ExperimentArguments
Invoke-Check "Run pytest with core coverage" @(
    "-m",
    "pytest",
    "--cov=src",
    "--cov-report=term-missing",
    "--cov-fail-under=80"
)

Write-Host ""
Write-Host "==> Check diff whitespace"
git diff --check
if ($LASTEXITCODE -ne 0) { throw "git diff --check failed with exit code $LASTEXITCODE" }

Write-Host ""
Write-Host "All local checks completed successfully."
