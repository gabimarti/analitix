#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Script: install_linux.sh
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-09-07
# ---------------------------------------------------------------------------
# Instalación en Linux. El entorno principal soportado es Windows; esto se
# ofrece de forma best-effort.
set -e
cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null; then
    echo "No se encuentra python3. Instálalo con el gestor de paquetes de tu distribución."
    exit 1
fi

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo "Falta el módulo tkinter. En Debian/Ubuntu: sudo apt install python3-tk"
    exit 1
fi

if [ ! -d venv ]; then
    echo "Creando entorno virtual en ./venv ..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
if ! pip install -r requirements.txt; then
    echo
    echo "Si el fallo es por 'sqlcipher3' (cifrado de la base de datos), instala"
    echo "las cabeceras de SQLCipher antes de reintentar, p.ej. en Debian/Ubuntu:"
    echo "  sudo apt install libsqlcipher-dev"
    exit 1
fi

echo
echo "Instalación completada. Ejecuta scripts/run_linux.sh para iniciar Analitix."
