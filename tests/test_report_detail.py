# ---------------------------------------------------------------------------
# Script: test_report_detail.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-11-15
# ---------------------------------------------------------------------------
"""Tests unitarios para el detalle de analítica y comparativa delta (report_detail)."""

from analitix import report_detail
from analitix.db import connect
from analitix.repository import (
    get_or_create_patient,
    get_previous_report,
    get_report_meta,
    get_report_results,
    insert_result,
    upsert_report,
)


def test_normalize_name_key():
    assert report_detail.normalize_name_key(" Glucosa en suero ") == "glucosa en suero"
    assert report_detail.normalize_name_key("COLÈSTEROL  HDL") == "colesterol hdl"
    assert report_detail.normalize_name_key("Ácido Úrico") == "acido urico"
    assert report_detail.normalize_name_key("") == ""
    assert report_detail.normalize_name_key(None) == ""


def test_format_status():
    assert report_detail.format_status("alto", None) == "↑ Alto"
    assert report_detail.format_status("bajo", None) == "↓ Bajo"
    assert report_detail.format_status("normal", None) == "Normal"
    assert report_detail.format_status(None, "*") == "↑ Alto"
    assert report_detail.format_status(None, "L") == "↓ Bajo"
    assert report_detail.format_status(None, "ANORMAL") == "⚠ Fuera de rango"
    assert report_detail.format_status(None, None) == "Normal"


def test_diff_level():
    assert report_detail.diff_level(50.0) == "high"
    assert report_detail.diff_level(-25.0) == "high"
    assert report_detail.diff_level(15.0) == "moderate"
    assert report_detail.diff_level(-10.0) == "moderate"
    assert report_detail.diff_level(5.0) == "low"
    assert report_detail.diff_level(0.0) == "low"
    assert report_detail.diff_level(None) == "none"


def test_filter_non_analytical_values():
    curr = [
        {
            "id": 1,
            "raw_name": "Bilirubina directa",
            "value_raw": "No és procedent",
            "value_num": None,
        },
        {"id": 2, "raw_name": "Glucosa", "value_raw": "90", "value_num": 90.0},
        {"id": 3, "raw_name": "Prueba nueva", "value_raw": "5.5", "value_num": 5.5},
        {"id": 4, "raw_name": "Prueba cancelada", "value_raw": "No procede", "value_num": None},
    ]
    prev = [
        {
            "id": 10,
            "raw_name": "Bilirubina directa",
            "value_raw": "No és procedent",
            "value_num": None,
        },
        {"id": 11, "raw_name": "Glucosa", "value_raw": "95", "value_num": 95.0},
        {"id": 12, "raw_name": "Prueba cancelada", "value_raw": "10.0", "value_num": 10.0},
    ]
    rows = report_detail.match_and_compare_results(curr, prev)
    # Bilirubina directa debe ser omitida porque es 'No és procedent' en ambos
    # Prueba cancelada debe mantenerse porque en prev sí tenía valor real (10.0)
    # Glucosa y Prueba nueva deben mantenerse
    names = [r["raw_name"] for r in rows]
    assert "Bilirubina directa" not in names
    assert "Glucosa" in names
    assert "Prueba nueva" in names
    assert "Prueba cancelada" in names
    assert len(rows) == 3


def test_filter_comments_and_notes():
    # Se excluye siempre por nombre, independientemente de value_num
    assert report_detail.is_comment_or_note("Comentari proteïnograma", None) is True
    assert report_detail.is_comment_or_note("Comentari proteïnograma", 1.5) is True
    assert report_detail.is_comment_or_note("Comentario clínico", None) is True
    assert report_detail.is_comment_or_note("Observacions", None) is True
    assert report_detail.is_comment_or_note("Glucosa", 90.0) is False
    assert report_detail.is_comment_or_note("Hemoglobina", None) is False

    curr = [
        {
            "id": 1,
            "raw_name": "Comentari proteïnograma",
            "value_raw": "Desplaçament de banda",
            "value_num": None,
        },
        {"id": 2, "raw_name": "Glucosa", "value_raw": "90", "value_num": 90.0},
    ]
    prev = [
        {
            "id": 10,
            "raw_name": "Comentari proteïnograma",
            "value_raw": "Desplaçament de banda",
            "value_num": None,
        },
        {"id": 11, "raw_name": "Glucosa", "value_raw": "95", "value_num": 95.0},
    ]
    rows = report_detail.match_and_compare_results(curr, prev)
    names = [r["raw_name"] for r in rows]
    assert "Comentari proteïnograma" not in names
    assert "Glucosa" in names
    assert len(rows) == 1


