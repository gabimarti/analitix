:: ---------------------------------------------------------------------------
:: Script: build_windows.bat
:: Autor: Gabriel Marti
:: Contacto: https://github.com/gabimarti
:: Fecha de creación: 2026-09-29
:: ---------------------------------------------------------------------------
:: Genera el instalador de Windows dist\Analitix-Setup-<versión>.exe:
::   1. entorno aislado venv-build (no toca venv ni venv-tests),
::   2. ejecutable con PyInstaller (packaging\analitix.spec -> %TEMP%\analitix-dist\Analitix\),
::   3. instalador con Inno Setup 6 (packaging\analitix.iss).
:: Requiere Inno Setup 6: winget install JRSoftware.InnoSetup
:: Los temporales y el programa compilado van a %TEMP%, fuera del proyecto;
:: en dist solo queda el instalador final.
@echo off
setlocal
cd /d "%~dp0\.."

if not exist venv-build (
    echo Creando entorno de compilacion en .\venv-build ...
    python -m venv venv-build || exit /b 1
)
venv-build\Scripts\python.exe -m pip install -q --upgrade pip
venv-build\Scripts\python.exe -m pip install -q -r requirements.txt pyinstaller || exit /b 1

if not exist build mkdir build
venv-build\Scripts\python.exe -c "from PIL import Image; Image.open('src/analitix/res/analitix_icon.png').save('build/analitix.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])" || exit /b 1

venv-build\Scripts\python.exe -m PyInstaller packaging\analitix.spec --noconfirm --clean --distpath "%TEMP%\analitix-dist" --workpath "%TEMP%\analitix-pyinstaller" || exit /b 1

for /f %%v in ('venv-build\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import analitix; print(analitix.__version__)"') do set VERSION=%%v

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo No se encuentra Inno Setup 6. Instalalo con: winget install JRSoftware.InnoSetup
    exit /b 1
)
"%ISCC%" /Q /DAppVersion=%VERSION% "/DDistDir=%TEMP%\analitix-dist\Analitix" packaging\analitix.iss || exit /b 1

echo.
echo Instalador generado: dist\Analitix-Setup-%VERSION%.exe
endlocal
