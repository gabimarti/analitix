$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$venv = Join-Path $root "venv-tests"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Creando el entorno virtual local venv-tests..."
    python -m venv $venv
}

Write-Host "Actualizando dependencias de pruebas..."
& $python -m pip install -r requirements.txt -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) {
    throw "No se pudieron instalar las dependencias."
}

Write-Host "Ejecutando la suite..."
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "La suite de pruebas ha fallado."
}

Write-Host ""
Write-Host "Suite completada correctamente." -ForegroundColor Green
