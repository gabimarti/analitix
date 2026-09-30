import pytest

from analitix.pdf_parser import compute_flag
from analitix.glycemic_risk import (
    ADA_DIABETES_LOW,
    ADA_NORMAL_HIGH,
    _mg_dl,
    _pct,
    eag,
    get_glucose_series,
    get_glycemic_index_series,
    get_latest_glycemic_summary,
    hba1c_category,
)
from analitix.repository import get_or_create_patient, insert_result, upsert_report


def test_unit_guard():
    assert _pct({"value_num": 6.0, "unit": "%"}) == 6.0
    assert _pct({"value_num": 6.0, "unit": "mmol/mol"}) is None  # variante IFCC, sin conversión
    assert _pct(None) is None


def test_eag():
    assert eag(6.0) == pytest.approx(28.7 * 6.0 - 46.7)
    assert eag(None) is None


@pytest.mark.parametrize(
    ("hba1c", "expected"),
    [
        (5.0, "normal"),
        (ADA_NORMAL_HIGH, "prediabetes"),
        (6.0, "prediabetes"),
        (ADA_DIABETES_LOW, "diabetes"),
        (None, None),
    ],
)
def test_hba1c_category(hba1c, expected):
    assert hba1c_category(hba1c) == expected


def _insert_report(
    con, patient_id, report_number, fecha, hba1c=None, hba1c_cid="hb_glicosilada_hba1c_sang", unit="%",
    glucosa=None,
):
    report_id = upsert_report(con, patient_id, report_number, fecha, None, "synthetic.pdf")
    if hba1c is not None:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name="HbA1c",
                 canonical_id=hba1c_cid, value_raw=str(hba1c), value_num=hba1c, unit=unit,
                 ref_low=None, ref_high=None, ref_text=None, flag_pdf=None, flag_calc=None,
                 sample_date=None),
        )
    if glucosa is not None:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name="Glucosa",
                 canonical_id="glucosa_serum", value_raw=str(glucosa), value_num=glucosa, unit="mg/dl",
                 ref_low=70, ref_high=100, ref_text=None, flag_pdf=None,
                 flag_calc=compute_flag(glucosa, 70, 100), sample_date=None),
        )
    con.commit()


def test_glucose_unit_guard():
    assert _mg_dl({"value_num": 90.0, "unit": "mg/dl"}) == 90.0
    assert _mg_dl({"value_num": 90.0, "unit": "mg/L"}) is None


def test_glucose_series(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", glucosa=95.0)
    _insert_report(db, patient_id, "R2", "2024-06-01", hba1c=7.0, glucosa=180.0)
    series = get_glucose_series(db, patient_id)
    assert len(series) == 2
    assert series[1]["value_num"] == 180.0
    assert series[1]["flag_calc"] == "alto"


def test_glucose_series_empty_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_glucose_series(db, patient_id) == []


def test_series_and_high_flag(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", hba1c=5.0)
    _insert_report(db, patient_id, "R2", "2024-06-01", hba1c=7.0)
    series = get_glycemic_index_series(db, patient_id)
    points = series["idx_eag"]
    assert len(points) == 2
    assert points[0]["flag_calc"] == "normal"
    assert points[1]["flag_calc"] == "alto"
    assert points[1]["value_num"] == pytest.approx(28.7 * 7.0 - 46.7)


def test_series_ignores_ifcc_unit(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(
        db, patient_id, "R1", "2024-01-01", hba1c=48.0,
        hba1c_cid="hb_glicosilada_hba1c_ifcc_sang", unit="mmol/mol",
    )
    assert get_glycemic_index_series(db, patient_id) == {}


def test_series_empty_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_glycemic_index_series(db, patient_id) == {}


def test_latest_summary(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", hba1c=5.0)
    _insert_report(db, patient_id, "R2", "2024-06-01", hba1c=7.0)
    summary = get_latest_glycemic_summary(db, patient_id)
    assert summary["fecha"] == "2024-06-01"
    assert summary["hba1c"] == 7.0
    assert summary["categoria"] == "diabetes"
    assert summary["eag"] == pytest.approx(28.7 * 7.0 - 46.7)


def test_latest_summary_none_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_latest_glycemic_summary(db, patient_id) is None
