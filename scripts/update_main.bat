@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_main.ps1"
set "exit_code=%errorlevel%"
echo.
if not "%exit_code%"=="0" (
    echo No se ha actualizado la carpeta principal.
) else (
    echo Proceso terminado correctamente.
)
pause
endlocal & exit /b %exit_code%
