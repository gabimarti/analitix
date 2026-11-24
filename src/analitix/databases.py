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

import datetime as dt
import json
import re
import shutil
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
_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


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
        return (
            "El nombre de la base de datos solo puede llevar letras, números, espacios, guiones, "
            f"guiones bajos y puntos (máximo {FILENAME_MAX}), sin empezar ni acabar en espacio o punto."
        )
    if fichero.split(".")[0].casefold() in _RESERVED:
        return f"«{fichero}» es un nombre reservado de Windows; elige otro."
    existentes = list_databases()
    # Windows no distingue mayúsculas en los nombres de fichero.
    if (
        any(d["fichero"].casefold() == fichero.casefold() for d in existentes)
        or db_path(fichero).exists()
    ):
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
    _register(nombre, fichero)


def _register(nombre: str, fichero: str) -> None:
    """Añade la entrada a la lista sin validar (quien llama ya lo hizo, antes
    de crear el fichero)."""
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


# -- Gestor de bases de datos ---------------------------------------------
# Copia de seguridad = el fichero cifrado tal cual (sigue protegido con la
# misma contraseña). Con la BD abierta basta con hacer `commit` antes: el
# diario de SQLite es el de por defecto (DELETE), sin ficheros -wal aparte.

REMINDER_DEFAULT_DAYS = 30


def backup_suggested_name(fichero: str) -> str:
    return f"{fichero}_{dt.date.today():%Y%m%d}.db"


def backup_dir() -> Path:
    """Carpeta que se propone al guardar una copia de seguridad: la elegida
    en Configuración → Seguridad o, si no hay (o ya no existe), la carpeta
    personal del usuario (no la de importación, que es la que recordaba el
    diálogo de Windows)."""
    carpeta = load_config().get("carpeta_copias")
    return Path(carpeta) if carpeta and Path(carpeta).is_dir() else Path.home()


def set_backup_dir(carpeta: Path) -> None:
    cfg = load_config()
    cfg["carpeta_copias"] = str(carpeta)
    save_config(cfg)


def backup_database(fichero: str, destino: Path) -> None:
    """Copia el fichero cifrado de la BD a `destino` y anota la fecha."""
    if destino.resolve() == db_path(fichero).resolve():
        raise ValueError("La copia no puede sustituir a la propia base de datos.")
    shutil.copy2(db_path(fichero), destino)
    cfg = load_config()
    cfg.setdefault("copias", {})[fichero] = dt.date.today().isoformat()
    save_config(cfg)


def last_backup(fichero: str) -> dt.date | None:
    fecha = load_config().get("copias", {}).get(fichero)
    return dt.date.fromisoformat(fecha) if fecha else None


def reminder_days() -> int:
    """Cada cuántos días recordar la copia de seguridad (0 = nunca)."""
    return int(load_config().get("recordatorio_copia_dias", REMINDER_DEFAULT_DAYS))


def set_reminder_days(dias: int) -> None:
    if dias < 0:
        raise ValueError("Los días no pueden ser negativos.")
    cfg = load_config()
    cfg["recordatorio_copia_dias"] = dias
    save_config(cfg)


def backup_overdue(fichero: str, hoy: dt.date | None = None) -> int | None:
    """Días desde la última copia si toca recordarla (`None` si no toca);
    -1 si nunca se ha hecho ninguna."""
    dias = reminder_days()
    if dias <= 0:
        return None
    ultima = last_backup(fichero)
    if ultima is None:
        return -1
    transcurridos = ((hoy or dt.date.today()) - ultima).days
    return transcurridos if transcurridos >= dias else None


def add_existing_database(nombre: str, fichero: str, origen: Path) -> None:
    """Añade a la lista una BD que ya existe (una copia de seguridad, o una
    traída de otro equipo): la copia a `config.PATIENTS_DIR` con el nombre
    `fichero` y la registra. El original no se toca. No se comprueba la
    contraseña aquí: se pide al abrirla."""
    error = validate_new(nombre, fichero)
    if error:
        raise ValueError(error)
    shutil.copy2(origen, db_path(fichero))
    _register(nombre, fichero)


def delete_database(fichero: str) -> None:
    """Borra la BD: el fichero, su entrada de la lista y lo que la
    configuración guarda de ella (irreversible; las copias de seguridad que
    se hicieran siguen donde se guardaron)."""
    db_path(fichero).unlink(missing_ok=True)
    remove_database(fichero)
    cfg = load_config()
    cfg.get("copias", {}).pop(fichero, None)
    if cfg.get("ultima_bd") == fichero:
        del cfg["ultima_bd"]
    save_config(cfg)


def split_database(origen: Path, password: str, destinos: list[tuple[int, str, str]]) -> None:
    """Separa una BD antigua con varios pacientes en una BD por paciente.
    `destinos` = `(patient_id, nombre, fichero)` por cada BD nueva: cada una
    es una copia cifrada del original (misma contraseña) de la que se borran
    los demás pacientes con todos sus datos (`repository.delete_patient`).
    El original no cambia. Si algo falla, se deshace lo que se había
    creado y se relanza el error."""
    # Import local: `repository` arrastra `pdf_parser` y este módulo se
    # importa al arrancar, antes de la ventana de bienvenida.
    from analitix.db import connect
    from analitix.repository import delete_patient

    for _pid, nombre, fichero in destinos:
        error = validate_new(nombre, fichero)
        if error:
            raise ValueError(error)
    creadas: list[str] = []
    try:
        for patient_id, nombre, fichero in destinos:
            shutil.copy2(origen, db_path(fichero))
            creadas.append(fichero)
            con = connect(password, db_path(fichero))
            try:
                otros = con.execute(
                    "SELECT id FROM patients WHERE id != ?", (patient_id,)
                ).fetchall()
                for (otro,) in otros:
                    delete_patient(con, otro)
                con.execute("VACUUM")  # que no queden restos de los demás en el fichero
            finally:
                con.close()
            _register(nombre, fichero)
    except Exception:
        for fichero in creadas:
            db_path(fichero).unlink(missing_ok=True)
            remove_database(fichero)
        raise
