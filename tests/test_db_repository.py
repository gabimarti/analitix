from pathlib import Path

import pytest

from analitix.db import WrongPasswordError, connect, rekey
from analitix.pdf_parser import compute_flag
from analitix.repository import (
    MergeBlockedError,
    already_processed,
    clear_previous_import,
    create_manual_report,
    get_all_results,
    get_latest_report_summary,
    get_or_create_patient,
    get_series,
    insert_result,
    list_canonical_groups,
    list_patients,
    merge_canonical_ids,
    merge_check,
    record_processed_file,
    upsert_report,
)


def _insert_report_row(con, patient_id, report_number, fecha, raw_name, canonical_id, value_num, unit,
                        ref_low=None, ref_high=None):
    report_id = upsert_report(con, patient_id, report_number, fecha, fecha, "synthetic.pdf")
    insert_result(
        con, report_id,
        dict(section=None, test_group=None, loinc_code=None, raw_name=raw_name,
             canonical_id=canonical_id, value_raw=str(value_num), value_num=value_num, unit=unit,
             ref_low=ref_low, ref_high=ref_high, ref_text=None, flag_pdf=None,
             flag_calc=compute_flag(value_num, ref_low, ref_high), sample_date=None),
    )
    con.commit()
    return report_id


def test_sqlcipher_database_and_wrong_password(tmp_path: Path):
    path = tmp_path / "encrypted.db"
    con = connect("secret", path)
    con.close()
    wrong = None
    try:
        connect("wrong", path)
    except WrongPasswordError as exc:
        wrong = exc
    assert wrong is not None
    con = connect("secret", path)
    rekey(con, "new-secret")
    con.close()
    assert connect("new-secret", path)


def test_connect_rejects_sqlcipher_raw_key_literal_shape(tmp_path: Path):
    # `PRAGMA key = 'x<64 o 96 hex>'` es la sintaxis reservada de SQLCipher
    # para una clave binaria en bruto (sin PBKDF2) — una contraseña de
    # usuario que coincidiera con esa forma por casualidad debe rechazarse
    # explícitamente en vez de tratarse como clave en bruto en silencio.
    path = tmp_path / "encrypted.db"
    raw_key_shaped = "x'" + "AB" * 32 + "'"  # 64 hex chars, valor sintético
    try:
        connect(raw_key_shaped, path)
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert not path.exists() or path.stat().st_size == 0


def test_patient_report_result_and_processed_file_lifecycle(db):
    patient_id, matched = get_or_create_patient(
        db, "Lovelace, Ada", "1815-12-10", "DNI1", "NHC1"
    )
    assert matched == "new"
    same_id, matched = get_or_create_patient(
        db, "Ada Lovelace", "1815-12-10", "DNI1", "NHC2"
    )
    assert (same_id, matched) == (patient_id, "name")
    assert list_patients(db)[0]["nhc_alt"] == "NHC1"

    report_id = upsert_report(db, patient_id, "R-1", "2024-01-01", None, "old.pdf")
    assert upsert_report(db, patient_id, "R-1", None, None, "renamed.pdf") == report_id
    report_id = create_manual_report(
        db, patient_id, "2024-02-01", [{"raw_name": "Glucosa", "value_num": 110,
                                        "unit": "mg/dL", "ref_low": 70, "ref_high": 100}]
    )
    assert get_series(db, "glucosa", patient_id)[0]["value_num"] == 110
    assert get_all_results(db, patient_id)[0]["paciente"] == "Ada Lovelace"

    record_processed_file(db, "synthetic.pdf", "hash", "ok", report_id)
    db.commit()
    assert already_processed(db, "synthetic.pdf", "hash")
    record_processed_file(db, "synthetic.pdf", "hash", "review", report_id, "needs review")
    db.commit()
    assert not already_processed(db, "synthetic.pdf", "hash")

    clear_previous_import(db, "synthetic.pdf")
    assert db.execute("SELECT COUNT(*) FROM reports WHERE id = ?", (report_id,)).fetchone()[0] == 0


