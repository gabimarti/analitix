import pytest

from analitix.hepatic_risk import (
    _age_at,
    _plaquetes_1e9_l,
    _u_l,
    apri,
    de_ritis_ratio,
    fib4,
    get_hepatic_index_series,
    get_latest_hepatic_summary,
)
from analitix.repository import get_or_create_patient, insert_result, upsert_report


@pytest.mark.parametrize(
    ("ast", "alt", "expected"),
    [(80, 40, 2.0), (30, 60, 0.5), (None, 40, None), (30, 0, None)],
)
def test_de_ritis_ratio(ast, alt, expected):
    assert de_ritis_ratio(ast, alt) == expected


@pytest.mark.parametrize(
    ("ast", "plaquetes", "expected"),
    [(80, 200, 1.0), (40, 100, 1.0), (None, 200, None), (40, 0, None)],
)
def test_apri(ast, plaquetes, expected):
    assert apri(ast, plaquetes) == expected


def test_fib4_formula():
    # 50 * 80 / (200 * sqrt(40)) = 4000 / 1264.9... ~= 3.162
    result = fib4(50, 80, 200, 40)
    assert result == pytest.approx(3.1623, rel=1e-3)
    assert fib4(None, 80, 200, 40) is None
    assert fib4(50, 80, 200, 0) is None
    assert fib4(50, 80, 0, 40) is None


@pytest.mark.parametrize(
    ("birth_date", "fecha", "expected"),
    [
        ("1980-01-01", "2024-01-01", 44),
        ("1980-06-15", "2024-01-01", 43),  # cumpleaños todavía no llegado ese año
        ("1980-06-15", "2024-06-15", 44),  # justo el día del cumpleaños
        (None, "2024-01-01", None),
    ],
)
def test_age_at(birth_date, fecha, expected):
    assert _age_at(birth_date, fecha) == expected


def test_u_l_accepts_ui_with_temperature_suffix():
    assert _u_l({"value_num": 21, "unit": "U/L"}) == 21
    assert _u_l({"value_num": 21, "unit": "UI/l 37C"}) == 21
    assert _u_l({"value_num": 21, "unit": "mmol/L"}) is None
    assert _u_l(None) is None


def test_plaquetes_1e9_l_accepts_truncated_unit():
    # "x10^3_u/mc" (sin la "L" final) es un valor real visto en un PDF: la
    # extracción trunca el sufijo de unidad en alguna plantilla.
    assert _plaquetes_1e9_l({"value_num": 250, "unit": "x10^3_u/mc"}) == 250
    assert _plaquetes_1e9_l({"value_num": 250, "unit": "x10^3/ul"}) == 250
    assert _plaquetes_1e9_l({"value_num": 250, "unit": "mg/dL"}) is None


def _insert_hepatic_report(con, patient_id, report_number, fecha, ast, alt, plaquetes):
    report_id = upsert_report(con, patient_id, report_number, fecha, None, "synthetic.pdf")
    values = [
        ("AST", "aspartat_aminotranferasa_ast_serum", ast, "U/L"),
        ("ALT", "alanina_aminotransferasa_alt_serum", alt, "U/L"),
        ("Plaquetes", "plaquetes", plaquetes, "x10^3/ul"),
    ]
    for raw_name, canonical_id, value, unit in values:
        insert_result(
            con,
            report_id,
            dict(section=None, test_group=None, loinc_code=None, raw_name=raw_name,
                 canonical_id=canonical_id, value_raw=str(value), value_num=value,
                 unit=unit, ref_low=None, ref_high=None, ref_text=None,
                 flag_pdf=None, flag_calc=None, sample_date=None),
        )
    con.commit()


def test_hepatic_index_series_without_birth_date_skips_fib4(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    _insert_hepatic_report(db, patient_id, "R1", "2024-01-01", ast=80, alt=40, plaquetes=200)

    series = get_hepatic_index_series(db, patient_id)
    assert series["idx_de_ritis"][0]["value_num"] == 2.0
    assert series["idx_apri"][0]["value_num"] == pytest.approx(1.0)
    assert "idx_fib4" not in series


def test_hepatic_index_series_with_birth_date_includes_fib4(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", "1980-01-01", None, None)
    _insert_hepatic_report(db, patient_id, "R1", "2024-01-01", ast=80, alt=40, plaquetes=200)

    series = get_hepatic_index_series(db, patient_id)
    # Edad en la fecha del informe: 44 (nacido 1980-01-01, informe 2024-01-01).
    assert series["idx_fib4"][0]["value_num"] == pytest.approx(2.7828, rel=1e-3)


def test_latest_hepatic_summary(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", "1980-01-01", None, None)
    _insert_hepatic_report(db, patient_id, "R1", "2024-01-01", ast=80, alt=40, plaquetes=200)

    summary = get_latest_hepatic_summary(db, patient_id)
    assert summary["fecha"] == "2024-01-01"
    assert summary["edad"] == 44
    assert summary["de_ritis"] == 2.0
    assert summary["fib4"] == pytest.approx(2.7828, rel=1e-3)


def test_latest_hepatic_summary_none_without_data(db):
    patient_id, _ = get_or_create_patient(db, "Test Patient", None, None, None)
    assert get_latest_hepatic_summary(db, patient_id) is None
