import pytest

from analitix.inflammation_risk import (
    _mg_dl,
    _mm_h,
    get_inflammation_series,
    get_latest_inflammation_summary,
)
from analitix.repository import get_or_create_patient, insert_result, upsert_report


def test_unit_guards():
    assert _mg_dl({"value_num": 5, "unit": "mg/dl"}) == 5
    assert _mg_dl({"value_num": 5, "unit": "mg/dL"}) == 5
    assert _mg_dl({"value_num": 5, "unit": "mg/L"}) is None
    assert _mm_h({"value_num": 20, "unit": "mm/h"}) == 20
    assert _mm_h({"value_num": 20, "unit": "mg/dl"}) is None


def _insert_report(
    con, patient_id, report_number, fecha,
    pcr=None, pcr_cid="proteina_c_reactiva_serum", pcr_ref=(None, None),
    vsg=None, vsg_cid="vsg_velocitat_de_sedimentacio_globular", vsg_ref=(None, None),
):
    report_id = upsert_report(con, patient_id, report_number, fecha, None, "synthetic.pdf")
    values = []
    if pcr is not None:
        values.append(("PCR", pcr_cid, pcr, "mg/dl", *pcr_ref))
    if vsg is not None:
        values.append(("VSG", vsg_cid, vsg, "mm/h", *vsg_ref))
    for raw_name, cid, value, unit, ref_low, ref_high in values:
        flag = None
        if ref_low is not None and value < ref_low:
            flag = "bajo"
        elif ref_high is not None and value > ref_high:
            flag = "alto"
        elif ref_low is not None or ref_high is not None:
            flag = "normal"
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name=raw_name,
                 canonical_id=cid, value_raw=str(value), value_num=value, unit=unit,
                 ref_low=ref_low, ref_high=ref_high, ref_text=None, flag_pdf=None, flag_calc=flag,
                 sample_date=None),
        )
    con.commit()


def test_pcr_vsg_spelling_variants_are_merged(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2023-01-01", pcr=0.5, pcr_cid="proteina_c_reactiva")
    _insert_report(db, patient_id, "R2", "2024-01-01", vsg=10, vsg_cid="vsg_velocitat_de_sedimentacio_globular_sang")
    series = get_inflammation_series(db, patient_id)
    assert len(series["pcr"]) == 1
    assert len(series["vsg"]) == 1


def test_latest_summary_no_discordance(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", pcr=0.3, pcr_ref=(0, 0.5), vsg=10, vsg_ref=(0, 20))
    summary = get_latest_inflammation_summary(db, patient_id)
    assert summary["pcr"]["value_num"] == 0.3
    assert summary["vsg"]["value_num"] == 10
    assert summary["discordancia"] is None


def test_latest_summary_detects_discordance(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", pcr=5.0, pcr_ref=(0, 0.5), vsg=10, vsg_ref=(0, 20))
    summary = get_latest_inflammation_summary(db, patient_id)
    assert summary["discordancia"] is not None
    assert "PCR fuera de rango" in summary["discordancia"]


def test_latest_summary_none_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_latest_inflammation_summary(db, patient_id) is None


def test_latest_summary_only_one_parameter(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_report(db, patient_id, "R1", "2024-01-01", pcr=0.3, pcr_ref=(0, 0.5))
    summary = get_latest_inflammation_summary(db, patient_id)
    assert summary["pcr"] is not None
    assert summary["vsg"] is None
    assert summary["discordancia"] is None


def test_pcr_in_mg_l_is_converted_to_mg_dl():
    from analitix.inflammation_risk import _as_mg_dl

    row = {"value_num": 12.0, "unit": "mg/L", "ref_low": None, "ref_high": 5.0, "flag_calc": "alto"}
    converted = _as_mg_dl(row)
    assert (converted["value_num"], converted["ref_high"], converted["unit"], converted["flag_calc"]) == (
        1.2, 0.5, "mg/dL", "alto"
    )
    assert row["value_num"] == 12.0  # no modifica la fila original
    assert _as_mg_dl({"value_num": 0.3, "unit": "mg/dL"})["value_num"] == 0.3
    assert _as_mg_dl({"value_num": 1.0, "unit": "mmol/L"}) is None