def test_report_notes_saved_and_kept_on_reimport(db):
    # `report_number` explícitos (no los `MANUAL-<timestamp>` de
    # `create_manual_report`, con resolución de segundo: dos llamadas
    # rápidas seguidas podrían colisionar en el mismo test) para poder
    # probar `upsert_report` de forma determinista.
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)

    report_id = upsert_report(db, patient_id, "R-NOTES-1", "2024-03-01", "2024-03-01", "(entrada manual)", notes="Control post-vacaciones")
    assert db.execute("SELECT notes FROM reports WHERE id = ?", (report_id,)).fetchone()[0] == (
        "Control post-vacaciones"
    )

    # Sin notas -> queda NULL, no cadena vacía.
    report_id_2 = upsert_report(db, patient_id, "R-NOTES-2", "2024-04-01", "2024-04-01", "(entrada manual)")
    assert db.execute("SELECT notes FROM reports WHERE id = ?", (report_id_2,)).fetchone()[0] is None

    # Reimportar (upsert_report sin pasar `notes`, como hace ingest.py) no borra la nota existente.
    assert upsert_report(db, patient_id, "R-NOTES-1", "2024-03-01", "2024-03-01", "otro.pdf") == report_id
    assert db.execute("SELECT notes FROM reports WHERE id = ?", (report_id,)).fetchone()[0] == (
        "Control post-vacaciones"
    )

    # `create_manual_report` pasa `notes` hasta `reports.notes` igual que `upsert_report` directo.
    manual_report_id = create_manual_report(
        db, patient_id, "2024-05-01",
        [{"raw_name": "Glucosa", "value_num": 100, "unit": "mg/dL", "ref_low": 70, "ref_high": 100}],
        notes="Analítica hecha en otro laboratorio",
    )
    assert db.execute("SELECT notes FROM reports WHERE id = ?", (manual_report_id,)).fetchone()[0] == (
        "Analítica hecha en otro laboratorio"
    )


def test_get_latest_report_summary(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report_row(db, patient_id, "R1", "2024-01-01", "Glucosa", "glucosa", 90, "mg/dL", 70, 100)
    _insert_report_row(db, patient_id, "R2", "2024-06-01", "Glucosa", "glucosa", 150, "mg/dL", 70, 100)
    _insert_report_row(db, patient_id, "R2", "2024-06-01", "Sodi", "sodi", 140, "mEq/L", 135, 145)

    summary = get_latest_report_summary(db, patient_id)
    assert summary["fecha"] == "2024-06-01"
    por_nombre = {r["raw_name"]: r for r in summary["resultados"]}
    assert por_nombre["Glucosa"]["value_num"] == 150
    assert por_nombre["Glucosa"]["valor_anterior"] == 90
    assert por_nombre["Glucosa"]["flag_calc"] == "alto"
    assert por_nombre["Sodi"]["valor_anterior"] is None  # sin informe anterior con sodio


def test_get_latest_report_summary_none_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_latest_report_summary(db, patient_id) is None


def test_patient_sex_and_report_file_md5_and_assistance_number(db):
    # Datos inventados.
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None, sex="Mujer")
    # Una plantilla sin sexo no borra el ya conocido.
    get_or_create_patient(db, "Test Patient", None, None, None)
    assert list_patients(db)[0]["sex"] == "Mujer"

    report_id = upsert_report(db, patient_id, "R-1", "2024-01-01", None, "a.pdf",
                              file_md5="0" * 32, assistance_number="99E000001")
    # Reimportar con otro nombre de fichero actualiza el nombre y conserva la firma.
    upsert_report(db, patient_id, "R-1", None, None, "b.pdf")
    row = db.execute(
        "SELECT source_file, file_md5, assistance_number FROM reports WHERE id = ?", (report_id,)
    ).fetchone()
    assert row == ("b.pdf", "0" * 32, "99E000001")


def test_effective_date_prefers_request_over_validation(db):
    # Sin fecha de recepción, la fecha de la analítica es la de petición,
    # no la de validación (que puede ser días posterior).
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    report_id = upsert_report(db, patient_id, "R-1", "2025-10-09", "2025-10-17", "a.pdf")
    insert_result(
        db, report_id,
        dict(section=None, test_group=None, loinc_code=None, raw_name="Glucosa", canonical_id="glucosa",
             value_raw="90", value_num=90.0, unit="mg/dL", ref_low=None, ref_high=None, ref_text=None,
             flag_pdf=None, flag_calc=None, sample_date=None),
    )
    assert get_series(db, "glucosa", patient_id)[0]["fecha"] == "2025-10-09"