def test_format_diff():
    assert report_detail.format_diff(0.4, 2.8) == "+0.4 (+2.8%)"
    assert report_detail.format_diff(-15.0, -12.5) == "-15 (-12.5%)"
    assert report_detail.format_diff(0.0, 0.0) == "0 (0.0%)"
    assert report_detail.format_diff(5.0, None) == "+5"
    assert report_detail.format_diff(None, None) == "—"


def test_match_and_compare_single_report():
    curr = [
        {
            "id": 1,
            "section": "BIOQUÍMICA",
            "raw_name": "Glucosa",
            "canonical_id": "glucosa",
            "value_raw": "95",
            "value_num": 95.0,
            "unit": "mg/dL",
            "ref_low": 70.0,
            "ref_high": 110.0,
            "flag_calc": None,
        },
        {
            "id": 2,
            "section": "BIOQUÍMICA",
            "raw_name": "Colesterol",
            "canonical_id": "colesterol_serum",
            "value_raw": "220",
            "value_num": 220.0,
            "unit": "mg/dL",
            "ref_low": None,
            "ref_high": 200.0,
            "flag_calc": "alto",
        },
    ]
    rows = report_detail.match_and_compare_results(curr, previous_results=None)
    assert len(rows) == 2
    assert rows[0]["raw_name"] == "Glucosa"
    assert rows[0]["status"] == "Normal"
    assert rows[0]["diff_num"] is None
    assert rows[1]["status"] == "↑ Alto"
    assert rows[1]["ref_text"] == "≤ 200"


