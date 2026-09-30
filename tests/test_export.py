from pathlib import Path

import openpyxl
import pdfplumber

from analitix.export import export_csv, export_excel, export_pdf, to_dataframe


def test_export_defuses_formula_like_text_but_not_numeric_columns(tmp_path: Path):
    rows = [{"raw_name": "=HYPERLINK(\"x\")", "unit": "+unsafe", "value_raw": "-1.5", "value_num": -1.5}]
    frame = to_dataframe(rows)
    assert frame.loc[0, "raw_name"].startswith("'=")
    assert frame.loc[0, "unit"] == "'+unsafe"
    assert frame.loc[0, "value_raw"] == "-1.5"
    assert frame.loc[0, "value_num"] == -1.5

    csv_path = tmp_path / "results.csv"
    xlsx_path = tmp_path / "results.xlsx"
    export_csv(rows, csv_path)
    export_excel(rows, xlsx_path)
    assert csv_path.exists() and xlsx_path.exists()


def test_export_defuses_formula_in_value_raw(tmp_path: Path):
    # `value_raw` guarda texto libre del PDF cuando el valor no es numérico.
    rows = [{"raw_name": "Glucosa", "value_raw": "=1+1", "value_num": None}]
    assert to_dataframe(rows).loc[0, "value_raw"] == "'=1+1"

    xlsx_path = tmp_path / "results.xlsx"
    export_excel(rows, xlsx_path)
    cell = openpyxl.load_workbook(xlsx_path)["Resultados"]["B2"]
    assert cell.data_type != "f" and cell.value == "'=1+1"


def _filas_prueba():
    return [
        {
            "raw_name": "Glucosa", "canonical_id": "glucosa_serum", "value_num": 150.0, "unit": "mg/dL",
            "ref_low": 70.0, "ref_high": 100.0, "flag_calc": "alto", "valor_anterior": 90.0,
            "pct": 66.7, "brusco": True, "orden": 0,
        },
        {
            "raw_name": "Sodi", "canonical_id": "sodi", "value_num": 140.0, "unit": "mEq/L",
            "ref_low": 135.0, "ref_high": 145.0, "flag_calc": "normal", "valor_anterior": None,
            "pct": None, "brusco": False, "orden": 2,
        },
        {
            # Un solo valor registrado: entra en la tabla pero no debe generar página de gráfico.
            "raw_name": "Potassi", "canonical_id": "potassi", "value_num": 4.0, "unit": "mEq/L",
            "ref_low": 3.5, "ref_high": 5.1, "flag_calc": "normal", "valor_anterior": None,
            "pct": None, "brusco": False, "orden": 2,
        },
    ]


def _series_prueba():
    return {
        "glucosa_serum": [
            {"fecha": "2024-01-01", "value_num": 90.0, "unit": "mg/dL", "ref_low": 70.0, "ref_high": 100.0,
             "flag_calc": "normal", "raw_name": "Glucosa"},
            {"fecha": "2024-06-01", "value_num": 150.0, "unit": "mg/dL", "ref_low": 70.0, "ref_high": 100.0,
             "flag_calc": "alto", "raw_name": "Glucosa"},
        ],
        "potassi": [
            {"fecha": "2024-06-01", "value_num": 4.0, "unit": "mEq/L", "ref_low": 3.5, "ref_high": 5.1,
             "flag_calc": "normal", "raw_name": "Potassi"},
        ],
        # "sodi" deliberadamente sin serie.
    }


def test_export_pdf_fixed_page_structure(tmp_path: Path):
    path = tmp_path / "informe.pdf"
    paginas = export_pdf(
        "Paciente de Prueba", "2024-06-01", _filas_prueba(), _series_prueba(),
        {"glucosa_serum": "Glucosa", "potassi": "Potassi"}, 30.0, path,
        tipo_informe="Informe completo",
    )
    # Solo Glucosa (2 puntos) genera gráfico; Potassi (1 punto) y Sodi (sin serie) no.
    assert paginas == 1
    with pdfplumber.open(path) as pdf:
        assert len(pdf.pages) == 4  # portada + fuera de rango + resto + 1 gráfico

        portada = pdf.pages[0].extract_text()
        assert "Paciente de Prueba" in portada and "Informe completo" in portada
        assert "Página 1" in portada

        pagina_fuera_rango = pdf.pages[1].extract_text()
        assert "Glucosa" in pagina_fuera_rango and "Sodi" not in pagina_fuera_rango
        assert "Página 2" in pagina_fuera_rango and "Informe completo" in pagina_fuera_rango

        pagina_resto = pdf.pages[2].extract_text()
        assert "Sodi" in pagina_resto and "Potassi" in pagina_resto and "Glucosa" not in pagina_resto
        assert "Página 3" in pagina_resto

        pagina_grafico = pdf.pages[3].extract_text()
        assert "Página 4" in pagina_grafico