def test_patient_matched_by_cip_when_name_differs(db):
    # Mismo CIP, nombre escrito distinto (p. ej. con segundo nombre): mismo paciente.
    patient_id, _ = get_or_create_patient(db, "Lopez, Ana", "1980-01-01", None, None, cip="XXXX0000000000")
    same_id, matched = get_or_create_patient(
        db, "Lopez, Ana Maria", "1980-01-01", None, None, cip="XXXX0000000000"
    )
    assert (same_id, matched) == (patient_id, "cip")
    assert list_patients(db)[0]["cip"] == "XXXX0000000000"


def test_update_patient_completes_fields_and_validates(db):
    import pytest

    from analitix.repository import merge_patients, update_patient

    patient_id, _ = get_or_create_patient(db, "Lopez, Ana", None, None, None)
    update_patient(db, patient_id, {
        "birth_date": "1980-01-01", "sex": "Mujer", "dni": " 00000000A ", "cip": "XXXX0000000000",
        "smoker_current": 0, "smoker_former": 1, "smoker_former_from": "1998", "smoker_former_to": "2010",
        "smoker_former_period": "",
    })
    p = list_patients(db)[0]
    assert (p["birth_date"], p["sex"], p["dni"], p["cip"]) == ("1980-01-01", "Mujer", "00000000A", "XXXX0000000000")
    assert (p["smoker_former"], p["smoker_former_from"], p["smoker_former_to"]) == (1, 1998, 2010)
    assert p["smoker_former_period"] is None

    # Una reimportación sin esos datos no borra lo completado a mano.
    get_or_create_patient(db, "Lopez, Ana", "1980-01-01", None, None)
    assert list_patients(db)[0]["cip"] == "XXXX0000000000"

    # Dejar de marcar "fumador anterior" limpia su periodo.
    update_patient(db, patient_id, {"smoker_former": 0})
    assert list_patients(db)[0]["smoker_former_from"] is None

    for bad in ({"birth_date": "01/01/1980"}, {"sex": "X"}, {"full_name": " "},
                {"smoker_former": 1, "smoker_former_from": "2010", "smoker_former_to": "1998"},
                {"smoker_former_from": "19"}, {"name_key": "x"}):
        with pytest.raises(ValueError):
            update_patient(db, patient_id, bad)

    # Nombre + fecha de otro paciente ya existente: error claro, no excepción de SQL.
    other_id, _ = get_or_create_patient(db, "Perez, Juan", "1970-01-01", None, None)
    with pytest.raises(ValueError, match="Fusionar"):
        update_patient(db, other_id, {"full_name": "Lopez, Ana", "birth_date": "1980-01-01"})

    # Al fusionar, el tabaquismo del origen rellena el que le falte al destino.
    update_patient(db, other_id, {"smoker_current": 1})
    update_patient(db, patient_id, {"smoker_current": None})
    merge_patients(db, [other_id], patient_id)
    assert list_patients(db)[0]["smoker_current"] == 1


def test_reimport_keeps_report_on_manually_merged_patient(db):
    # Un PDF sin fecha de nacimiento ni identificador (queda en "revisar" y
    # se reimporta siempre) fusionado a mano en otro paciente: la
    # reimportación debe respetar esa fusión, no recrear el duplicado.
    from analitix.repository import merge_patients

    target_id, _ = get_or_create_patient(db, "Lopez, Ana", "1980-01-01", None, None)
    upsert_report(db, target_id, "R-OLD", "2020-01-01", None, "old.pdf")
    phantom_id, _ = get_or_create_patient(db, "Ana Lopez Garcia", None, None, None)
    report_id = upsert_report(db, phantom_id, "R-1", "2024-01-01", None, "sin_fecha_nac.pdf")
    record_processed_file(db, "sin_fecha_nac.pdf", "hash", "review", report_id)
    merge_patients(db, [phantom_id], target_id)

    previous = clear_previous_import(db, "sin_fecha_nac.pdf")
    assert previous == target_id
    patient_id, matched = get_or_create_patient(
        db, "Ana Lopez Garcia", None, None, None, previous_patient_id=previous
    )
    assert (patient_id, matched) == (target_id, "previous")
    assert list_patients(db)[0]["full_name"] == "Lopez, Ana"  # conserva el nombre elegido


def test_current_nhc_not_repeated_as_secondary(db):
    patient_id, _ = get_or_create_patient(db, "Lopez, Ana", "1980-01-01", None, "111")
    get_or_create_patient(db, "Lopez, Ana", "1980-01-01", None, "222")  # 111 pasa a secundario
    get_or_create_patient(db, "Lopez, Ana", "1980-01-01", None, "111")  # vuelve al 111
    p = list_patients(db)[0]
    assert (p["nhc"], p["nhc_alt"]) == ("111", "222")


