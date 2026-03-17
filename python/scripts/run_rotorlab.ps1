$NoLaunch = $false
if ($args -contains "-NoLaunch") {
    $NoLaunch = $true
}

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonDir = Resolve-Path (Join-Path $scriptDir "..")
$repoRoot = Resolve-Path (Join-Path $pythonDir "..")
$pythonExe = Join-Path $pythonDir ".venv\Scripts\python.exe"
$backendScript = Join-Path $scriptDir "develop_rust_backend.ps1"

if (-not (Test-Path $pythonExe)) {
    throw "Expected app interpreter at $pythonExe"
}

if (-not (Test-Path $backendScript)) {
    throw "Expected backend installer script at $backendScript"
}

Push-Location $repoRoot
try {
    & $pythonExe -m pip install -e .\python
    if ($LASTEXITCODE -ne 0) {
        throw "Editable install for the Python app failed."
    }

    & $backendScript
    if ($LASTEXITCODE -ne 0) {
        throw "Rust backend installation failed."
    }

    & $pythonExe -c "import rotorlab_propeller_preview as m; assert hasattr(m, 'propeller_backend_contract'); assert hasattr(m, 'propeller_build_model')"
    if ($LASTEXITCODE -ne 0) {
        throw "Rust backend verification failed."
    }

    if (-not $NoLaunch) {
        & $pythonExe -m rotorlab_app.main
    }
}
finally {
    Pop-Location
}
