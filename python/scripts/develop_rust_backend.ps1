$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonDir = Resolve-Path (Join-Path $scriptDir "..")
$pythonExe = Join-Path $pythonDir ".venv\Scripts\python.exe"
$manifestPath = Resolve-Path (Join-Path $pythonDir "..\rust\rotorlab_propeller_preview\Cargo.toml")
$wheelDir = Join-Path $pythonDir ".wheelhouse"

if (-not (Test-Path $pythonExe)) {
    throw "Expected virtualenv interpreter at $pythonExe"
}

if (Test-Path $wheelDir) {
    Get-ChildItem -Path $wheelDir -Filter "rotorlab_propeller_preview-*.whl" -ErrorAction SilentlyContinue |
        Remove-Item -Force
} else {
    New-Item -ItemType Directory -Path $wheelDir | Out-Null
}

& $pythonExe -m maturin build --manifest-path $manifestPath --out $wheelDir
if ($LASTEXITCODE -ne 0) {
    throw "maturin build failed."
}

$wheel = Get-ChildItem -Path $wheelDir -Filter "rotorlab_propeller_preview-*.whl" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($null -eq $wheel) {
    throw "Could not find the built rotorlab_propeller_preview wheel."
}

& $pythonExe -m pip install --force-reinstall $wheel.FullName
if ($LASTEXITCODE -ne 0) {
    throw "pip install --force-reinstall failed."
}

Write-Host "Rust backend wheel installed into the local python/.venv environment."
