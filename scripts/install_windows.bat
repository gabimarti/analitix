:: ---------------------------------------------------------------------------
:: Script: install_windows.bat
:: Autor: Gabriel Marti
:: Contacto: https://github.com/gabimarti
:: Fecha de creación: 2026-09-07
:: Última actualización: 2026-10-13
:: ---------------------------------------------------------------------------
@echo off
setlocal
cd /d "%~dp0\.."

where python >nul 2>nul
if errorlevel 1 (
    echo No se encuentra "python" en el PATH. Instala Python 3.14+ desde https://www.python.org/downloads/
    exit /b 1
)
python -c "import sys; sys.exit(sys.version_info < (3, 14))" >nul 2>nul
if errorlevel 1 (
    echo Analitix necesita Python 3.14 o superior y el "python" del PATH es otro:
    python --version
    echo Instalalo desde https://www.python.org/downloads/
    exit /b 1
)

if not exist venv (
    echo Creando entorno virtual en .\venv ...
    python -m venv venv
)

:: Sin activate.bat (guarda una ruta absoluta, ver run_windows.bat): siempre
:: el python del entorno. No se borra un entorno roto automaticamente: puede
:: ser el de otro equipo que comparte esta carpeta.
venv\Scripts\python.exe -c "pass" >nul 2>nul
if errorlevel 1 (
    echo El entorno virtual .\venv no funciona en este equipo: se creo con un
    echo Python que aqui no esta instalado. Borra la carpeta venv y vuelve a
    echo ejecutar este script.
    exit /b 1
)
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

echo.
echo Instalacion completada. Ejecuta scripts\run_windows.bat para iniciar Analitix.
endlocal
