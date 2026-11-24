:: ---------------------------------------------------------------------------
:: Script: run_windows.bat
:: Autor: Gabriel Marti
:: Contacto: https://github.com/gabimarti
:: Fecha de creación: 2026-09-07
:: Última actualización: 2026-10-13
:: ---------------------------------------------------------------------------
@echo off
setlocal
cd /d "%~dp0\.."

if not exist venv\Scripts\pythonw.exe (
    echo No existe el entorno virtual. Ejecuta primero scripts\install_windows.bat
    pause
    exit /b 1
)

:: Sin activate.bat: guarda la ruta absoluta de la carpeta donde se creo el
:: entorno, y si la carpeta del proyecto se mueve (o se usa desde otro
:: equipo) acabaria lanzando el python del sistema, sin las dependencias.
venv\Scripts\python.exe -c "import sqlcipher3, ttkbootstrap" >nul 2>nul
if errorlevel 1 (
    echo El entorno virtual .\venv no funciona en este equipo: se creo con un
    echo Python que aqui no esta instalado o le faltan dependencias.
    echo Borra la carpeta venv y ejecuta scripts\install_windows.bat
    pause
    exit /b 1
)

set PYTHONPATH=%cd%\src;%PYTHONPATH%
:: pythonw (sin consola) + start (lanza sin esperar): la ventana de CMD se
:: cierra sola nada mas arrancar Analitix, en vez de quedarse abierta toda
:: la sesion. Los errores siguen registrados en data\analitix.log
:: (`main.configure_logging`, ver el diagnostico de problemas del manual de
:: usuario), asi que no hace falta la consola para depurar un fallo.
start "" venv\Scripts\pythonw.exe -m analitix.main
endlocal
