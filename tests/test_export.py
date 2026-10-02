import pytest
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


def test_custom_pdf_pages_fit_a4_with_footer_room(tmp_path: Path):
    from matplotlib.figure import Figure

    from analitix.export import _fit_page_a4, export_pages_pdf, text_page

    # Un gráfico apaisado pasa a A4 horizontal; su contenido deja libre la franja del pie.
    fig = Figure(figsize=(8, 3))
    ax = fig.add_axes((0.1, 0.0, 0.8, 0.9))
    leyenda = fig.legend(handles=[], loc="lower center")
    _fit_page_a4(fig)
    assert tuple(round(v, 2) for v in fig.get_size_inches()) == (11.69, 8.27)
    assert ax.get_position().y0 == pytest.approx(0.4 / 8.27)
    assert leyenda.get_bbox_to_anchor().y0 > 0
    # Uno más alto que ancho pasa a A4 vertical.
    alta = Figure(figsize=(9, 15))
    _fit_page_a4(alta)
    assert tuple(round(v, 2) for v in alta.get_size_inches()) == (8.27, 11.69)
    # Una página que ya es A4 no se toca.
    a4 = text_page("Título", "Texto de prueba")
    posiciones = [t.get_position() for t in a4.texts]
    _fit_page_a4(a4)
    assert [t.get_position() for t in a4.texts] == posiciones

    path = tmp_path / "personalizado.pdf"
    total = export_pages_pdf("PACIENTE FICTICIO", "2024-01-01", [a4, Figure(figsize=(8, 4))], path,
                             tipo_informe="Informe personalizado")
    assert total == 3
    with pdfplumber.open(path) as pdf:
        tamanos = {tuple(sorted((round(p.width / 72, 2), round(p.height / 72, 2)))) for p in pdf.pages}
        assert tamanos == {(8.27, 11.69)}  # todas las páginas son A4
        assert "Último informe de laboratorio" in pdf.pages[0].extract_text()


def test_variable_height_charts_are_relaid_out_on_a4():
    from analitix.charts import heatmap_figure
    from analitix.export import _fit_page_a4

    nombre = "Parámetro sintético con un nombre bastante largo (sèrum)"
    filas = [(f"{nombre} {i}", [dict(fecha="2024-01-01", value_num=1.0, ref_low=0.0, ref_high=2.0, flag_calc="normal")])
             for i in range(20)]
    fig = heatmap_figure(filas, "Prueba")
    _fit_page_a4(fig)
    fig.canvas.draw()
    ancho_px = fig.get_size_inches()[0] * fig.dpi
    etiquetas = [t.get_window_extent() for t in fig.axes[0].get_yticklabels() if t.get_text()]
    assert min(e.x0 for e in etiquetas) >= 0 and max(e.x1 for e in etiquetas) <= ancho_px  # nada cortado