def test_list_patient_reports(db):
    from analitix.repository import list_patient_reports

    patient_id, _ = get_or_create_patient(db, "Lopez, Ana", "1980-01-01", None, None)
    old_id = upsert_report(db, patient_id, "R-1", "2024-01-05", "2024-01-09", "a.pdf", file_md5="a" * 32)
    new_id = upsert_report(db, patient_id, "R-2", None, "2025-03-10", "b.pdf", file_md5="b" * 32)
    for report_id, name in ((old_id, "Glucosa"), (old_id, "Urea"), (new_id, "Glucosa")):
        insert_result(db, report_id, dict(
            section=None, test_group=None, loinc_code=None, raw_name=name, canonical_id=name.lower(),
            value_raw="1", value_num=1.0, unit=None, ref_low=None, ref_high=None, ref_text=None,
            flag_pdf=None, flag_calc=None, sample_date="2024-01-04 08:00:00" if report_id == old_id else None,
        ))
    rows = list_patient_reports(db, patient_id)
    # Más reciente primero; fecha = recepción de la muestra si la hay, si no petición/validación.
    assert [(r["source_file"], r["fecha"][:10], r["num_results"], r["file_md5"]) for r in rows] == [
        ("b.pdf", "2025-03-10", 1, "b" * 32),
        ("a.pdf", "2024-01-04", 2, "a" * 32),
    ]


def test_lab_is_stored_and_reaches_series(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    report_id = upsert_report(db, patient_id, "R-1", "2024-01-01", None, "a.pdf", lab="HUGTIP")
    insert_result(db, report_id, dict(
        section=None, test_group=None, loinc_code=None, raw_name="Glucosa", canonical_id="glucosa",
        value_raw="90", value_num=90.0, unit="mg/dL", ref_low=None, ref_high=None, ref_text=None,
        flag_pdf=None, flag_calc=None, sample_date=None,
    ))
    create_manual_report(db, patient_id, "2024-02-01", [{"raw_name": "Glucosa", "value_num": 95, "unit": "mg/dL"}])
    assert [s["lab"] for s in get_series(db, "glucosa", patient_id)] == ["HUGTIP", "Entrada manual"]


def _add_rows(con, patient_id, report_number, lab, rows):
    """Informe sintético con varias filas `(raw_name, canonical_id, loinc, unit)`."""
    report_id = upsert_report(con, patient_id, report_number, "2024-01-01", "2024-01-01", "synthetic.pdf", lab=lab)
    for raw_name, canonical_id, loinc, unit in rows:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=loinc, raw_name=raw_name, canonical_id=canonical_id,
                 value_raw="1", value_num=1.0, unit=unit, ref_low=None, ref_high=None, ref_text=None,
                 flag_pdf=None, flag_calc=None, sample_date=None),
        )
    con.commit()


def test_merge_check_blocks_tests_measured_in_the_same_report(db):
    pid, _ = get_or_create_patient(db, full_name="PACIENTE FICTICIO", birth_date="1980-01-01", dni=None, nhc=None)
    _add_rows(db, pid, "1", "Lab A", [
        ("Glucosa sèrum", "glucosa_serum", "2345-7", "mg/dL"),
        ("Glucosa", "glucosa_orina", "50555-2", None),
    ])
    blocked, _ = merge_check(db, ["glucosa_serum", "glucosa_orina"])
    assert len(blocked) == 1 and "1 informe" in blocked[0]
    with pytest.raises(MergeBlockedError):
        merge_canonical_ids(db, ["glucosa_orina"], "glucosa_serum")
    assert db.execute("SELECT COUNT(*) FROM results WHERE canonical_id = 'glucosa_serum'").fetchone()[0] == 1


