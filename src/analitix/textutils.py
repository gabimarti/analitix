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


def split_full_name(full_name: str | None) -> tuple[str, str] | None:
    """`(nombre, apellidos)` de un nombre guardado como "Apellidos, Nombre";
    `None` si no lleva coma (no se sabe qué parte es el nombre)."""
    if not full_name or "," not in full_name:
        return None
    apellidos, nombre = full_name.split(",", 1)
    return nombre.strip(), apellidos.strip()


def join_full_name(nombre: str, apellidos: str) -> str:
    """Forma guardada del nombre, "Apellidos, Nombre" (la coma separa las
    dos partes; `normalize_name` la entiende). Sin una de las dos partes,
    solo la otra, sin coma."""
    nombre, apellidos = nombre.strip(), apellidos.strip()
    return f"{apellidos}, {nombre}" if nombre and apellidos else nombre or apellidos


def name_splits(full_name: str) -> list[tuple[str, str]]:
    """Posibles `(nombre, apellidos)` de un nombre sin coma, para que el
    usuario elija: primero las de "NOMBRE APELLIDOS" (lo habitual sin coma)
    y después las de "APELLIDOS NOMBRE"."""
    words = full_name.split()
    cuts = range(1, len(words))
    return [(" ".join(words[:i]), " ".join(words[i:])) for i in cuts] + [
        (" ".join(words[i:]), " ".join(words[:i])) for i in reversed(cuts)
    ]


def name_words_key(raw_name: str) -> str:
    """Las palabras de `normalize_name` ordenadas: igual para "GARCIA LOPEZ
    JUAN" y "JUAN GARCIA LOPEZ" (mismo nombre en otro orden, sin coma).
    Solo sirve junto con la fecha de nacimiento (`find_patient`)."""
    return " ".join(sorted(normalize_name(raw_name).split()))


def unit_key(unit: str | None) -> str:
    """Unidad en forma comparable: minúsculas, sin espacios ni "_", "µ" ->
    "mc", superíndices a dígitos y "x10N"/"·10N" -> "x10^N". Así "x10³/mm³"
    (Synlab), "·10³/µl" (Quirón) y "x10^3_u/mcL" (Maresme) empiezan todos
    por "x10^3", y "µg/dL" queda como "mcg/dl"."""
    u = (unit or "").strip().lower().replace(" ", "").replace("_", "")
    u = (
        u.replace("µ", "mc")
        .replace("μ", "mc")
        .replace("³", "3")
        .replace("⁶", "6")
        .replace("·", "x")
    )
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
