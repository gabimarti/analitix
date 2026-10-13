"""Una base de datos = un paciente: los informes que no encajan con el
paciente de la BD no se importan sin confirmación («Es este paciente» /
«No es»). Solo datos inventados."""

from pathlib import Path

import pytest

from analitix import ingest
from analitix.repository import (
    STATUS_DISCARDED,
    STATUS_OTHER_PATIENT,
    discard_other_patient_file,
    find_patient,
    get_or_create_patient,
    list_files_other_patient,
    set_target,
)

PACIENTE = {
    "full_name": "GARCIA LOPEZ, JUAN",
    "birth_date": "1970-05-20",
    "dni": None,
    "nhc": "111",
}


def _header(**cambios) -> dict:
    return {
        **PACIENTE,
        "cip": None,
        "report_number": None,
        "request_date": "2026-01-10",
        "validation_date": None,
        **cambios,
    }


def _resultado(pdf_path: Path, header: dict) -> dict:
    return {
        "header": header,
        "results": [
            {
                "raw_name": "Glucosa",
                "loinc_code": None,
                "value_raw": "90",
                "value_num": 90.0,
                "unit": "mg/dL",
                "ref_low": 70.0,
                "ref_high": 100.0,
                "ref_text": "70 - 100",
                "flag_pdf": None,
                "section": None,
                "test_group": None,
                "sample_date": None,
            }
        ],
        "source_file": pdf_path.name,
        "format_id": "ficticio",
        "format_name": "Laboratorio ficticio",
        "format_short_name": "Ficticio",
        "manual_review_only": False,
    }


@pytest.fixture
def informes(monkeypatch, tmp_path):
    """Crea PDF vacíos con la cabecera que se le indique: `informes(nombre, **cabecera)`."""
    cabeceras: dict[str, dict] = {}
    monkeypatch.setattr(ingest, "parse_report", lambda p: _resultado(p, cabeceras[p.name]))

    def crear(nombre: str, numero: str, **cambios) -> Path:
        path = tmp_path / nombre
        path.write_bytes(nombre.encode())  # contenido distinto → huella distinta
        cabeceras[nombre] = _header(report_number=numero, **cambios)
        return path

    return crear


def _importar(db, path):
    return ingest._ingest_one(db, path, ingest.file_hash(path))


def _count(db, tabla):
    return db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]  # noqa: S608 - tabla fija


def test_first_report_sets_the_patient_and_same_identity_imports(db, informes):
    _importar(db, informes("a.pdf", "1"))
    _importar(db, informes("b.pdf", "2"))
    assert _count(db, "patients") == 1
    assert _count(db, "reports") == 2


def test_name_in_other_order_with_same_birth_date_imports(db, informes):
    _importar(db, informes("a.pdf", "1"))
    _importar(db, informes("b.pdf", "2", full_name="JUAN GARCIA LOPEZ"))  # sin coma, otro orden
    _importar(db, informes("c.pdf", "3", full_name="GARCIA LOPEZ JUAN"))
    assert _count(db, "patients") == 1
    assert _count(db, "reports") == 3


def test_new_nhc_with_same_name_imports(db, informes):
    _importar(db, informes("a.pdf", "1"))
    _importar(db, informes("b.pdf", "2", nhc="222"))
    assert _count(db, "patients") == 1
    assert _count(db, "reports") == 2


def test_report_without_birth_date_waits_for_confirmation(db, informes):
    _importar(db, informes("a.pdf", "1"))
    with pytest.raises(ingest.OtherPatientError, match="no trae fecha de nacimiento"):
        _importar(
            db, informes("b.pdf", "2", birth_date=None, full_name="JUAN GARCIA LOPEZ", nhc="999")
        )
    assert _count(db, "patients") == 1  # no se crea un segundo paciente
    assert _count(db, "reports") == 1  # ni se importan sus resultados
    pendientes = list_files_other_patient(db)
    assert [p["filename"] for p in pendientes] == ["b.pdf"]


def test_different_dni_or_birth_date_is_flagged_as_probably_another_person(db, informes):
    _importar(db, informes("a.pdf", "1", dni="00000000T"))
    with pytest.raises(ingest.OtherPatientError, match="PROBABLEMENTE OTRA PERSONA.*DNI distinto"):
        _importar(db, informes("b.pdf", "2", full_name="ANA PEREZ RUIZ", dni="11111111H"))
    with pytest.raises(ingest.OtherPatientError, match="PROBABLEMENTE OTRA PERSONA: fecha"):
        _importar(db, informes("c.pdf", "3", birth_date="1971-05-20"))