def test_match_and_compare_with_previous():
    curr = [
        {
            "id": 10,
            "section": "HEMATOLOGÍA",
            "raw_name": "Hemoglobina",
            "canonical_id": "hemoglobina",
            "value_raw": "14.5",
            "value_num": 14.5,
            "unit": "g/dL",
            "flag_calc": None,
        },
        {
            "id": 11,
            "section": "BIOQUÍMICA",
            "raw_name": "Colesterol Total",
            "canonical_id": "colesterol_serum",
            "value_raw": "195",
            "value_num": 195.0,
            "unit": "mg/dL",
            "flag_calc": None,
        },
        {
            "id": 12,
            "section": "BIOQUÍMICA",
            "raw_name": "Triglicéridos",
            "canonical_id": "triglicerids_serum",
            "value_raw": "180",
            "value_num": 180.0,
            "unit": "mg/dL",
            "flag_calc": "alto",
        },
        {
            "id": 13,
            "section": "BIOQUÍMICA",
            "raw_name": "Prueba Rara Sin Id",
            "canonical_id": None,
            "value_raw": "50",
            "value_num": 50.0,
            "unit": "U/L",
            "flag_calc": None,
        },
    ]
    prev = [
        {
            "id": 1,
            "section": "HEMATOLOGÍA",
            "raw_name": "Hemoglobina",
            "canonical_id": "hemoglobina",
            "value_raw": "13.5",
            "value_num": 13.5,
            "unit": "g/dL",
            "flag_calc": None,
        },
        {
            "id": 2,
            "section": "BIOQUÍMICA",
            "raw_name": "Colesterol",
            "canonical_id": "colesterol_serum",
            "value_raw": "210",
            "value_num": 210.0,
            "unit": "mg/dL",
            "flag_calc": "alto",
        },
        {
            "id": 3,
            "section": "BIOQUÍMICA",
            "raw_name": "Triglicéridos",
            "canonical_id": "triglicerids_serum",
            "value_raw": "140",
            "value_num": 140.0,
            "unit": "mg/dL",
            "flag_calc": None,
        },
        {
            "id": 4,
            "section": "BIOQUÍMICA",
            "raw_name": "prueba rara sin id",
            "canonical_id": None,
            "value_raw": "60",
            "value_num": 60.0,
            "unit": "U/L",
            "flag_calc": None,
        },
    ]

    rows = report_detail.match_and_compare_results(curr, prev)
    assert len(rows) == 4

    # Hemoglobina: 14.5 vs 13.5 -> +1.0 (+7.4%), tendencia ↑
    hb = rows[0]
    assert hb["canonical_id"] == "hemoglobina"
    assert hb["diff_num"] == 1.0
    assert hb["diff_pct"] == 7.4
    assert hb["trend"] == report_detail.ARROW_UP
    assert hb["range_alert"] == report_detail.ALERT_NORMAL

    # Colesterol: 195 vs 210 -> -15 (-7.1%), antes alto y ahora normal -> Normalizado
    col = rows[1]
    assert col["diff_num"] == -15.0
    assert col["diff_pct"] == -7.1
    assert col["trend"] == report_detail.ARROW_DOWN
    assert col["range_alert"] == report_detail.ALERT_NORMALIZED

    # Triglicéridos: 180 vs 140 -> +40 (+28.6%), antes normal y ahora alto -> Entra en alto
    tg = rows[2]
    assert tg["diff_num"] == 40.0
    assert tg["diff_pct"] == 28.6
    assert tg["trend"] == report_detail.ARROW_UP
    assert tg["range_alert"] == report_detail.ALERT_ENTERED_HIGH

    # Prueba sin id emparejada por nombre: 50 vs 60 -> -10 (-16.7%)
    rara = rows[3]
    assert rara["diff_num"] == -10.0
    assert rara["trend"] == report_detail.ARROW_DOWN

    summary = report_detail.build_comparison_summary(rows)
    assert summary["total"] == 4
    assert summary["fuera_rango"] == 1
    assert summary["normalizados"] == 1
    assert summary["nuevos_fuera"] == 1
    assert summary["al_alza"] == 2
    assert summary["a_la_baja"] == 2


def test_repository_report_functions(tmp_path):
    db_path = tmp_path / "test.db"
    con = connect("clave-secreta", db_path)
    pid, _ = get_or_create_patient(con, "Paciente Prueba", "1980-01-01", None, None)

    # Crear dos informes
    rep1 = upsert_report(
        con, pid, "REP001", "2025-01-10", "2025-01-11", "informe1.pdf", lab="Lab A"
    )
    insert_result(
        con,
        rep1,
        {
            "section": "BIOQ",
            "test_group": None,
            "loinc_code": None,
            "raw_name": "Glucosa",
            "canonical_id": "glucosa",
            "value_raw": "100",
            "value_num": 100.0,
            "unit": "mg/dL",
            "ref_low": 70.0,
            "ref_high": 110.0,
            "ref_text": None,
            "flag_pdf": None,
            "flag_calc": None,
            "sample_date": None,
        },
    )

    rep2 = upsert_report(
        con, pid, "REP002", "2025-06-15", "2025-06-16", "informe2.pdf", lab="Lab A"
    )
    insert_result(
        con,
        rep2,
        {
            "section": "BIOQ",
            "test_group": None,
            "loinc_code": None,
            "raw_name": "Glucosa",
            "canonical_id": "glucosa",
            "value_raw": "115",
            "value_num": 115.0,
            "unit": "mg/dL",
            "ref_low": 70.0,
            "ref_high": 110.0,
            "ref_text": None,
            "flag_pdf": None,
            "flag_calc": "alto",
            "sample_date": None,
        },
    )
    con.commit()

    # Probar get_report_meta
    meta = get_report_meta(con, rep2)
    assert meta is not None
    assert meta["report_number"] == "REP002"
    assert meta["lab"] == "Lab A"
    assert meta["fecha"] == "2025-06-15"
    assert meta["num_results"] == 1

    # Probar get_report_results
    results = get_report_results(con, rep2)
    assert len(results) == 1
    assert results[0]["raw_name"] == "Glucosa"
    assert results[0]["value_num"] == 115.0
    assert results[0]["flag_calc"] == "alto"

    # Probar get_previous_report
    prev = get_previous_report(con, pid, rep2)
    assert prev is not None
    assert prev["id"] == rep1
    assert prev["report_number"] == "REP001"

    # rep1 no tiene informe previo
    prev_of_first = get_previous_report(con, pid, rep1)
    assert prev_of_first is None

    con.close()


