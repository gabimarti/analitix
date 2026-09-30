#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Script: run_linux.sh
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-09-07
# ---------------------------------------------------------------------------
set -e
cd "$(dirname "$0")/.."

if [ ! -d venv ]; then
    echo "No existe el entorno virtual. Ejecuta primero scripts/install_linux.sh"
    exit 1
fi

source venv/bin/activate
export PYTHONPATH="$(pwd)/src:$PYTHONPATH"
python -m analitix.main
