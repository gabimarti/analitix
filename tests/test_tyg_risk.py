import math

import pytest

from analitix.repository import get_or_create_patient, insert_result, upsert_report
from analitix.tyg_risk import get_tyg_series, tyg


def test_tyg_formula():
    # ln(150 × 90 / 2) = ln(6750) ≈ 8.82
    assert tyg(150, 90) == pytest.approx(math.log(6750))
    assert round(tyg(150, 90), 2) == 8.82
    assert tyg(None, 90) is None
    assert tyg(0, 90) is None


def _insert(con, patient_id, number, fecha, tg=None, glucosa=None, unit="mg/dL"):
    report_id = upsert_report(con, patient_id, number, fecha, None, "synthetic.pdf", lab="Lab A")
    for canonical_id, valor in (("triglicerids_serum", tg), ("glucosa_serum", glucosa)):
        if valor is not None:
            insert_result(con, report_id, dict(
                section=None, test_group=None, loinc_code=None, raw_name=canonical_id, canonical_id=canonical_id,
                value_raw=str(valor), value_num=valor, unit=unit, ref_low=None, ref_high=None, ref_text=None,
                flag_pdf=None, flag_calc=None, sample_date=None))
    con.commit()


def test_tyg_series_needs_both_values_same_report_in_mg_dl(db):
    pid, _ = get_or_create_patient(db, "PACIENTE FICTICIO", None, None, None)
    _insert(db, pid, "R1", "2024-01-01", tg=150, glucosa=90)
    _insert(db, pid, "R2", "2024-06-01", tg=200)  # sin glucosa: no hay punto
    _insert(db, pid, "R3", "2025-01-01", tg=1.7, glucosa=5.0, unit="mmol/L")  # otra unidad: se descarta
    (serie,) = get_tyg_series(db, pid).values()
    assert [(p["fecha"][:10], p["value_num"]) for p in serie] == [("2024-01-01", 8.82)]
    assert serie[0]["ref_high"] is None and serie[0]["flag_calc"] is None  # sin umbral, solo tendencia
    assert serie[0]["lab"] == "Lab A"


def test_tyg_series_empty_without_data(db):
    pid, _ = get_or_create_patient(db, "PACIENTE FICTICIO", None, None, None)
    assert get_tyg_series(db, pid) == {}
