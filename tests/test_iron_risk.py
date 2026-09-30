import pytest

from analitix.iron_risk import (
    _mcg_dl,
    _mg_dl,
    _ng_ml,
    _percent,
    get_iron_index_series,
    get_latest_iron_summary,
    tsat_from_iron_transferrin,
)
from analitix.repository import get_or_create_patient, insert_result, upsert_report


def test_tsat_from_iron_transferrin():
    # 79.6 ug/dL / (369 mg/dL * 1.42) * 100 ~= 15.16% -- valores de un
    # informe real (2014, sin TSAT calculada por el laboratorio ese día).
    assert tsat_from_iron_transferrin(79.6, 369.0) == pytest.approx(15.16, rel=1e-2)
    assert tsat_from_iron_transferrin(None, 369.0) is None
    assert tsat_from_iron_transferrin(79.6, 0) is None


def test_unit_guards():
    assert _mcg_dl({"value_num": 80, "unit": "mcg/dl"}) == 80
    assert _mcg_dl({"value_num": 80, "unit": "mcg/dL"}) == 80
    assert _mcg_dl({"value_num": 80, "unit": "mg/dl"}) is None
    assert _ng_ml({"value_num": 30, "unit": "ng/mL"}) == 30
    assert _ng_ml({"value_num": 30, "unit": "ng/ml"}) == 30
    assert _ng_ml({"value_num": 30, "unit": "mcg/dl"}) is None
    assert _mg_dl({"value_num": 300, "unit": "mg/dl"}) == 300
    assert _mg_dl({"value_num": 300, "unit": "ng/ml"}) is None
    assert _percent({"value_num": 25, "unit": "%"}) == 25
    assert _percent({"value_num": 25, "unit": "mg/dl"}) is None


def _insert_iron_report(
    con, patient_id, report_number, fecha,
    ferro=None, ferro_cid="ferro_serum",
    ferritina=None, ferritina_cid="ferritina_serum",
    transferrina=None, transferrina_cid="transferrina_serum",
    tsat=None, tsat_cid="saturacio_transferrina_serum",
):
    report_id = upsert_report(con, patient_id, report_number, fecha, None, "synthetic.pdf")
    values = []
    if ferro is not None:
        values.append(("Ferro", ferro_cid, ferro, "mcg/dl"))
    if ferritina is not None:
        values.append(("Ferritina", ferritina_cid, ferritina, "ng/ml"))
    if transferrina is not None:
        values.append(("Transferrina", transferrina_cid, transferrina, "mg/dl"))
    if tsat is not None:
        values.append(("Saturacio transferrina", tsat_cid, tsat, "%"))
    for raw_name, cid, value, unit in values:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name=raw_name,
                 canonical_id=cid, value_raw=str(value), value_num=value, unit=unit,
                 ref_low=None, ref_high=None, ref_text=None, flag_pdf=None, flag_calc=None, sample_date=None),
        )
    con.commit()


def test_ferro_ferritina_transferrina_spelling_variants_are_merged(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_iron_report(
        db, patient_id, "R1", "2014-01-01",
        ferro=31.3, ferro_cid="ferro", ferritina=8.2, ferritina_cid="ferritina",
        transferrina=427.0, transferrina_cid="transferrina",
    )
    _insert_iron_report(
        db, patient_id, "R2", "2024-01-01",
        ferro=80.0, ferro_cid="ferro_serum", ferritina=34.0, ferritina_cid="ferritina_serum",
        transferrina=250.0, transferrina_cid="transferrina_serum", tsat=25.0,
    )
    series = get_iron_index_series(db, patient_id)
    assert len(series["idx_ferritina"]) == 2
    assert series["idx_ferritina"][0]["value_num"] == 8.2
    assert series["idx_ferritina"][1]["value_num"] == 34.0
    # 2014-01-01 no trae TSAT del laboratorio: se calcula con hierro/transferrina.
    assert len(series["idx_tsat"]) == 2
    assert series["idx_tsat"][0]["value_num"] == pytest.approx(
        tsat_from_iron_transferrin(31.3, 427.0), rel=1e-6
    )
    assert series["idx_tsat"][1]["value_num"] == 25.0


def test_latest_iron_summary_flags(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_iron_report(
        db, patient_id, "R1", "2024-01-01",
        ferro=31.3, ferritina=8.0, transferrina=427.0, tsat=15.0,
    )
    summary = get_latest_iron_summary(db, patient_id)
    assert summary["fecha"] == "2024-01-01"
    assert summary["ferritina"] == 8.0
    assert summary["ferritina_flag"] == "bajo"
    assert summary["tsat"] == 15.0
    assert summary["tsat_flag"] == "bajo"
    assert summary["tsat_estimado"] is False


def test_latest_iron_summary_estimates_tsat_when_missing(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_iron_report(db, patient_id, "R1", "2024-01-01", ferro=79.6, transferrina=369.0)
    summary = get_latest_iron_summary(db, patient_id)
    assert summary["tsat_estimado"] is True
    assert summary["tsat"] == pytest.approx(tsat_from_iron_transferrin(79.6, 369.0), rel=1e-6)


def test_latest_iron_summary_none_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_latest_iron_summary(db, patient_id) is None
