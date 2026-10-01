from pathlib import Path

from analitix import ingest
from analitix.repository import get_or_create_patient


def test_known_pdf_filenames_sees_other_subfolders(tmp_path, monkeypatch):
    # Caso real (2026-09-17): el usuario organiza los PDF en subcarpetas por
    # persona (informes_analiticas/gmf, informes_analiticas/afg) y cambia de
    # "carpeta actual" para importar cada una. El PDF de una subcarpeta no
    # activa en este momento debe seguir contando como "existente".
    root = tmp_path / "informes_analiticas"
    (root / "gmf").mkdir(parents=True)
    (root / "afg").mkdir(parents=True)
    (root / "gmf" / "informes_GMF_20200101.pdf").write_bytes(b"")
    (root / "afg" / "informes_AFG_20200101.pdf").write_bytes(b"")
    monkeypatch.setattr(ingest, "REPORTS_DIR", root)

    names = ingest.known_pdf_filenames(root / "afg")

    assert "informes_GMF_20200101.pdf" in names
    assert "informes_AFG_20200101.pdf" in names


def _fake_manual_review_result(pdf_path: Path) -> dict:
    return {
        "header": {
            "full_name": None, "dni": None, "nhc": None, "report_number": None,
            "birth_date": None, "request_date": None, "validation_date": None,
        },
        "results": [],
        "source_file": pdf_path.name,
        "format_id": "unknown",
        "format_name": "Formato no reconocido",
        "manual_review_only": True,
    }


def test_manual_review_only_does_not_create_patient(db, monkeypatch, tmp_path):
    # Reproduce el bug del 2026-09-17: un PDF de un centro sin motor de
    # parseo (`manual_review_only`) no debe crear un paciente "de repuesto"
    # con el nombre del fichero — solo debe quedar marcado para revisar.
    monkeypatch.setattr(ingest, "parse_report", _fake_manual_review_result)
    pdf_path = tmp_path / "informes_UNKNOWN0000000_20260101.pdf"
    pdf_path.write_bytes(b"")

    reason, format_name = ingest._ingest_one(db, pdf_path, "fake-hash")

    assert "Formato no reconocido" in reason
    assert "parser no implementado" in reason
    assert format_name == "Formato no reconocido"
    assert db.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0
    row = db.execute(
        "SELECT status, report_id, error_message FROM processed_files WHERE filename = ?",
        (pdf_path.name,),
    ).fetchone()
    assert row == ("review", None, reason)


def _fake_no_birth_date_result(pdf_path: Path) -> dict:
    # Nombre inventado: nunca datos reales de un informe. Reproduce un
    # perfil con motor de parseo real pero sin fecha de nacimiento en la
    # cabecera (p. ej. HUGTIP, que solo trae la edad en años).
    return {
        "header": {
            "full_name": "GARCIA LOPEZ, MARIA", "dni": None, "nhc": "999",
            "report_number": "1", "birth_date": None, "request_date": None,
            "validation_date": None,
        },
        "results": [
            {
                "raw_name": "Glucosa", "loinc_code": None, "value_raw": "100",
                "value_num": 100.0, "unit": "mg/dL", "ref_low": 70.0, "ref_high": 100.0,
                "ref_text": "70 - 100", "flag_pdf": None, "section": None,
                "test_group": None, "sample_date": None,
            }
        ],
        "source_file": pdf_path.name,
        "format_id": "hugtip",
        "format_name": "Hospital Universitari Germans Trias i Pujol (HUGTIP)",
        "manual_review_only": False,
    }