def test_confirm_same_patient_imports_and_next_similar_report_matches(db, informes, tmp_path):
    _importar(db, informes("a.pdf", "1"))
    (owner,) = db.execute("SELECT id FROM patients").fetchone()
    sin_fecha = {"birth_date": None, "full_name": "GARCIA LOPEZ, J.", "nhc": "333"}
    b = informes("b.pdf", "2", **sin_fecha)
    with pytest.raises(ingest.OtherPatientError):
        _importar(db, b)

    ingest.confirm_same_patient(db, b, owner)
    assert _count(db, "reports") == 2
    assert db.execute("SELECT DISTINCT patient_id FROM reports").fetchall() == [(owner,)]
    assert list_files_other_patient(db) == []
    # Los datos del paciente no se sustituyen por los del alias.
    assert db.execute("SELECT full_name, nhc FROM patients").fetchone() == (
        "GARCIA LOPEZ, JUAN",
        "111",
    )

    # El siguiente informe con la misma identidad encaja solo.
    _importar(db, informes("c.pdf", "3", **sin_fecha))
    assert _count(db, "reports") == 3
    assert find_patient(db, "GARCIA LOPEZ, J.", None, None, "333") == (owner, "alias")


def test_confirmed_identity_with_conflicting_birth_date_is_not_asked_again(db, informes):
    # P. ej. un laboratorio con la fecha de nacimiento mal escrita: el
    # usuario confirma una vez y los siguientes informes iguales encajan.
    _importar(db, informes("a.pdf", "1"))
    (owner,) = db.execute("SELECT id FROM patients").fetchone()
    errata = {"birth_date": "1970-02-05"}
    b = informes("b.pdf", "2", **errata)
    with pytest.raises(ingest.OtherPatientError, match="PROBABLEMENTE OTRA PERSONA"):
        _importar(db, b)
    ingest.confirm_same_patient(db, b, owner)
    _importar(db, informes("c.pdf", "3", **errata))
    assert _count(db, "reports") == 3 and _count(db, "patients") == 1


def test_discarded_report_is_not_asked_again_until_it_changes(db, informes, tmp_path):
    _importar(db, informes("a.pdf", "1"))
    b = informes("b.pdf", "2", full_name="ANA PEREZ RUIZ", birth_date="1990-02-02")
    with pytest.raises(ingest.OtherPatientError):
        _importar(db, b)
    discard_other_patient_file(db, "b.pdf")
    status = db.execute("SELECT status FROM processed_files WHERE filename = 'b.pdf'").fetchone()
    assert status == (STATUS_DISCARDED,)

    result = ingest.ingest_folder(db, tmp_path)
    assert "b.pdf" in result.skipped and not result.other_patient
    b.write_bytes(b"contenido nuevo")  # si el fichero cambia, se vuelve a comprobar
    result = ingest.ingest_folder(db, tmp_path)
    assert [name for name, _ in result.other_patient] == ["b.pdf"]
    status = db.execute("SELECT status FROM processed_files WHERE filename = 'b.pdf'").fetchone()
    assert status == (STATUS_OTHER_PATIENT,)


def test_ingest_folder_reports_other_patient_without_names_in_log(db, informes, tmp_path, caplog):
    informes("a.pdf", "1")
    informes("b.pdf", "2", full_name="ANA PEREZ RUIZ", birth_date="1990-02-02")
    with caplog.at_level("INFO", logger="analitix"):
        result = ingest.ingest_folder(db, tmp_path)
    assert [name for name, _ in result.processed] == ["a.pdf"]
    assert [name for name, _ in result.other_patient] == ["b.pdf"]
    assert "ANA PEREZ" in result.other_patient[0][1]  # el motivo, para la pantalla
    assert "PEREZ" not in caplog.text and "GARCIA" not in caplog.text


def test_reimporting_the_only_report_keeps_a_patient_with_other_data(db, informes):
    a = informes("a.pdf", "1")
    _importar(db, a)
    (owner,) = db.execute("SELECT id FROM patients").fetchone()
    set_target(db, owner, "glucosa_serum", None, 100.0, "objetivo ficticio")
    db.commit()
    _importar(db, a)  # reimportación (p. ej. «Reimportar todo»)
    assert db.execute("SELECT id FROM patients").fetchall() == [(owner,)]
    assert _count(db, "targets") == 1


def test_aliases_follow_merge_and_are_deleted_with_the_patient(db):
    from analitix.repository import (
        add_patient_alias,
        delete_all_data,
        delete_patient,
        merge_patients,
    )

    a, _ = get_or_create_patient(db, "GARCIA LOPEZ, JUAN", "1970-05-20", None, "111")
    b, _ = get_or_create_patient(db, "PEREZ RUIZ, ANA", "1990-02-02", None, "444")
    add_patient_alias(db, b, "PEREZ R., ANA", None, None, "555")
    merge_patients(db, [b], a)
    assert db.execute("SELECT patient_id FROM patient_aliases").fetchall() == [(a,)]
    delete_patient(db, a)
    assert _count(db, "patient_aliases") == 0
    c, _ = get_or_create_patient(db, "SANZ GIL, LUIS", "1985-03-03", None, None)
    add_patient_alias(db, c, "SANZ G., LUIS", None, None, "666")
    delete_all_data(db)
    assert _count(db, "patient_aliases") == 0


def test_legacy_db_with_several_patients_imports_as_before(db, informes):
    get_or_create_patient(db, "PEREZ RUIZ, ANA", "1990-02-02", None, None)
    get_or_create_patient(db, "SANZ GIL, LUIS", "1985-03-03", None, None)
    db.commit()
    _importar(db, informes("a.pdf", "1"))  # no encaja con ninguno: se crea como antes
    assert _count(db, "patients") == 3
