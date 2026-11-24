"""BD de ejemplo (`analitix.demo`): se crea en la carpeta de pacientes, se
añade a la lista, se abre con su contraseña pública y no queda nada a medias
si falla."""

import pytest

from analitix import config, databases, demo
from analitix.db import connect


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    """Lista, configuración y carpeta de pacientes en un directorio temporal."""
    monkeypatch.setattr(config, "PATIENTS_DIR", tmp_path / "pacientes")
    monkeypatch.setattr(config, "DB_LIST_PATH", tmp_path / "bases_de_datos.json")
    monkeypatch.setattr(config, "APP_CONFIG_PATH", tmp_path / "config.json")
    return tmp_path


def test_create_registers_and_opens_with_public_password(carpeta):
    assert demo.create_demo_database() is True
    assert databases.list_databases() == [{"nombre": demo.DEMO_NAME, "fichero": demo.DEMO_FILE}]
    con = connect(demo.DEMO_PASSWORD, databases.db_path(demo.DEMO_FILE))
    try:
        assert con.execute("SELECT full_name FROM patients").fetchall() == [("FICTICIO, PACIENTE",)]
        assert con.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == len(demo.REPORTS)
        assert con.execute("SELECT COUNT(*) FROM results").fetchone()[0] == len(demo.REPORTS) * len(
            demo.PARAMS
        )
        assert con.execute("SELECT COUNT(*) FROM bp_readings").fetchone()[0] > 0
        # La app no fija carpeta de informes: no existe en el equipo del usuario.
        assert (
            con.execute("SELECT COUNT(*) FROM settings WHERE key = 'reports_dir'").fetchone()[0]
            == 0
        )
    finally:
        con.close()


def test_second_call_keeps_the_existing_one(carpeta):
    demo.create_demo_database()
    path = databases.db_path(demo.DEMO_FILE)
    antes = path.stat().st_mtime_ns
    assert demo.create_demo_database() is False
    assert path.stat().st_mtime_ns == antes
    assert len(databases.list_databases()) == 1


def test_recreated_if_the_file_was_deleted_outside_the_app(carpeta):
    demo.create_demo_database()
    databases.db_path(demo.DEMO_FILE).unlink()
    assert demo.create_demo_database() is True
    assert databases.db_path(demo.DEMO_FILE).exists()
    assert len(databases.list_databases()) == 1


def test_failure_leaves_neither_entry_nor_file(carpeta, monkeypatch):
    def _falla(path, *a, **k):
        path.write_bytes(b"a medias")
        raise OSError("disco lleno")

    monkeypatch.setattr(demo, "build_demo_db", _falla)
    with pytest.raises(OSError):
        demo.create_demo_database()
    assert databases.list_databases() == []
    assert not databases.db_path(demo.DEMO_FILE).exists()