def test_new_patient_without_birth_date_flagged_as_possible_duplicate(db, monkeypatch, tmp_path):
    # Caso real (HUGTIP, 2026-09-17): la misma persona ya tiene paciente en
    # la BD por otro centro que sí trae fecha de nacimiento; un perfil sin
    # fecha de nacimiento nunca podrá emparejar por nombre+fecha con ese
    # paciente aunque el nombre coincida, así que crea uno nuevo — debe
    # quedar marcado para revisar como posible duplicado en vez de colarse
    # en silencio.
    get_or_create_patient(
        db, full_name="GARCIA LOPEZ, MARIA", birth_date="1980-01-01", dni=None, nhc=None,
    )
    db.commit()

    monkeypatch.setattr(ingest, "parse_report", _fake_no_birth_date_result)
    pdf_path = tmp_path / "informes_HUGTIP0000000_20260101.pdf"
    pdf_path.write_bytes(b"")

    reason, format_name = ingest._ingest_one(db, pdf_path, "fake-hash")

    assert "posible duplicado" in reason
    assert format_name == "Hospital Universitari Germans Trias i Pujol (HUGTIP)"
    assert db.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 1
    row = db.execute(
        "SELECT status FROM processed_files WHERE filename = ?", (pdf_path.name,)
    ).fetchone()
    assert row == ("review",)


def test_age_band_range_resolved_with_stored_birth_date(db, monkeypatch, tmp_path):
    # Synlab trae a veces "F. Nac." vacío: la franja de referencia por edad
    # se elige con la fecha de nacimiento del paciente ya guardado.
    get_or_create_patient(db, full_name="GARCIA LOPEZ, MARIA", birth_date="1980-01-01", dni=None, nhc="999")
    db.commit()

    def fake(pdf_path: Path) -> dict:
        parsed = _fake_no_birth_date_result(pdf_path)
        parsed["results"][0].update(
            raw_name="Tiroxina libre (T4L)", value_raw="0,95", value_num=0.95, unit="ng/dL",
            ref_low=None, ref_high=None, ref_text=None, sample_date="2024-01-01",
            age_bands=[(0, 0, "0.75-1.49"), (20, 200, "0.61-1.12")],
        )
        return parsed

    monkeypatch.setattr(ingest, "parse_report", fake)
    pdf_path = tmp_path / "informes_SYNLAB0000000_20240101.pdf"
    pdf_path.write_bytes(b"")
    ingest._ingest_one(db, pdf_path, "fake-hash")

    row = db.execute("SELECT ref_low, ref_high, flag_calc FROM results").fetchone()
    assert row == (0.61, 1.12, "normal")


def test_ingest_folder_optionally_includes_subfolders(db, monkeypatch, tmp_path):
    monkeypatch.setattr(ingest, "parse_report", _fake_no_birth_date_result)
    monkeypatch.setattr(ingest, "REPORTS_DIR", tmp_path)
    (tmp_path / "persona").mkdir()
    (tmp_path / "persona" / "informes_SINTETICO_20260101.pdf").write_bytes(b"%PDF sintetico")

    assert ingest.ingest_folder(db, tmp_path).processed == []
    result = ingest.ingest_folder(db, tmp_path, recursive=True)
    assert [name for name, _ in result.processed] == ["informes_SINTETICO_20260101.pdf"]


def test_log_uses_file_hash_not_filename(db, monkeypatch, tmp_path, caplog):
    # El nombre de un PDF real puede ser el del paciente: el log (texto
    # plano) solo debe llevar la huella del fichero, tanto en "revisar"
    # como en error.
    def _parse(pdf_path):
        if "error" in pdf_path.name:
            raise RuntimeError("fallo sintético")
        return _fake_no_birth_date_result(pdf_path)  # sin fecha de nacimiento → revisar

    monkeypatch.setattr(ingest, "parse_report", _parse)
    (tmp_path / "PACIENTE_FICTICIO_revisar.pdf").write_bytes(b"%PDF uno")
    (tmp_path / "PACIENTE_FICTICIO_error.pdf").write_bytes(b"%PDF dos")
    with caplog.at_level("INFO", logger="analitix"):
        result = ingest.ingest_folder(db, tmp_path)

    assert result.review and result.errors
    assert "PACIENTE_FICTICIO" not in caplog.text
    assert caplog.text.count("md5=") == 2
