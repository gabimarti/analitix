import pytest

from analitix.uric_acid_risk import (
    HYPERURICEMIA_HIGH,
    _mg_dl,
    get_latest_uric_acid_summary,
    get_uric_acid_series,
)
from analitix.repository import get_or_create_patient, insert_result, upsert_report


def test_unit_guard():
    assert _mg_dl({"value_num": 7.0, "unit": "mg/dl"}) == 7.0
    assert _mg_dl({"value_num": 7.0, "unit": "mg/dL"}) == 7.0
    assert _mg_dl({"value_num": 7.0, "unit": "mg/L"}) is None
    assert _mg_dl(None) is None


def _insert_report(con, patient_id, report_number, fecha, urat=None, urat_cid="urat_serum"):
    report_id = upsert_report(con, patient_id, report_number, fecha, None, "synthetic.pdf")
    if urat is not None:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name="Urat",
                 canonical_id=urat_cid, value_raw=str(urat), value_num=urat, unit="mg/dl",
                 ref_low=None, ref_high=None, ref_text=None, flag_pdf=None, flag_calc=None,
                 sample_date=None),
        )
    con.commit()


def test_series_classifies_high(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", urat=5.0)
    _insert_report(db, patient_id, "R2", "2024-06-01", urat=7.5)
    series = get_uric_acid_series(db, patient_id)
    points = series["idx_acido_urico"]
    assert len(points) == 2
    assert points[0]["flag_calc"] == "normal"
    assert points[1]["flag_calc"] == "alto"
    assert points[1]["value_num"] == 7.5


def test_series_empty_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_uric_acid_series(db, patient_id) == {}


def test_boundary_value_is_not_flagged_high(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", urat=HYPERURICEMIA_HIGH)
    series = get_uric_acid_series(db, patient_id)
    assert series["idx_acido_urico"][0]["flag_calc"] == "normal"


def test_latest_summary(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", urat=5.0)
    _insert_report(db, patient_id, "R2", "2024-06-01", urat=7.5)
    summary = get_latest_uric_acid_summary(db, patient_id)
    assert summary["fecha"] == "2024-06-01"
    assert summary["value"] == 7.5
    assert summary["flag"] == "alto"


def test_latest_summary_none_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_latest_uric_acid_summary(db, patient_id) is None
