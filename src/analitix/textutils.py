# ---------------------------------------------------------------------------
# Script: textutils.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-09-07
# ---------------------------------------------------------------------------
"""Utilidades de normalización de texto compartidas."""
from __future__ import annotations

import re
import unicodedata


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def normalize_name(raw_name: str) -> str:
    """Normaliza 'Apellidos, Nombre' o 'Nombre Apellidos' a una forma comparable."""
    name = raw_name.strip()
    if "," in name:
        apellidos, nombre = name.split(",", 1)
        name = f"{nombre.strip()} {apellidos.strip()}"
    # Algunas plantillas separan el segundo nombre con un guion en vez de un
    # espacio ("MARIA-JOSE" frente a "MARIA JOSE"); se normaliza a espacio
    # para que ambas formas emparejen con el mismo paciente.
    name = name.replace("-", " ")
    name = re.sub(r"\s+", " ", name)
    return strip_accents(name).upper().strip()


def unit_key(unit: str | None) -> str:
    """Unidad en forma comparable: minúsculas, sin espacios ni "_", "µ" ->
    "mc", superíndices a dígitos y "x10N"/"·10N" -> "x10^N". Así "x10³/mm³"
    (Synlab), "·10³/µl" (Quirón) y "x10^3_u/mcL" (Maresme) empiezan todos
    por "x10^3", y "µg/dL" queda como "mcg/dl"."""
    u = (unit or "").strip().lower().replace(" ", "").replace("_", "")
    u = u.replace("µ", "mc").replace("μ", "mc").replace("³", "3").replace("⁶", "6").replace("·", "x")
    return re.sub(r"^x10\^?", "x10^", u)


def is_count_1e9_l(unit: str | None) -> bool:
    """Recuento celular en 10⁹/L: x10³/µL, x10³/mm³ y x10⁹/L son la misma
    magnitud (1 µL = 1 mm³ = 10⁻⁶ L)."""
    u = unit_key(unit)
    return u.startswith("x10^3") or u.startswith("x10^9/l")


def is_count_1e12_l(unit: str | None) -> bool:
    """Recuento de hematíes en 10¹²/L: x10⁶/µL, x10⁶/mm³ y x10¹²/L son la
    misma magnitud."""
    u = unit_key(unit)
    return u.startswith("x10^6") or u.startswith("x10^12/l")


def normalize_test_name(raw_name: str) -> str:
    """Normaliza el nombre de una determinación analítica para emparejar alias."""
    name = strip_accents(raw_name).lower()
    name = re.sub(r"[^a-z0-9]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()
