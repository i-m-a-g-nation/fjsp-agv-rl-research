$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DefaultEnvPath = Join-Path $ProjectRoot ".conda-env"
$EnvPath = if ($env:FJSP_CONDA_ENV) { $env:FJSP_CONDA_ENV } else { $DefaultEnvPath }
$PythonExe = Join-Path $EnvPath "python.exe"

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
}

Write-Host "Project root: $ProjectRoot"
Write-Host "Python executable: $PythonExe"

Invoke-Check "Audit benchmark metadata" @("experiments\exp_012_benchmark_metadata_audit.py")
Invoke-Check "Build CP-SAT report" @("experiments\exp_013_cpsat_report.py")
Invoke-Check "Run Phase 2A dynamic smoke" @("experiments\exp_014_dynamic_reschedule_smoke.py")
Invoke-Check "Audit Phase 2A dynamic event files" @("experiments\exp_015_dynamic_event_file_check.py")
Invoke-Check "Replay Phase 2A dynamic event files" @("experiments\exp_016_dynamic_event_file_reschedule.py")
Invoke-Check "Build Phase 2A dynamic overview report" @("experiments\exp_017_phase2a_dynamic_report.py")
Invoke-Check "Run pytest with core coverage" @(
    "-m",
    "pytest",
    "--cov=src",
    "--cov-report=term-missing",
    "--cov-fail-under=80"
)

Write-Host ""
Write-Host "All local checks completed successfully."
