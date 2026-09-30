:: ---------------------------------------------------------------------------
:: Script: alias_audit.bat
:: Autor: Gabriel Marti
:: Contacto: https://github.com/gabimarti
:: Fecha de creación: 2026-09-25
:: ---------------------------------------------------------------------------
:: Auditoria de alias de pruebas (analitix.alias_audit): analiza los PDF de
:: informes_analiticas\ y deja el informe y el CSV de propuestas en export\.
:: Se puede lanzar desde cualquier carpeta; admite los mismos argumentos que
:: el modulo (p. ej. otra carpeta de PDF o --out).
@echo off
setlocal
cd /d "%~dp0\.."

if not exist venv (
    echo No existe el entorno virtual. Ejecuta primero scripts\install_windows.bat
    exit /b 1
)

set PYTHONPATH=%cd%\src;%PYTHONPATH%
venv\Scripts\python.exe -m analitix.alias_audit %*
endlocal