def test_export_report_detail(tmp_path):
    from analitix.export import (
        export_report_detail_csv,
        export_report_detail_excel,
        export_report_detail_pdf,
    )

    curr = [
        {
            "id": 1,
            "section": "BIOQUÍMICA",
            "raw_name": "Glucosa",
            "canonical_id": "glucosa",
            "value_raw": "95",
            "value_num": 95.0,
            "unit": "mg/dL",
            "ref_low": 70.0,
            "ref_high": 110.0,
            "ref_text": "70 – 110",
            "flag_calc": None,
            "flag_pdf": None,
        }
    ]
    rows = report_detail.match_and_compare_results(curr)
    report_meta = {
        "report_number": "INF-2026-001",
        "lab": "Laboratori Clínic",
        "fecha": "2026-05-10",
    }

    # CSV
    csv_path = tmp_path / "detalle.csv"
    export_report_detail_csv(rows, csv_path, is_comparison=False)
    assert csv_path.exists()
    assert "Glucosa" in csv_path.read_text(encoding="utf-8-sig")

    # Excel
    xlsx_path = tmp_path / "detalle.xlsx"
    export_report_detail_excel(rows, xlsx_path, is_comparison=False)
    assert xlsx_path.exists()

    # PDF individual
    pdf_path = tmp_path / "detalle.pdf"
    pags = export_report_detail_pdf(
        "Paciente Ficticio", report_meta, rows, pdf_path, prev_report_meta=None
    )
    assert pdf_path.exists()
    assert pags >= 2  # Portada + tabla

    # PDF comparativo
    pdf_comp_path = tmp_path / "detalle_comp.pdf"
    prev_meta = {
        "report_number": "INF-2025-099",
        "lab": "Laboratori Clínic",
        "fecha": "2025-11-20",
    }
    pags_comp = export_report_detail_pdf(
        "Paciente Ficticio", report_meta, rows, pdf_comp_path, prev_report_meta=prev_meta
    )
    assert pdf_comp_path.exists()
    assert pags_comp >= 2


def _fila(nombre, status="Normal", alerta=report_detail.ALERT_NORMAL):
    return {"raw_name": nombre, "status": status, "range_alert": alerta, "section": "S"}


def test_filter_rows_for_mode():
    filas = [
        _fila("normal"),
        _fila("alto", "↑ Alto", report_detail.ALERT_STILL_HIGH),
        _fila("normalizado", "Normal", report_detail.ALERT_NORMALIZED),
        _fila("pdf", "⚠ Fuera de rango"),
    ]
    alterados = report_detail.filter_rows_for_mode(filas, report_detail.DELTA_MODE_ALTERED)
    assert [f["raw_name"] for f in alterados] == ["alto", "normalizado", "pdf"]
    for modo in (report_detail.DELTA_MODE_FULL, report_detail.DELTA_MODE_LATEST):
        assert report_detail.filter_rows_for_mode(filas, modo) == filas
    assert report_detail.delta_mode_compares(report_detail.DELTA_MODE_FULL)
    assert report_detail.delta_mode_compares(report_detail.DELTA_MODE_ALTERED)
    assert not report_detail.delta_mode_compares(report_detail.DELTA_MODE_LATEST)
