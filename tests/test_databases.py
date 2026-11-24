import json

import pytest

from analitix import config, databases
from analitix.db import WrongPasswordError, connect


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    """Lista, configuración y bases de datos de paciente en una carpeta temporal."""
    monkeypatch.setattr(config, "PATIENTS_DIR", tmp_path / "pacientes")
    monkeypatch.setattr(config, "DB_LIST_PATH", tmp_path / "bases_de_datos.json")
    monkeypatch.setattr(config, "APP_CONFIG_PATH", tmp_path / "config.json")
    return tmp_path


def test_add_list_and_last_database(carpeta):
    assert databases.list_databases() == []
    assert databases.last_database() is None
    databases.add_database("Paciente B", "paciente_b")
    databases.add_database("paciente a", "paciente_a")
    assert [d["fichero"] for d in databases.list_databases()] == [
        "paciente_a",
        "paciente_b",
    ]  # por nombre
    # La lista no lleva más que nombre y fichero (va sin cifrar).
    assert json.loads(config.DB_LIST_PATH.read_text(encoding="utf-8"))[0] == {
        "nombre": "Paciente B",
        "fichero": "paciente_b",
    }

    databases.set_last_database("paciente_b")
    assert databases.last_database() is None  # el fichero aún no existe
    connect("clave-b", databases.db_path("paciente_b")).close()
    assert databases.last_database() == {"nombre": "Paciente B", "fichero": "paciente_b"}
    databases.remove_database("paciente_b")
    assert [d["fichero"] for d in databases.list_databases()] == ["paciente_a"]
    assert databases.db_path("paciente_b").exists()  # quitar de la lista no borra el fichero


def test_each_database_has_its_own_password(carpeta):
    for fichero, clave in (("uno", "clave-uno"), ("dos", "clave-dos")):
        databases.add_database(fichero.capitalize(), fichero)
        connect(clave, databases.db_path(fichero)).close()
    connect("clave-dos", databases.db_path("dos")).close()
    with pytest.raises(WrongPasswordError):
        connect("clave-uno", databases.db_path("dos"))


@pytest.mark.parametrize(
    "nombre, fichero, error",
    [
        ("", "x", "nombre para el paciente"),
        ("x" * 41, "x", "más de 40"),
        ("Ana", "", "nombre para la base de datos"),
        ("Ana", "ana/dni", "solo puede llevar"),
        ("Ana", "-ana", "solo puede llevar"),
        ("Ana", "ana.", "solo puede llevar"),
        ("Ana", "CON", "reservado"),
        ("Ana", "existente", "Ya existe"),
        ("Ana", "EXISTENTE", "Ya existe"),  # Windows no distingue mayúsculas
        ("Ya está", "otra", "Ya hay un paciente"),
    ],
)
def test_validate_new_rejects(carpeta, nombre, fichero, error):
    databases.add_database("Ya está", "existente")
    assert error in databases.validate_new(nombre, fichero)
    with pytest.raises(ValueError):
        databases.add_database(nombre, fichero)


def test_validate_new_accepts_and_suggests(carpeta):
    assert databases.validate_new("Àngels Puig", "Àngels Puig 0001") is None
    assert databases.suggest_filename("Ana/María: 1234*") == "Ana_María_ 1234_"


def test_backup_reminder_and_delete(carpeta):
    import datetime as dt

    databases.add_database("Paciente A", "paciente_a")
    connect("clave", databases.db_path("paciente_a")).close()
    assert databases.backup_overdue("paciente_a") == -1  # nunca se ha hecho
    destino = carpeta / "copia.db"
    databases.backup_database("paciente_a", destino)
    assert destino.read_bytes() == databases.db_path("paciente_a").read_bytes()
    assert databases.last_backup("paciente_a") == dt.date.today()
    assert databases.backup_overdue("paciente_a") is None
    dentro_de = dt.date.today() + dt.timedelta(days=databases.REMINDER_DEFAULT_DAYS)
    assert databases.backup_overdue("paciente_a", hoy=dentro_de) == databases.REMINDER_DEFAULT_DAYS
    databases.set_reminder_days(0)
    assert databases.backup_overdue("paciente_a", hoy=dentro_de) is None
    with pytest.raises(ValueError):
        databases.backup_database("paciente_a", databases.db_path("paciente_a"))

    # Restaurar la copia como otra BD de la lista.
    databases.add_existing_database("Copia A", "copia_a", destino)
    connect("clave", databases.db_path("copia_a")).close()
    databases.set_last_database("paciente_a")
    databases.delete_database("paciente_a")
    assert not databases.db_path("paciente_a").exists()
    assert [d["fichero"] for d in databases.list_databases()] == ["copia_a"]
    assert databases.last_database() is None
    assert databases.last_backup("paciente_a") is None
    assert destino.exists()  # las copias no se borran


def test_split_database_one_patient_each(carpeta):
    from analitix.repository import get_or_create_patient

    origen = carpeta / "antigua.db"
    con = connect("clave", origen)
    a, _ = get_or_create_patient(con, "Ruiz, Ana", "1980-01-01", None, "1")
    b, _ = get_or_create_patient(con, "Gil, Luis", "1975-02-02", None, "2")
    for pid, numero in ((a, "R1"), (b, "R2")):
        con.execute(
            "INSERT INTO reports (patient_id, report_number, source_file) VALUES (?, ?, ?)",
            (pid, numero, f"{numero}.pdf"),
        )
    con.commit()
    con.close()

    with pytest.raises(WrongPasswordError):
        databases.split_database(origen, "mal", [(a, "Ana", "ana"), (b, "Luis", "luis")])
    assert databases.list_databases() == []  # sin restos del intento fallido
    assert not databases.db_path("ana").exists()

    databases.split_database(origen, "clave", [(a, "Ana", "ana"), (b, "Luis", "luis")])
    for fichero, nombre, informe in (("ana", "Ruiz, Ana", "R1"), ("luis", "Gil, Luis", "R2")):
        nueva = connect("clave", databases.db_path(fichero))
        assert nueva.execute("SELECT full_name FROM patients").fetchall() == [(nombre,)]
        assert nueva.execute("SELECT report_number FROM reports").fetchall() == [(informe,)]
        nueva.close()
    original = connect("clave", origen)
    assert original.execute("SELECT COUNT(*) FROM patients").fetchone() == (2,)  # intacta
    original.close()


def test_backup_dir_defaults_to_home_and_is_configurable(carpeta):
    from pathlib import Path

    assert databases.backup_dir() == Path.home()
    destino = carpeta / "copias"
    destino.mkdir()
    databases.set_backup_dir(destino)
    assert databases.backup_dir() == destino
    destino.rmdir()  # carpeta borrada (p. ej. disco externo desconectado)
    assert databases.backup_dir() == Path.home()
