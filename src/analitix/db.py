# ---------------------------------------------------------------------------
# Script: db.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-10-09
# ---------------------------------------------------------------------------
"""Acceso a la base de datos SQLite cifrada (SQLCipher) del proyecto."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from sqlcipher3 import dbapi2 as sqlcipher


SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    birth_date TEXT,
    dni TEXT,
    nhc TEXT,
    nhc_alt TEXT,
    sex TEXT,
    cip TEXT,
    smoker_current INTEGER,
    smoker_former INTEGER,
    smoker_former_from INTEGER,
    smoker_former_to INTEGER,
    smoker_former_period TEXT,
    UNIQUE(name_key, birth_date)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    report_number TEXT,
    request_date TEXT,
    validation_date TEXT,
    source_file TEXT NOT NULL,
    file_md5 TEXT,
    assistance_number TEXT,
    lab TEXT,
    UNIQUE(patient_id, report_number)
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    section TEXT,
    test_group TEXT,
    loinc_code TEXT,
    raw_name TEXT NOT NULL,
    canonical_id TEXT,
    value_raw TEXT,
    value_num REAL,
    unit TEXT,
    ref_low REAL,
    ref_high REAL,
    ref_text TEXT,
    flag_pdf TEXT,
    flag_calc TEXT,
    sample_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_results_canonical ON results(canonical_id);
CREATE INDEX IF NOT EXISTS idx_results_report ON results(report_id);

CREATE TABLE IF NOT EXISTS processed_files (
    id INTEGER PRIMARY KEY,
    filename TEXT UNIQUE NOT NULL,
    file_hash TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    report_id INTEGER,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Objetivo indicado por el médico para un paciente y una prueba (p. ej. LDL
-- < 100 mg/dL): lo introduce la persona a mano, nunca lo calcula Analitix.
-- En los gráficos sustituye al rango del laboratorio. Un límite puede faltar
-- ("< 100" = solo target_high). set_on: "AAAA-MM-DD".
CREATE TABLE IF NOT EXISTS targets (
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    canonical_id TEXT NOT NULL,
    target_low REAL,
    target_high REAL,
    note TEXT,
    set_on TEXT,
    PRIMARY KEY (patient_id, canonical_id)
);

-- Mediciones de tensión arterial (entrada manual o CSV, ver
-- blood_pressure.py). measured_at: "AAAA-MM-DD HH:MM"; place: "casa" o
-- "consulta" (los umbrales de las guías difieren); source: "manual" o "csv".
-- Una sola medición por paciente y minuto: reimportar un CSV no duplica.
CREATE TABLE IF NOT EXISTS bp_readings (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    measured_at TEXT NOT NULL,
    systolic INTEGER NOT NULL,
    diastolic INTEGER NOT NULL,
    pulse INTEGER,
    place TEXT NOT NULL DEFAULT 'casa',
    note TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    UNIQUE(patient_id, measured_at)
);
CREATE INDEX IF NOT EXISTS idx_bp_patient ON bp_readings(patient_id, measured_at);
"""


class WrongPasswordError(Exception):
    pass


def _ensure_column(con: sqlcipher.Connection, table: str, column: str, coltype: str) -> None:
    """Añade una columna a una tabla ya existente si todavía no la tiene, para
    poder evolucionar el esquema (`SCHEMA`) sin perder las bases de datos ya
    creadas con una versión anterior. `table`/`column`/`coltype` son siempre
    literales fijos del propio código, nunca vienen de fuera."""
    existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}  # noqa: S608
    if column not in existing:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")  # noqa: S608


# SQLCipher interpreta `x'<64 o 96 hex>'` como una clave binaria en bruto
# (sin pasar por PBKDF2), en vez de una contraseña textual normal — un caso
# de esquina, pero si una contraseña elegida por el usuario coincidiera por
# casualidad con esa forma, `PRAGMA key = '...'` la trataría así en
# silencio. Se rechaza antes de construir el PRAGMA (auditoría de
# seguridad, 2026-09-24).
_RAW_KEY_LITERAL_RE = re.compile(r"[Xx]'[0-9A-Fa-f]{64}'|[Xx]'[0-9A-Fa-f]{96}'")


def _set_key(con: sqlcipher.Connection, pragma: str, password: str) -> None:
    if _RAW_KEY_LITERAL_RE.fullmatch(password):
        raise ValueError(
            "Esta contraseña no es válida: coincide con la forma reservada de clave "
            "SQLCipher en bruto (x'...'). Elige otra."
        )
    escaped_password = password.replace("'", "''")
    con.execute(f"PRAGMA {pragma} = '{escaped_password}'")


def connect(password: str, db_path: Path) -> sqlcipher.Connection:
    """Abre (o crea) la base de datos cifrada `db_path` (la de un paciente,
    ver `databases.db_path`) con la contraseña dada."""
    con = sqlcipher.connect(str(db_path))
    _set_key(con, "key", password)
    try:
        con.execute("SELECT count(*) FROM sqlite_master")
    except sqlcipher.DatabaseError as exc:
        con.close()
        raise WrongPasswordError("Contraseña incorrecta o base de datos dañada") from exc
    con.executescript(SCHEMA)
    _ensure_column(con, "patients", "nhc_alt", "TEXT")
    _ensure_column(con, "reports", "notes", "TEXT")
    _ensure_column(con, "patients", "sex", "TEXT")
    _ensure_column(con, "patients", "cip", "TEXT")
    # Tabaquismo (1 = sí, 0 = no, NULL = no consta): solo se rellena a mano
    # desde la ficha del paciente, ningún PDF lo trae.
    _ensure_column(con, "patients", "smoker_current", "INTEGER")
    _ensure_column(con, "patients", "smoker_former", "INTEGER")
    _ensure_column(con, "patients", "smoker_former_from", "INTEGER")
    _ensure_column(con, "patients", "smoker_former_to", "INTEGER")
    _ensure_column(con, "patients", "smoker_former_period", "TEXT")
    _ensure_column(con, "reports", "file_md5", "TEXT")
    _ensure_column(con, "reports", "assistance_number", "TEXT")
    # Laboratorio/centro de origen (nombre corto del perfil de parser, o
    # "Entrada manual"); NULL en informes importados antes de 2026-09-25
    # hasta la siguiente reimportación forzada.
    _ensure_column(con, "reports", "lab", "TEXT")
    con.commit()
    # Laboratorios excluidos de gráficos y paneles (`repository.set_excluded_labs`):
    # tabla TEMPORAL, propia de esta conexión y nunca guardada en el fichero;
    # la elección del usuario persiste aparte en `settings`.
    con.execute("CREATE TEMP TABLE IF NOT EXISTS excluded_labs (lab TEXT PRIMARY KEY)")
    return con


def rekey(con: sqlcipher.Connection, new_password: str) -> None:
    """Cambia la contraseña de cifrado de la base de datos ya abierta."""
    _set_key(con, "rekey", new_password)


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")
