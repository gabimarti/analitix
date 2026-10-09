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
    assert [d["fichero"] for d in databases.list_databases()] == ["paciente_a", "paciente_b"]  # por nombre
    # La lista no lleva más que nombre y fichero (va sin cifrar).
    assert json.loads(config.DB_LIST_PATH.read_text(encoding="utf-8"))[0] == {"nombre": "Paciente B",
                                                                              "fichero": "paciente_b"}

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


@pytest.mark.parametrize("nombre, fichero, error", [
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
])
def test_validate_new_rejects(carpeta, nombre, fichero, error):
    databases.add_database("Ya está", "existente")
    assert error in databases.validate_new(nombre, fichero)
    with pytest.raises(ValueError):
        databases.add_database(nombre, fichero)


def test_validate_new_accepts_and_suggests(carpeta):
    assert databases.validate_new("Àngels Puig", "Àngels Puig 0001") is None
    assert databases.suggest_filename("Ana/María: 1234*") == "Ana_María_ 1234_"
