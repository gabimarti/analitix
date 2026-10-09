# ---------------------------------------------------------------------------
# Script: databases.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-10-09
# Última actualización: 2026-10-09
# ---------------------------------------------------------------------------
"""Lista de bases de datos de paciente y configuración de la aplicación.

Cada paciente tiene su propia base de datos cifrada (`db.connect`) en
`config.PATIENTS_DIR`, con su contraseña. La lista (`config.DB_LIST_PATH`)
solo guarda, de cada una, un nombre corto para reconocerla y el nombre del
fichero: no lleva datos sensibles, así que es un JSON sin cifrar que se lee
antes de pedir ninguna contraseña. La configuración de la aplicación
(`config.APP_CONFIG_PATH`, también JSON) guarda la última base de datos
usada, para abrirla directamente en el siguiente arranque.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from analitix import config

NAME_MAX = 40  # nombre corto del paciente en la lista
FILENAME_MAX = 60
# Nombre del fichero (sin ".db"): letras (también acentuadas), números,
# espacios, guiones, guiones bajos y puntos, sin empezar ni acabar en espacio
# o punto (Windows no los admite al final).
_FILENAME_RE = re.compile(r"[\w][\w .-]*[\w-]|[\w]")
# Nombres reservados de Windows: no pueden ser nombre de fichero.
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # sin fichero a medias si se corta la escritura


def list_databases() -> list[dict[str, str]]:
    """Bases de datos registradas, `{"nombre", "fichero"}`, ordenadas por
    nombre."""
    lista = _read_json(config.DB_LIST_PATH, [])
    return sorted(lista, key=lambda d: d["nombre"].casefold())


def db_path(fichero: str) -> Path:
    config.PATIENTS_DIR.mkdir(parents=True, exist_ok=True)
    return config.PATIENTS_DIR / f"{fichero}.db"


def find_database(fichero: str) -> dict[str, str] | None:
    return next((d for d in list_databases() if d["fichero"] == fichero), None)


def suggest_filename(nombre: str) -> str:
    """Nombre de fichero propuesto a partir del nombre del paciente (el
    usuario puede cambiarlo): los caracteres no válidos pasan a "_"."""
    limpio = re.sub(r"[^\w .-]", "_", nombre.strip())[:FILENAME_MAX]
    return limpio.strip(" .")


def validate_new(nombre: str, fichero: str) -> str | None:
    """Mensaje de error si no se puede crear una base de datos con ese
    nombre y fichero, o `None` si es válido."""
    nombre, fichero = nombre.strip(), fichero.strip()
    if not nombre:
        return "Escribe un nombre para el paciente."
    if len(nombre) > NAME_MAX:
        return f"El nombre no puede tener más de {NAME_MAX} caracteres."
    if not fichero:
        return "Escribe un nombre para la base de datos."
    if len(fichero) > FILENAME_MAX or not _FILENAME_RE.fullmatch(fichero):
        return ("El nombre de la base de datos solo puede llevar letras, números, espacios, guiones, "
                f"guiones bajos y puntos (máximo {FILENAME_MAX}), sin empezar ni acabar en espacio o punto.")
    if fichero.split(".")[0].casefold() in _RESERVED:
        return f"«{fichero}» es un nombre reservado de Windows; elige otro."
    existentes = list_databases()
    # Windows no distingue mayúsculas en los nombres de fichero.
    if any(d["fichero"].casefold() == fichero.casefold() for d in existentes) or db_path(fichero).exists():
        return f"Ya existe una base de datos «{fichero}»."
    if any(d["nombre"].casefold() == nombre.casefold() for d in existentes):
        return f"Ya hay un paciente «{nombre}» en la lista."
    return None


def add_database(nombre: str, fichero: str) -> None:
    """Registra una base de datos en la lista (el fichero lo crea
    `db.connect` al abrirlo por primera vez)."""
    error = validate_new(nombre, fichero)
    if error:
        raise ValueError(error)
    lista = _read_json(config.DB_LIST_PATH, [])
    lista.append({"nombre": nombre.strip(), "fichero": fichero.strip()})
    _write_json(config.DB_LIST_PATH, lista)


def remove_database(fichero: str) -> None:
    """Quita una base de datos de la lista (no borra el fichero)."""
    lista = [d for d in _read_json(config.DB_LIST_PATH, []) if d["fichero"] != fichero]
    _write_json(config.DB_LIST_PATH, lista)


def load_config() -> dict[str, Any]:
    return _read_json(config.APP_CONFIG_PATH, {})


def save_config(cfg: dict[str, Any]) -> None:
    _write_json(config.APP_CONFIG_PATH, cfg)


def last_database() -> dict[str, str] | None:
    """Última base de datos usada, si sigue en la lista y existe su fichero."""
    fichero = load_config().get("ultima_bd")
    entrada = find_database(fichero) if fichero else None
    return entrada if entrada and db_path(entrada["fichero"]).exists() else None


def set_last_database(fichero: str) -> None:
    cfg = load_config()
    cfg["ultima_bd"] = fichero
    save_config(cfg)
