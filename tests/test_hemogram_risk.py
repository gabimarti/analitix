import pytest

from analitix.hemogram_risk import (
    _fl,
    _percent,
    _x10e3_ul,
    _x10e6_ul,
    get_hemogram_index_series,
    get_latest_hemogram_summary,
    get_sustained_lymphocytosis_alert,
    lmr,
    mentzer_index,
    nlr,
    plr,
    vcm_category,
)
from analitix.repository import get_or_create_patient, insert_result, upsert_report


@pytest.mark.parametrize(
    ("neutrofils", "limfocits", "expected"),
    [(6.0, 2.0, 3.0), (None, 2.0, None), (6.0, 0, None)],
)
def test_nlr(neutrofils, limfocits, expected):
    assert nlr(neutrofils, limfocits) == expected


def test_plr():
    assert plr(300.0, 2.0) == 150.0
    assert plr(300.0, None) is None


def test_lmr():
    assert lmr(2.0, 0.5) == 4.0
    assert lmr(2.0, 0) is None


def test_mentzer_index():
    # VCM 70 fL / 4.5 millones/uL ~= 15.56 -> sugiere ferropenia, no talasemia.
    assert mentzer_index(70.0, 4.5) == pytest.approx(15.556, rel=1e-3)
    assert mentzer_index(None, 4.5) is None


@pytest.mark.parametrize(
    ("vcm", "expected"),
    [(79.9, "microcitica"), (80.0, "normocitica"), (100.0, "normocitica"),
     (100.1, "macrocitica"), (None, None)],
)
def test_vcm_category(vcm, expected):
    assert vcm_category(vcm) == expected


def test_unit_guards():
    assert _x10e3_ul({"value_num": 5, "unit": "x10^3/ul"}) == 5
    assert _x10e3_ul({"value_num": 5, "unit": "x10^3_u/mc"}) == 5  # sufijo truncado real
    assert _x10e3_ul({"value_num": 5, "unit": "x10^6/ul"}) is None
    assert _x10e6_ul({"value_num": 4.5, "unit": "x10^6/ul"}) == 4.5
    assert _x10e6_ul({"value_num": 4.5, "unit": "x10^3/ul"}) is None
    assert _fl({"value_num": 90, "unit": "fL"}) == 90
    assert _fl({"value_num": 90, "unit": "pg"}) is None
    assert _percent({"value_num": 14, "unit": "%"}) == 14
    assert _percent({"value_num": 14, "unit": "fL"}) is None


def _insert_hemogram_report(
    con, patient_id, report_number, fecha, vcm=None, hematies=None, rdw=None,
    neutrofils=None, limfocits=None, limfocits_cid="limfocits_total", monocits=None, plaquetes=None,
):
    report_id = upsert_report(con, patient_id, report_number, fecha, None, "synthetic.pdf")
    values = []
    if vcm is not None:
        values.append(("VCM", "vcm", vcm, "fL"))
    if hematies is not None:
        values.append(("Hematies", "hematies", hematies, "x10^6/ul"))
    if rdw is not None:
        values.append(("RDW-CV", "rdw_cv", rdw, "%"))
    if neutrofils is not None:
        values.append(("Neutrofils total", "neutrofils_total", neutrofils, "x10^3/ul"))
    if limfocits is not None:
        values.append(("Limfocits total", limfocits_cid, limfocits, "x10^3/ul"))
    if monocits is not None:
        values.append(("Monocits total", "monocits_total", monocits, "x10^3/ul"))
    if plaquetes is not None:
        values.append(("Plaquetes", "plaquetes", plaquetes, "x10^3/ul"))
    for raw_name, cid, value, unit in values:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name=raw_name,
                 canonical_id=cid, value_raw=str(value), value_num=value, unit=unit,
                 ref_low=None, ref_high=None, ref_text=None, flag_pdf=None, flag_calc=None, sample_date=None),
        )
    con.commit()


def test_limfocits_spelling_variants_are_merged(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_hemogram_report(
        db, patient_id, "R1", "2023-01-01", vcm=90, neutrofils=6.0, limfocits=2.0, limfocits_cid="limfocits_total",
    )
    _insert_hemogram_report(
        db, patient_id, "R2", "2024-01-01", vcm=90, neutrofils=6.0, limfocits=3.0, limfocits_cid="linfocits_total",
    )
    series = get_hemogram_index_series(db, patient_id)
    assert len(series["idx_nlr"]) == 2
    assert series["idx_nlr"][0]["value_num"] == 3.0  # 6/2
    assert series["idx_nlr"][1]["value_num"] == 2.0  # 6/3


def test_mentzer_only_appears_when_microcytic(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_hemogram_report(db, patient_id, "R1", "2023-01-01", vcm=90, hematies=4.5)  # normocitico
    _insert_hemogram_report(db, patient_id, "R2", "2024-01-01", vcm=70, hematies=4.5)  # microcitico

    series = get_hemogram_index_series(db, patient_id)
    assert len(series["idx_mentzer"]) == 1
    assert series["idx_mentzer"][0]["fecha"] == "2024-01-01"


def test_latest_hemogram_summary(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_hemogram_report(
        db, patient_id, "R1", "2024-01-01", vcm=70, hematies=4.5, rdw=16.0,
        neutrofils=6.0, limfocits=2.0, monocits=0.5, plaquetes=300,
    )
    summary = get_latest_hemogram_summary(db, patient_id)
    assert summary["fecha"] == "2024-01-01"
    assert summary["vcm_categoria"] == "microcitica"
    assert summary["nlr"] == 3.0
    assert summary["plr"] == 150.0
    assert summary["lmr"] == 4.0
    assert summary["mentzer"] == pytest.approx(70 / 4.5, rel=1e-3)


def test_latest_hemogram_summary_none_without_vcm(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_latest_hemogram_summary(db, patient_id) is None


def test_sustained_lymphocytosis_alert_requires_two_reports(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_hemogram_report(db, patient_id, "R1", "2023-01-01", limfocits=5.5)
    assert get_sustained_lymphocytosis_alert(db, patient_id) is None  # una sola vez, no cuenta

    _insert_hemogram_report(db, patient_id, "R2", "2024-01-01", limfocits=6.0, limfocits_cid="linfocits_total")
    alerta = get_sustained_lymphocytosis_alert(db, patient_id)
    assert alerta["fechas"] == ["2023-01-01", "2024-01-01"]
    assert alerta["ultimo_valor"] == 6.0


def test_sustained_lymphocytosis_alert_none_when_normal(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_hemogram_report(db, patient_id, "R1", "2023-01-01", limfocits=2.0)
    _insert_hemogram_report(db, patient_id, "R2", "2024-01-01", limfocits=3.0)
    assert get_sustained_lymphocytosis_alert(db, patient_id) is None