def test_merge_check_allows_same_lab_renames_and_duplicated_rows(db):
    pid, _ = get_or_create_patient(db, full_name="PACIENTE FICTICIO", birth_date="1980-01-01", dni=None, nhc=None)
    # Mismo laboratorio, nombre cambiado entre plantillas, nunca juntos.
    _add_rows(db, pid, "1", "Lab A", [("Ferritina", "ferritina", None, "ng/ml")])
    _add_rows(db, pid, "2", "Lab A", [("Ferritina sèrum", "ferritina_serum", None, "ng/mL")])
    # Mismo dato repetido en un informe con el mismo LOINC.
    _add_rows(db, pid, "3", "Lab A", [
        ("Colesterol HDL", "colesterol_hdl_a", "2085-9", "mg/dL"),
        ("Colesterol HDL sèrum", "colesterol_hdl_b", "2085-9", "mg/dL"),
    ])
    assert merge_check(db, ["ferritina", "ferritina_serum"]) == ([], [])
    assert merge_check(db, ["colesterol_hdl_a", "colesterol_hdl_b"]) == ([], [])
    assert merge_canonical_ids(db, ["ferritina"], "ferritina_serum") == 1


def test_merge_check_warns_on_different_loinc_or_units(db):
    pid, _ = get_or_create_patient(db, full_name="PACIENTE FICTICIO", birth_date="1980-01-01", dni=None, nhc=None)
    _add_rows(db, pid, "1", "Lab A", [("Hematies", "hematies_a", "789-8", "x10^6/ul")])
    _add_rows(db, pid, "2", "Lab B", [("Hematíes", "hematies_b", "32776-7", "x10^6/ul")])
    _add_rows(db, pid, "3", "Lab A", [("Albúmina", "albumina_a", None, "g/dL")])
    _add_rows(db, pid, "4", "Lab B", [("Albúmina", "albumina_b", None, "g/L")])
    blocked, warnings = merge_check(db, ["hematies_a", "hematies_b"])
    assert not blocked and len(warnings) == 1 and "LOINC" in warnings[0]
    blocked, warnings = merge_check(db, ["albumina_a", "albumina_b"])
    assert not blocked and len(warnings) == 1 and "unidades" in warnings[0]


def test_list_canonical_groups_reports_labs(db):
    pid, _ = get_or_create_patient(db, full_name="PACIENTE FICTICIO", birth_date="1980-01-01", dni=None, nhc=None)
    _add_rows(db, pid, "1", "Lab A", [("Urea", "urea", None, "mg/dL")])
    _add_rows(db, pid, "2", "Lab B", [("Urea sèrum", "urea", None, "mg/dL")])
    (group,) = list_canonical_groups(db)
    assert group["labs"] == ["Lab A", "Lab B"]
    assert group["variants"] == [("Urea", "Lab A", 1), ("Urea sèrum", "Lab B", 1)]


def test_lab_filter_applies_to_series_summary_and_test_list(db):
    from analitix.repository import get_excluded_labs, list_canonical_tests, list_labs, set_excluded_labs

    pid, _ = get_or_create_patient(db, full_name="PACIENTE FICTICIO", birth_date="1980-01-01", dni=None, nhc=None)
    for numero, fecha, lab, valor in (("1", "2024-01-01", "Lab A", 90.0), ("2", "2024-06-01", "Lab B", 95.0),
                                      ("3", "2025-01-01", None, 99.0)):
        report_id = upsert_report(db, pid, numero, fecha, fecha, "synthetic.pdf", lab=lab)
        insert_result(db, report_id, dict(
            section=None, test_group=None, loinc_code=None, raw_name="Glucosa", canonical_id="glucosa",
            value_raw=str(valor), value_num=valor, unit="mg/dL", ref_low=70.0, ref_high=110.0, ref_text=None,
            flag_pdf=None, flag_calc="normal", sample_date=None))
    db.commit()
    assert [l["lab"] for l in list_labs(db)] == ["", "Lab A", "Lab B"]  # "" = laboratorio desconocido

    assert len(get_series(db, "glucosa", pid)) == 3  # sin filtro: todo
    set_excluded_labs(db, ["Lab A", ""])
    assert get_excluded_labs(db) == {"Lab A", ""}
    assert [s["value_num"] for s in get_series(db, "glucosa", pid)] == [95.0]
    summary = get_latest_report_summary(db, pid)
    assert summary["fecha"].startswith("2024-06-01")  # el último de los laboratorios incluidos
    assert summary["resultados"][0]["valor_anterior"] is None
    assert list_canonical_tests(db, pid)[0]["num_points"] == 1

    db.rollback()  # un rollback de otra operación no deshace el filtro
    assert get_excluded_labs(db) == {"Lab A", ""}
    set_excluded_labs(db, [])
    assert len(get_series(db, "glucosa", pid)) == 3
