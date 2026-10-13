$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$venv = Join-Path $root "venv-tests"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    python -c "import sys; sys.exit(sys.version_info < (3, 14))"
    if ($LASTEXITCODE -ne 0) {
        throw "Analitix necesita Python 3.14 o superior y el 'python' del PATH es otro."
    }
    Write-Host "Creando el entorno virtual local venv-tests..."
    python -m venv $venv
}

# Un entorno creado con un Python que aqui no esta instalado (p. ej. si se
# copio la carpeta desde otro equipo) no arranca: mejor decirlo que fallar en pip.
& $python -c "pass"
if ($LASTEXITCODE -ne 0) {
    throw "venv-tests no funciona en este equipo (se creo con un Python que aqui no esta instalado). Borra la carpeta venv-tests y vuelve a ejecutar este script."
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
