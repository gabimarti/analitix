import pytest

from analitix.lipid_risk import (
    _mg_dl,
    castelli_1,
    castelli_2,
    get_lipid_index_series,
    ldl_friedewald,
    tg_hdl_ratio,
)
from analitix.repository import get_or_create_patient, insert_result, upsert_report


@pytest.mark.parametrize(
    ("total", "hdl", "tg", "expected"),
    [(200, 50, 150, 120.0), (200, 50, 400, None), (None, 50, 100, None)],
)
def test_lipid_formulas(total, hdl, tg, expected):
    assert ldl_friedewald(total, hdl, tg) == expected
    assert castelli_1(total, hdl) == (total / hdl if total is not None else None)
    assert castelli_2(total, hdl) == (total / hdl if total is not None else None)
    assert tg_hdl_ratio(tg, hdl) == (tg / hdl if tg is not None else None)


def test_mg_dl_rejects_other_units():
    assert _mg_dl({"value_num": 10, "unit": "mg/dL"}) == 10
    assert _mg_dl({"value_num": 10, "unit": "mmol/L"}) is None
    assert _mg_dl(None) is None


def test_lipid_series_uses_measured_or_friedewald_ldl(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", "1980-01-01", None, None)
    report_id = upsert_report(db, patient_id, "R1", "2024-01-01", None, "synthetic.pdf")
    values = [
        ("Colesterol", "colesterol", 200),
        ("HDL", "colesterol_hdl", 50),
        ("TG", "triglicerids", 150),
    ]
    for raw_name, canonical_id, value in values:
        insert_result(
            db,
            report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name=raw_name,
                 canonical_id=canonical_id, value_raw=str(value), value_num=value,
                 unit="mg/dL", ref_low=None, ref_high=None, ref_text=None,
                 flag_pdf=None, flag_calc=None, sample_date=None),
        )
    db.commit()
    series = get_lipid_index_series(db, patient_id)
    assert series["idx_ldl_estimado"][0]["value_num"] == 120
    assert series["idx_castelli1"][0]["value_num"] == 4
