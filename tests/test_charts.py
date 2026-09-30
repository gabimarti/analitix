from analitix.charts import trend_arrow


def _serie(fechas, valores):
    return [{"fecha": f, "value_num": v} for f, v in zip(fechas, valores)]


def test_trend_arrow_ascendente():
    serie = _serie(
        ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"],
        [80, 90, 100, 115],
    )
    resultado = trend_arrow(serie, 70, 100)
    assert resultado.startswith("↑ +") and resultado.endswith("%/año"), resultado


def test_trend_arrow_descendente():
    serie = _serie(
        ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"],
        [115, 100, 90, 80],
    )
    resultado = trend_arrow(serie, 70, 100)
    assert resultado.startswith("↓ -") and resultado.endswith("%/año"), resultado


def test_trend_arrow_estable():
    serie = _serie(
        ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"],
        [140, 140.5, 139.5, 140],
    )
    assert trend_arrow(serie, 135, 145) == "→"


def test_trend_arrow_pocos_puntos():
    serie = _serie(["2024-01-01", "2024-04-01"], [4.0, 3.6])
    assert trend_arrow(serie, 3.5, 5.0) is None


def test_range_position():
    from analitix.charts import HEATMAP_MIN_INTENSITY, range_position

    assert range_position(14, 12, 16) == 0.0
    assert range_position(None, 12, 16) is None and range_position(5, None, None) is None
    # Justo fuera del rango: ya con la intensidad mínima (nunca confundible con "en rango").
    assert -1 < range_position(11.9, 12, 16) <= -HEATMAP_MIN_INTENSITY
    assert HEATMAP_MIN_INTENSITY <= range_position(16.1, 12, 16) < 1
    # A medio ancho de rango o más: intensidad máxima.
    assert range_position(20, 12, 16) == 1.0 and range_position(0, 12, 16) == -1.0
    # Un solo límite ("< 200"): distancia en fracciones del límite.
    assert range_position(150, None, 200) == 0.0 and range_position(300, None, 200) == 1.0


def _row(fecha, value, lab, low=12.0, high=16.0):
    from analitix.pdf_parser import compute_flag

    return dict(fecha=fecha, value_num=value, unit="g/dL", ref_low=low, ref_high=high,
                flag_calc=compute_flag(value, low, high), lab=lab, raw_name="Hemoglobina")


def test_heatmap_figure_cells_and_metadata():
    from analitix.charts import heatmap_figure

    rows = [
        ("Hemoglobina", [_row("2024-01-01", 11.0, "A"), _row("2024-06-01 08:00:00", 14.0, "B")]),
        ("Ferritina", [_row("2024-06-01", 400.0, "B", 30, 300)]),
        ("Sin datos", []),
    ]
    fig = heatmap_figure(rows, "Prueba")
    meta = fig.axes[0].analitix_heatmap
    assert meta["rows"] == ["Hemoglobina", "Ferritina"]  # las filas vacías no se dibujan
    assert meta["dates"] == ["2024-01-01", "2024-06-01"]
    assert meta["cells"][(0, 1)]["value_num"] == 14.0 and (1, 0) not in meta["cells"]


def test_evolution_points_shaped_by_lab():
    from analitix.charts import evolution_figure

    def scatters(fig):
        return [c for c in fig.axes[0].collections if hasattr(c, "analitix_series")]

    one_lab = [_row(f"2024-0{m}-01", 14.0, "A") for m in (1, 2, 3)]
    assert len(scatters(evolution_figure(one_lab, "x"))) == 1
    two_labs = one_lab + [_row("2024-04-01", 15.0, "B"), _row("2024-05-01", 13.0, None)]
    groups = scatters(evolution_figure(two_labs, "x"))
    assert [len(g.analitix_series) for g in groups] == [3, 1, 1]  # A, B y "desconocido"
    labels = [t.get_text() for t in evolution_figure(two_labs, "x").axes[0].get_legend().get_texts()]
    assert {"A", "B", "Laboratorio desconocido"} <= set(labels)


def test_change_status():
    from analitix.charts import change_status

    # Medido en anchos de rango: creatinina 0.9 -> 1.1 (rango 0.5-1.0) sale del rango.
    delta, estado = change_status(0.9, 1.1, 0.5, 1.0)
    assert round(delta, 2) == 0.4 and estado == "empeora"
    assert change_status(200, 244, 150, 400)[1] == "igual"        # dentro antes y ahora
    assert change_status(130, 104, 70, 105)[1] == "mejora"        # vuelve al rango
    assert change_status(25, 18, 30, 300)[1] == "empeora"         # ya fuera, se aleja más
    assert change_status(230, 210, None, 200)[1] == "mejora"      # un solo límite
    assert change_status(20, 31, None, None) is None              # sin rango, no se puede medir


def test_changes_figure_orders_and_skips():
    from analitix.charts import changes_figure

    rows = [
        dict(label="Plaquetas", previous=200, value=244, unit="", ref_low=150, ref_high=400),
        dict(label="Creatinina", previous=0.9, value=1.1, unit="", ref_low=0.5, ref_high=1.0),
        dict(label="Sin rango", previous=1, value=2, unit="", ref_low=None, ref_high=None),
        dict(label="Sin anterior", previous=None, value=2, unit="", ref_low=1, ref_high=3),
    ]
    items = changes_figure(rows, "x").axes[0].analitix_changes
    # Solo los medibles; el mayor cambio (en anchos de rango) queda arriba (último índice).
    assert [r["label"] for r in items] == ["Plaquetas", "Creatinina"]
