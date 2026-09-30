$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ((git rev-parse --is-inside-work-tree) -ne "true") {
    throw "La carpeta no es un repositorio Git: $root"
}

$trackedChanges = git status --porcelain --untracked-files=no
if ($trackedChanges) {
    Write-Host "Hay cambios versionados sin guardar. No se ejecuta el pull para evitar sobrescribirlos:" -ForegroundColor Yellow
    Write-Host $trackedChanges
    exit 1
}

$branch = (git branch --show-current).Trim()
if ($branch -ne "main") {
    Write-Host "Cambiando de la rama '$branch' a 'main'..."
    git switch main
}

Write-Host "Consultando origin/main..."
git fetch origin main
Write-Host "Actualizando la carpeta principal..."
git pull --ff-only origin main

Write-Host ""
Write-Host "Actualizacion completada. Los archivos locales ignorados no se modifican." -ForegroundColor Green
git status --short --branch
