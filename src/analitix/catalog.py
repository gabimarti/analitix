# ---------------------------------------------------------------------------
# Script: catalog.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-09-09
# ---------------------------------------------------------------------------
"""Catálogo de pruebas: asigna un identificador canónico estable a cada
determinación analítica, para poder seguir su evolución aunque el nombre
exacto varíe ligeramente entre plantillas del laboratorio.

Por defecto el identificador se deriva del propio nombre normalizado (p.ej.
"Colesterol sèrum" -> "colesterol_serum"), que ya es estable entre plantillas
en la inmensa mayoría de los casos observados. El fichero CSV de alias solo
hace falta para fusionar manualmente dos nombres distintos que en realidad
son la misma prueba (por ejemplo si el laboratorio la renombra en el futuro).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from analitix.config import BUNDLED_CATALOG_PATH, CATALOG_PATH, DESCRIPTIONS_DIR
from analitix.textutils import normalize_test_name

_overrides: Optional[dict[str, str]] = None


def _read_aliases(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["alias_normalizado"]: row["canonical_id"] for row in reader if row.get("alias_normalizado")}


def _load_overrides() -> dict[str, str]:
    """Alias de la aplicación más los del usuario (ver `config.CATALOG_PATH`);
    los del usuario ganan si coinciden."""
    overrides = _read_aliases(BUNDLED_CATALOG_PATH)
    if CATALOG_PATH != BUNDLED_CATALOG_PATH:
        overrides.update(_read_aliases(CATALOG_PATH))
    return overrides


def canonical_id_for(raw_name: str) -> str:
    global _overrides
    if _overrides is None:
        _overrides = _load_overrides()
    norm = normalize_test_name(raw_name)
    # `normalize_test_name` descarta el "%", así que "Linfocitos %" y
    # "Linfocitos" (recuento absoluto, Synlab) normalizan igual; con "%" en
    # el nombre se prueba antes el alias "<nombre> pct" para poder separar
    # porcentaje y valor absoluto desde el CSV sin cambiar los id ya
    # existentes (en Maresme "Limfòcits %" -> `limfocits`, el porcentaje).
    if "%" in raw_name and f"{norm} pct" in _overrides:
        return _overrides[f"{norm} pct"]
    if norm in _overrides:
        return _overrides[norm]
    return norm.replace(" ", "_")


def reload_overrides() -> None:
    """Fuerza releer el CSV de alias (tras editarlo en caliente)."""
    global _overrides
    _overrides = _load_overrides()


def get_description(canonical_id: str) -> Optional[str]:
    """Descripción en lenguaje llano de una prueba, para quien no esté
    familiarizado con los términos médicos (pestañas Evolución/Comparativa).
    Lee `data/descripciones/<canonical_id>.txt`; `None` si todavía no existe
    ninguna ficha para esa prueba (`canonical_id` sale siempre de
    `normalize_test_name`, que solo admite `[a-z0-9_]`, así que no hay riesgo
    de recorrido de rutas al construir la ruta del fichero)."""
    path = DESCRIPTIONS_DIR / f"{canonical_id}.txt"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def add_aliases(pairs: dict[str, str]) -> None:
    """Añade (o sobrescribe) entradas en el CSV de alias y recarga el
    catálogo en memoria. Usado por la pestaña "Normalizar pruebas" al fundir
    manualmente dos o más nombres que en realidad son la misma
    determinación."""
    if not pairs:
        return
    # Solo la capa del usuario: así una versión nueva de la app sigue
    # pudiendo corregir sus propios alias.
    overrides = _read_aliases(CATALOG_PATH)
    overrides.update(pairs)
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["alias_normalizado", "canonical_id"])
        for alias, canonical in sorted(overrides.items()):
            writer.writerow([alias, canonical])
    reload_overrides()
