$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DefaultEnvPath = Join-Path $ProjectRoot ".conda-env"
$EnvPath = if ($env:FJSP_CONDA_ENV) { $env:FJSP_CONDA_ENV } else { $DefaultEnvPath }

Set-Location $ProjectRoot

Write-Host "Project root: $ProjectRoot"
Write-Host "Target Conda env: $EnvPath"

if (Test-Path $EnvPath) {
    Write-Host "Conda environment already exists: $EnvPath"
} else {
    Write-Host "Creating Conda environment..."
    conda env create -p $EnvPath -f environment.yml
}

Write-Host ""
Write-Host "Activate with:"
Write-Host "conda activate `"$EnvPath`""
Write-Host ""
Write-Host "Verify with:"
Write-Host "python -c `"import sys; print(sys.executable)`""
