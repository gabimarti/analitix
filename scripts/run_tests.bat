@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_tests.ps1"
set "exit_code=%errorlevel%"
echo.
if not "%exit_code%"=="0" (
    echo La suite de pruebas ha fallado.
) else (
    echo Suite completada correctamente.
)
pause
endlocal & exit /b %exit_code%
