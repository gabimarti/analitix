from analitix.pdf_parser import compute_flag
from analitix.thyroid_risk import _ng_dl, _uui_ml, get_latest_thyroid_summary, get_thyroid_series
from analitix.repository import get_or_create_patient, insert_result, upsert_report


def test_unit_guards():
    assert _uui_ml({"value_num": 2.0, "unit": "mcUI/mL"}) == 2.0
    assert _uui_ml({"value_num": 2.0, "unit": "mcIU/mL"}) == 2.0  # orden de letras distinto, mismo valor
    # 1 mU/L = 1 µUI/mL exactamente (10^-3 UI / 10^3 mL); Synlab usa mU/L.
    assert _uui_ml({"value_num": 2.0, "unit": "mUI/L"}) == 2.0
    assert _uui_ml({"value_num": 2.0, "unit": "pmol/L"}) is None
    assert _ng_dl({"value_num": 1.2, "unit": "ng/dL"}) == 1.2
    assert _ng_dl({"value_num": 1.2, "unit": "pmol/L"}) is None


def _insert_report(con, patient_id, report_number, fecha, tsh=None, t4l=None):
    report_id = upsert_report(con, patient_id, report_number, fecha, None, "synthetic.pdf")
    if tsh is not None:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name="TSH",
                 canonical_id="tirotropina_tsh_serum", value_raw=str(tsh), value_num=tsh, unit="mcUI/mL",
                 ref_low=0.4, ref_high=4.0, ref_text=None, flag_pdf=None,
                 flag_calc=compute_flag(tsh, 0.4, 4.0), sample_date=None),
        )
    if t4l is not None:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name="T4L",
                 canonical_id="tiroxina_lliure_t4l", value_raw=str(t4l), value_num=t4l, unit="ng/dL",
                 ref_low=0.7, ref_high=1.8, ref_text=None, flag_pdf=None,
                 flag_calc=compute_flag(t4l, 0.7, 1.8), sample_date=None),
        )
    con.commit()


def test_series_classifies_against_report_range(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", tsh=6.0, t4l=0.5)
    series = get_thyroid_series(db, patient_id)
    assert series["tsh"][0]["flag_calc"] == "alto"
    assert series["t4l"][0]["flag_calc"] == "bajo"


def test_series_empty_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_thyroid_series(db, patient_id) == {}


def test_latest_summary(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", tsh=2.0, t4l=1.0)
    summary = get_latest_thyroid_summary(db, patient_id)
    assert summary["tsh"]["value_num"] == 2.0
    assert summary["t4l"]["value_num"] == 1.0


def test_latest_summary_none_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_latest_thyroid_summary(db, patient_id) is None
