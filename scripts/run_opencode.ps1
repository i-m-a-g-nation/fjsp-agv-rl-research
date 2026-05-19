$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DefaultEnvPath = Join-Path $ProjectRoot ".conda-env"
$EnvPath = if ($env:FJSP_CONDA_ENV) { $env:FJSP_CONDA_ENV } else { $DefaultEnvPath }

Set-Location $ProjectRoot

if (!(Test-Path $EnvPath)) {
    Write-Host "Conda env not found: $EnvPath"
    Write-Host "Please run first:"
    Write-Host "powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1"
    exit 1
}

conda activate $EnvPath

Write-Host "Python executable:"
python -c "import sys; print(sys.executable)"

Write-Host ""
Write-Host "Starting OpenCode..."
opencode
