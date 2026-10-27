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
Invoke-Check "Audit benchmark metadata" @("experiments\exp_012_benchmark_metadata_audit.py", "--output", (Join-Path $TempResults "metadata.csv"))
Invoke-Check "Build CP-SAT report" @("experiments\exp_013_cpsat_report.py", "--output", (Join-Path $TempResults "cpsat_report.md"))
Invoke-Check "Run Phase 2A dynamic smoke" @(
    "experiments\exp_014_dynamic_reschedule_smoke.py",
    "--output-dir",
    $TempResults
)
Invoke-Check "Audit Phase 2A dynamic event files" @(
    "experiments\exp_015_dynamic_event_file_check.py",
    "--output",
    (Join-Path $TempResults "exp_015_dynamic_event_file_check.csv")
)
Invoke-Check "Replay Phase 2A dynamic event files" @(
    "experiments\exp_016_dynamic_event_file_reschedule.py",
    "--output-dir",
    $TempResults
)
Invoke-Check "Build Phase 2A dynamic overview report" @(
    "experiments\exp_017_phase2a_dynamic_report.py",
    "--smoke-input",
    (Join-Path $TempResults "exp_014_dynamic_reschedule_smoke.csv"),
    "--audit-input",
    (Join-Path $TempResults "exp_015_dynamic_event_file_check.csv"),
    "--replay-input",
    (Join-Path $TempResults "exp_016_dynamic_event_file_reschedule.csv"),
    "--output",
    (Join-Path $TempResults "exp_017_phase2a_dynamic_report.md")
)
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
