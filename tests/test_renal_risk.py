import pytest

from analitix.renal_risk import (
    _acr_mg_g,
    _ml_min,
    _mg_dl,
    acr_category,
    aki_ratio,
    gfr_category,
    get_latest_renal_summary,
    get_renal_index_series,
    kdigo_risk,
    urea_creatinina_ratio,
)
from analitix.repository import get_or_create_patient, insert_result, upsert_report


@pytest.mark.parametrize(
    ("value", "expected"),
    [(95, "G1"), (90, "G1"), (89, "G2"), (60, "G2"), (59, "G3a"), (45, "G3a"),
     (44, "G3b"), (30, "G3b"), (29, "G4"), (15, "G4"), (14, "G5"), (0, "G5"), (None, None)],
)
def test_gfr_category(value, expected):
    assert gfr_category(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(10, "A1"), (29.9, "A1"), (30, "A2"), (299, "A2"), (300, "A3"), (500, "A3"), (None, None)],
)
def test_acr_category(value, expected):
    assert acr_category(value) == expected


@pytest.mark.parametrize(
    ("g", "a", "expected"),
    [
        ("G1", "A1", "verde"), ("G1", "A3", "naranja"),
        ("G3a", "A1", "amarillo"), ("G3a", "A3", "rojo"),
        ("G4", "A3", "rojo_oscuro"), ("G5", "A1", "rojo_oscuro"),
        (None, "A1", None), ("G1", None, None),
    ],
)
def test_kdigo_risk(g, a, expected):
    assert kdigo_risk(g, a) == expected


def test_urea_creatinina_ratio():
    # Urea 48 mg/dL, creatinina 0.9 mg/dL -> ratio ~53.3, por encima de
    # UREA_CREATININA_HIGH (~42.8) -> sugiere causa prerenal.
    assert urea_creatinina_ratio(48, 0.9) == pytest.approx(53.33, rel=1e-2)
    assert urea_creatinina_ratio(None, 0.9) is None
    assert urea_creatinina_ratio(48, 0) is None


def test_aki_ratio_uses_median_of_8_to_365_day_window():
    previas = [
        ("2023-01-01", 0.8),
        ("2023-06-01", 1.0),
        ("2023-12-20", 5.0),  # fuera de ventana (solo 11 días antes de la fecha actual, < 8 no... calculemos)
    ]
    # Fecha actual bien separada de todas salvo la primera comprobación manual.
    ratio = aki_ratio(1.5, previas[:2], "2024-01-01")
    # Mediana de [0.8, 1.0] = 0.9 -> 1.5/0.9 = 1.666...
    assert ratio == pytest.approx(1.6667, rel=1e-3)


def test_aki_ratio_excludes_same_date_and_out_of_window():
    previas = [
        ("2024-01-01", 999.0),  # misma fecha que la actual: se excluye
        ("2023-12-30", 1.0),  # solo 2 días antes: fuera de la ventana 8-365
        ("2022-01-01", 1.0),  # más de 365 días antes: fuera de ventana
    ]
    assert aki_ratio(1.5, previas, "2024-01-01") is None


def test_unit_guards():
    assert _mg_dl({"value_num": 48, "unit": "mg/dl"}) == 48
    assert _mg_dl({"value_num": 48, "unit": "mmol/L"}) is None
    assert _ml_min({"value_num": 80, "unit": "mL/min"}) == 80
    assert _ml_min({"value_num": 80, "unit": "mL/min/1.73m2"}) == 80
    assert _ml_min({"value_num": 80, "unit": None}) is None
    # mcg/mg y mg/g son numéricamente equivalentes (ver docstring de _acr_mg_g).
    assert _acr_mg_g({"value_num": 2.4, "unit": "mcg/mg"}) == 2.4
    assert _acr_mg_g({"value_num": 2.4, "unit": "mg/g_creat"}) == 2.4
    assert _acr_mg_g({"value_num": 2.4, "unit": "mg/L"}) is None


def _insert_renal_report(con, patient_id, report_number, fecha, fg=None, urea=None, creatinina=None, acr=None):
    report_id = upsert_report(con, patient_id, report_number, fecha, None, "synthetic.pdf")
    values = []
    if fg is not None:
        values.append(("FG estimat", "filtrat_glomerular_estimat_serum", fg, "mL/min"))
    if urea is not None:
        values.append(("Urea", "urea_serum", urea, "mg/dL"))
    if creatinina is not None:
        values.append(("Creatinina", "creatinina_serum", creatinina, "mg/dL"))
    if acr is not None:
        values.append(("Albumina/Creatinina", "albumina_creatinina", acr, "mg/g_creat"))
    for raw_name, cid, value, unit in values:
        insert_result(
            con, report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name=raw_name,
                 canonical_id=cid, value_raw=str(value), value_num=value, unit=unit,
                 ref_low=None, ref_high=None, ref_text=None, flag_pdf=None, flag_calc=None, sample_date=None),
        )
    con.commit()


def test_renal_index_series_and_summary(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", "1980-01-01", None, None)
    _insert_renal_report(db, patient_id, "R1", "2023-01-01", fg=90, urea=30, creatinina=0.9)
    _insert_renal_report(db, patient_id, "R2", "2024-01-01", fg=46, urea=48, creatinina=1.4, acr=50)

    series = get_renal_index_series(db, patient_id)
    assert len(series["idx_urea_creatinina"]) == 2
    # AKI: la segunda fecha tiene una creatinina previa (0.9) dentro de la ventana 8-365 días.
    assert len(series["idx_aki_creatinina"]) == 1
    assert series["idx_aki_creatinina"][0]["value_num"] == pytest.approx(1.4 / 0.9, rel=1e-3)

    summary = get_latest_renal_summary(db, patient_id)
    assert summary["fecha"] == "2024-01-01"
    assert summary["g_categoria"] == "G3a"
    assert summary["a_categoria"] == "A2"
    assert summary["riesgo_kdigo"] == "naranja"


def test_latest_renal_summary_none_without_fg(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_latest_renal_summary(db, patient_id) is None
