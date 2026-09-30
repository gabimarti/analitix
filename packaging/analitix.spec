# -*- mode: python ; coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Script: analitix.spec
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-29
# ---------------------------------------------------------------------------
# Receta de PyInstaller para el ejecutable de Windows. Uso: scripts\build_windows.bat
# (genera %TEMP%\analitix-dist\Analitix\, que luego empaqueta packaging\analitix.iss).
# Modo carpeta (onedir), no un único .exe autoextraíble: arranca más rápido y
# da menos falsos positivos de antivirus.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src" / "analitix"

a = Analysis(
    [str(ROOT / "packaging" / "analitix_launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        # Perfiles de parser, alias, fichas de descripción e iconos.
        (str(SRC / "data"), "analitix/data"),
        (str(SRC / "res"), "analitix/res"),
        *collect_data_files("ttkbootstrap"),
    ],
    # `gui` se importa en diferido y `alias_audit` carga los paneles con
    # importlib: se incluye el paquete entero para que no falte ninguno.
    hiddenimports=collect_submodules("analitix"),
    excludes=["pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Analitix",
    icon=str(ROOT / "build" / "analitix.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Analitix", upx=False)
