"""Comprobación de privacidad de los ficheros versionados (CI: privacy.yml).

Falla (código de salida 1) si el repositorio contiene:

1. Ficheros con extensión de datos reales (PDF de informes, bases de datos,
   hojas de cálculo, CSV, logs), salvo los de `PERMITIDOS`.
2. Un DNI/NIE con letra de control válida en cualquier fichero de texto.
   Los datos sintéticos de tests/docs deben usar el número 00000000
   (p. ej. "00000000T") o una letra de control inválida ("00000000A"),
   que esta comprobación ignora a propósito.

Uso: python scripts/check_privacy.py   (desde la raíz del repositorio)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

EXTENSIONES_PROHIBIDAS = {
    ".pdf", ".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm",
    ".xlsx", ".xls", ".xlsm", ".ods", ".csv", ".log",
}
# Datos de catálogo que sí forman parte del código (sin datos de pacientes)
# y el informe PDF de ejemplo del manual, generado por
# `scripts/doc_screenshots.py` con el paciente ficticio (nunca datos reales).
PERMITIDOS = {
    "src/analitix/data/test_aliases.csv", "src/analitix/data/biological_variation.csv",
    "docs/ejemplos/informe_alterados_ficticio.pdf",
}

LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
_DNI_RE = re.compile(r"\b([XYZ]?)(\d{7,8})([A-Z])\b")


def dni_valido(prefijo: str, numero: str, letra: str) -> bool:
    """True si es un DNI/NIE con letra de control correcta y no es el
    número sintético 00000000."""
    if prefijo:
        if len(numero) != 7:
            return False
        numero = str("XYZ".index(prefijo)) + numero
    elif len(numero) != 8:
        return False
    if int(numero) == 0:
        return False
    return LETRAS_DNI[int(numero) % 23] == letra


def revisar(rutas: list[str], raiz: Path) -> list[str]:
    problemas = []
    for ruta in rutas:
        if Path(ruta).suffix.lower() in EXTENSIONES_PROHIBIDAS and ruta not in PERMITIDOS:
            problemas.append(f"{ruta}: tipo de fichero no permitido en el repositorio")
            continue
        try:
            texto = (raiz / ruta).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binario (imágenes, iconos...) o no legible
        for n, linea in enumerate(texto.splitlines(), 1):
            for m in _DNI_RE.finditer(linea):
                if dni_valido(*m.groups()):
                    # No se imprime el número completo: el log de CI es público.
                    problemas.append(f"{ruta}:{n}: posible DNI/NIE real")
    return problemas


def main() -> int:
    rutas = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout.split("\0")
    problemas = revisar([r for r in rutas if r], Path.cwd())
    for p in problemas:
        print(p)
    if problemas:
        print(f"\n{len(problemas)} problema(s) de privacidad. Ver CONTRIBUTING.md.")
        return 1
    print("Sin problemas de privacidad.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
