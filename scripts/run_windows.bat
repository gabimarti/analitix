:: ---------------------------------------------------------------------------
:: Script: run_windows.bat
:: Autor: Gabriel Marti
:: Contacto: https://github.com/gabimarti
:: Fecha de creación: 2026-09-07
:: Última actualización: 2026-09-22
:: ---------------------------------------------------------------------------
@echo off
setlocal
cd /d "%~dp0\.."

if not exist venv (
    echo No existe el entorno virtual. Ejecuta primero scripts\install_windows.bat
    exit /b 1
)

call venv\Scripts\activate.bat
set PYTHONPATH=%cd%\src;%PYTHONPATH%
:: pythonw (sin consola) + start (lanza sin esperar): la ventana de CMD se
:: cierra sola nada mas arrancar Analitix, en vez de quedarse abierta toda
:: la sesion. Los errores siguen registrados en data\analitix.log
:: (`main.configure_logging`, ver el diagnostico de problemas del manual de
:: usuario), asi que no hace falta la consola para depurar un fallo.
start "" pythonw -m analitix.main
endlocal
