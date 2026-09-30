import pytest

from analitix.calcium_risk import (
    _g_dl,
    _mg_dl,
    corrected_calcium,
    get_calcium_index_series,
    get_latest_calcium_summary,
)
from analitix.repository import get_or_create_patient, insert_result, upsert_report


def test_unit_guards():
    assert _mg_dl({"value_num": 9.0, "unit": "mg/dl"}) == 9.0
    assert _mg_dl({"value_num": 9.0, "unit": "mg/L"}) is None
    assert _g_dl({"value_num": 4.0, "unit": "g/dL"}) == 4.0
    assert _g_dl({"value_num": 4.0, "unit": "%"}) is None  # fracción del proteinograma, no sirve


def test_corrected_calcium():
    # Ca 8.0 con albumina baja (2.0): corregido = 8.0 + 0.8*(4.0-2.0) = 9.6
    assert corrected_calcium(8.0, 2.0) == pytest.approx(9.6)
    assert corrected_calcium(None, 2.0) is None
    assert corrected_calcium(8.0, None) is None


def _insert_report(con, patient_id, report_number, fecha, calci=None, albumina=None, ref_low=8.5, ref_high=10.5):
    report_id = upsert_report(con, patient_id, report_number, fecha, None, "synthetic.pdf")
    if calci is not None:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name="Calci",
                 canonical_id="calci_serum", value_raw=str(calci), value_num=calci, unit="mg/dl",
                 ref_low=ref_low, ref_high=ref_high, ref_text=None, flag_pdf=None, flag_calc=None,
                 sample_date=None),
        )
    if albumina is not None:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name="Albumina",
                 canonical_id="albumina_serum", value_raw=str(albumina), value_num=albumina, unit="g/dl",
                 ref_low=None, ref_high=None, ref_text=None, flag_pdf=None, flag_calc=None,
                 sample_date=None),
        )
    con.commit()


def test_series_only_on_dates_with_both_values(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", calci=8.0)  # sin albumina ese dia
    _insert_report(db, patient_id, "R2", "2024-06-01", calci=8.0, albumina=2.0)
    series = get_calcium_index_series(db, patient_id)
    points = series["idx_calcio_corregido"]
    assert len(points) == 1
    assert points[0]["fecha"] == "2024-06-01"
    assert points[0]["value_num"] == pytest.approx(9.6)


def test_series_reuses_lab_reference_range(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", calci=8.0, albumina=2.0, ref_low=8.5, ref_high=10.5)
    series = get_calcium_index_series(db, patient_id)
    point = series["idx_calcio_corregido"][0]
    assert point["ref_low"] == 8.5
    assert point["ref_high"] == 10.5
    assert point["flag_calc"] == "normal"  # 9.6 esta dentro de 8.5-10.5


def test_series_empty_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_calcium_index_series(db, patient_id) == {}


def test_latest_summary(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-06-01", calci=8.0, albumina=2.0)
    summary = get_latest_calcium_summary(db, patient_id)
    assert summary["fecha"] == "2024-06-01"
    assert summary["calcio_medido"] == 8.0
    assert summary["albumina"] == 2.0
    assert summary["calcio_corregido"] == pytest.approx(9.6)


def test_latest_summary_none_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_latest_calcium_summary(db, patient_id) is None


def test_albumin_in_g_l_is_converted_to_g_dl():
    from analitix.calcium_risk import _g_dl

    assert _g_dl({"value_num": 39.0, "unit": "g/L"}) == 3.9
    assert _g_dl({"value_num": 3.9, "unit": "g/dL"}) == 3.9
    assert _g_dl({"value_num": 60.0, "unit": "%"}) is None
