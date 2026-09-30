:: ---------------------------------------------------------------------------
:: Script: install_windows.bat
:: Autor: Gabriel Marti
:: Contacto: https://github.com/gabimarti
:: Fecha de creación: 2026-09-07
:: Última actualización: 2026-09-07
:: ---------------------------------------------------------------------------
@echo off
setlocal
cd /d "%~dp0\.."

where python >nul 2>nul
if errorlevel 1 (
    echo No se encuentra "python" en el PATH. Instala Python 3.11+ desde https://www.python.org/downloads/
    exit /b 1
)

if not exist venv (
    echo Creando entorno virtual en .\venv ...
    python -m venv venv
)

call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Instalacion completada. Ejecuta scripts\run_windows.bat para iniciar Analitix.
endlocal
