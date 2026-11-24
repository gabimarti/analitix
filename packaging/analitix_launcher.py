# ---------------------------------------------------------------------------
# Script: analitix_launcher.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-29
# ---------------------------------------------------------------------------
"""Punto de entrada del ejecutable de Windows (PyInstaller, ver analitix.spec)."""

import multiprocessing

# Los PDF se leen en un proceso hijo (`analitix.pdf_worker`, modo «spawn»):
# en el ejecutable, ese hijo es el propio Analitix.exe relanzado, y sin esta
# llamada (antes de cualquier otra cosa) abriría otra ventana de la
# aplicación en vez de ponerse a leer el PDF.
multiprocessing.freeze_support()

from analitix.main import main  # noqa: E402

main()
