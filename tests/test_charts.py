from analitix.charts import trend_arrow


def _serie(fechas, valores):
    return [{"fecha": f, "value_num": v} for f, v in zip(fechas, valores)]


def test_trend_arrow_ascendente():
    serie = _serie(
        ["2022-01-01", "2022-07-01", "2023-01-01", "2023-07-01", "2024-03-01"],
        [80, 90, 100, 108, 115],
    )
    resultado = trend_arrow(serie, 70, 100)
    assert resultado.startswith("↑ +") and resultado.endswith("%/año"), resultado


def test_trend_arrow_descendente():
    serie = _serie(
        ["2022-01-01", "2022-07-01", "2023-01-01", "2023-07-01", "2024-03-01"],
        [115, 100, 95, 90, 80],
    )
    resultado = trend_arrow(serie, 70, 100)
    assert resultado.startswith("↓ -") and resultado.endswith("%/año"), resultado


def test_trend_arrow_estable():
    serie = _serie(
        ["2022-01-01", "2022-07-01", "2023-01-01", "2023-07-01", "2024-03-01"],
        [140, 140.5, 139.5, 140, 140.2],
    )
    assert trend_arrow(serie, 135, 145) == "→"


def test_trend_arrow_pocos_puntos():
    serie = _serie(["2024-01-01", "2024-04-01"], [4.0, 3.6])
    assert trend_arrow(serie, 3.5, 5.0) is None
    # 4 analíticas en 3 meses: hay recta, pero pocos datos para confirmar tendencia
    corta = _serie(["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"], [80, 90, 100, 115])
    assert trend_arrow(corta, 70, 100) is None


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


def test_data_sufficiency_thresholds():
    from analitix.charts import data_sufficiency

    assert data_sufficiency(0, 4) == "sin_datos"
    assert data_sufficiency(1, 4) == "un_punto"
    assert data_sufficiency(2, 4) == data_sufficiency(3, 4) == "pocos"
    assert data_sufficiency(4, 4) == "suficiente"
    assert data_sufficiency(2, 1) == "suficiente"  # el umbral nunca baja de 2


def test_few_points_control_in_every_series_chart():
    from analitix.charts import comparison_figure, evolution_figure

    def texts(ax):
        return " ".join(t.get_text() for t in ax.texts)

    def scatters(ax):
        return [c for c in ax.collections if hasattr(c, "analitix_series")]

    uno = [_row("2024-01-01", 14.0, "A")]
    dos = uno + [_row("2024-02-01", 15.0, "A")]
    cuatro = dos + [_row("2024-03-01", 15.0, "A"), _row("2024-04-01", 15.0, "A")]

    ax = evolution_figure(uno, "x", 4).axes[0]
    assert "Solo hay 1 analítica" in texts(ax) and not scatters(ax)  # sin gráfico
    ax = evolution_figure(dos, "x", 4).axes[0]
    assert "Solo 2 analíticas" in texts(ax) and scatters(ax)  # gráfico con aviso
    ax = evolution_figure(cuatro, "x", 4).axes[0]
    assert "Solo" not in texts(ax)

    # Comparativa (y paneles combinados): el mismo control en cada subgráfico.
    fig = comparison_figure({"A": uno, "B": cuatro}, 4)
    assert "Solo hay 1 analítica" in texts(fig.axes[0])
    assert "Solo" not in texts(fig.axes[1])


def test_evolution_rcv_band():
    from analitix.charts import evolution_figure

    serie = [_row("2024-01-01", 14.0, "A"), _row("2024-02-01", 15.0, "A")]
    rcv = dict(estado="esperable", rcv_bajada=-10.0, rcv_subida=12.0)
    ax = evolution_figure(serie, "x", 2, rcv=rcv).axes[0]
    (barra,) = [c for c in ax.containers if c.__class__.__name__ == "ErrorbarContainer"]
    (lineas,) = barra.lines[2]
    (segmento,) = lineas.get_segments()
    assert [round(y, 2) for _, y in segmento] == [12.6, 15.68]  # 14 −10 % y +12 %, centrada en el anterior
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert any("RCV -10% / +12%" in t for t in labels)

    otro = evolution_figure(serie, "x", 2, rcv=dict(estado="otro_lab", rcv_bajada=-10.0, rcv_subida=12.0))
    assert not otro.axes[0].containers
    assert any("otro laboratorio" in t.get_text() for t in otro.axes[0].get_legend().get_texts())


def test_evolution_personal_band():
    from analitix.charts import evolution_figure

    serie = [_row(f"2024-0{m}-01", 14.0, "A") for m in (1, 2, 3, 4)]
    pr = dict(bajo=13.0, alto=15.0, punto=14.0, n=3, labs=2)
    ax = evolution_figure(serie, "x", 2, personal=pr).axes[0]
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert any(t.startswith("Tu rango personal 13–15 (n=3)") and "mezcla laboratorios" in t for t in labels)
    assert not any("rango personal" in t for t in
                   [t.get_text() for t in evolution_figure(serie, "x", 2).axes[0].get_legend().get_texts()])


def test_series_summary_text():
    from analitix.charts import series_summary

    # Rango 12-16 (`_row`): 11 bajo, 14 dentro, 17.6 alto (+10 % sobre 16).
    serie = [_row("2024-01-01", 11.0, "A"), _row("2024-02-01", 14.0, "A"), _row("2024-03-01", 17.6, "A")]
    assert series_summary(serie) == (
        "Dentro del rango en 1 de 3 analíticas; la última (2024-03-01), un 10 % por encima del límite "
        "superior (16)."
    )
    assert series_summary(serie[:2]).endswith("la última (2024-02-01), dentro.")
    assert "por debajo del límite inferior (12)" in series_summary(serie[:1])
    sin_rango = [dict(fecha="2024-01-01", value_num=1.5, ref_low=None, ref_high=None, flag_calc=None)]
    assert series_summary(sin_rango) is None  # sin rango no hay nada que resumir


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


def test_heatmap_labels_only_row_extremes_with_many_columns():
    from analitix.charts import HEATMAP_MAX_LABELED_COLUMNS, _ink_for, heatmap_figure

    n = HEATMAP_MAX_LABELED_COLUMNS + 6  # más columnas de las que caben etiquetadas
    valores = [14.0] * n
    valores[3], valores[10], valores[20] = 18.0, 21.0, 9.0  # dos altos y un bajo (rango 12-16)
    serie = [_row(f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", v, "A") for i, v in enumerate(valores)]
    textos = sorted(t.get_text() for t in heatmap_figure([("Hb", serie)], "x").axes[0].texts)
    assert textos == ["21", "9"]  # el máximo por encima y el mínimo por debajo, no el 18
    # Contraste: blanco sobre oscuro, tinta oscura sobre claro.
    assert _ink_for((0.1, 0.1, 0.4, 1)) == "white"
    assert _ink_for((0.95, 0.9, 0.9, 1)) != "white"


def test_out_of_range_labels_carry_symbol_not_only_color():
    # Paleta apta para daltonismo: alto/bajo se leen también sin color.
    from analitix.charts import evolution_figure

    serie = [_row("2024-01-01", 17.0, "A"), _row("2024-02-01", 14.0, "A"),
             _row("2024-03-01", 11.0, "A"), _row("2024-04-01", 14.5, "A")]
    textos = [t.get_text() for t in evolution_figure(serie, "x").axes[0].texts]
    assert "▲ 17" in textos and "▼ 11" in textos


def test_last_value_highlighted_once():
    from analitix.charts import evolution_figure

    serie = [_row("2024-01-01", 14.0, "A"), _row("2024-02-01", 15.0, "A"),
             _row("2024-03-01", 14.5, "A"), _row("2024-04-01", 17.2, "A")]
    textos = [t.get_text() for t in evolution_figure(serie, "x").axes[0].texts]
    assert "Último: ▲ 17.2" in textos and "▲ 17.2" not in textos  # sin etiqueta duplicada


def test_doctor_target_replaces_range_and_one_sided_limit_is_drawn():
    from analitix.charts import apply_target, evolution_figure, series_summary

    serie = [_row(f"2024-0{m}-01", v, "A", low=None, high=130.0) for m, v in ((1, 125.0), (2, 110.0), (3, 95.0))]
    con_objetivo = apply_target(serie, {"low": None, "high": 100.0})
    assert [s["flag_calc"] for s in con_objetivo] == ["alto", "alto", "normal"]
    assert series_summary(con_objetivo).startswith("Dentro del objetivo indicado por su médico en 1 de 3")
    leyenda = [t.get_text() for t in evolution_figure(con_objetivo, "x").axes[0].get_legend().get_texts()]
    assert "Objetivo indicado por su médico (< 100)" in leyenda
    leyenda = [t.get_text() for t in evolution_figure(serie, "x").axes[0].get_legend().get_texts()]
    assert "Límite de referencia (< 130)" in leyenda  # antes, un solo límite no se dibujaba


def test_slight_deviation_is_lighter_same_hue_and_labelled():
    from analitix.charts import COLOR_ALTO, _point_style, deviation_label

    leve, contorno = _point_style({"flag_calc": "alto", "value_num": 16.5, "ref_low": 12.0, "ref_high": 16.0}, "g")
    grave, _ = _point_style({"flag_calc": "alto", "value_num": 20.0, "ref_low": 12.0, "ref_high": 16.0}, "g")
    assert contorno == COLOR_ALTO and grave == COLOR_ALTO and leve != COLOR_ALTO  # mismo tono, más claro
    assert [deviation_label(d) for d in (0, 0.1, -0.5, 1.2)] == [
        "dentro del rango", "ligeramente alto", "bajo", "muy alto"]


def test_doctor_target_note_shown_under_chart():
    from analitix.charts import apply_target, series_summary

    serie = [_row("2024-01-01", 70.0, "A", 20.0, 45.0), _row("2024-02-01", 50.0, "A", 20.0, 45.0)]
    texto = series_summary(apply_target(serie, {"low": 30.0, "high": 60.0, "note": "Dra. ficticia, 2026"}))
    assert texto.splitlines()[1] == "Objetivo indicado por su médico: entre 30 y 60 g/dL · Dra. ficticia, 2026"
    assert "\n" not in series_summary(serie)  # sin objetivo, una sola línea como antes


def test_theil_sen_is_robust_and_ci_says_if_trend_is_demonstrable():
    import datetime as dt

    from analitix.charts import _fit_trend, _trend_text

    fechas = [dt.datetime(2020 + i // 2, 1 + 6 * (i % 2), 1) for i in range(8)]
    sube = [10 + i for i in range(8)]
    sube[3] = 60  # un valor atípico no arrastra la pendiente robusta
    slope, _, _, bajo, alto = _fit_trend(fechas, sube)
    assert abs(slope * 365.25 - 2) < 0.1 and 0 < bajo <= slope <= alto
    plano = [10, 12, 9, 11, 10, 12, 9, 11]
    assert "sin tendencia demostrable" in _trend_text(_fit_trend(fechas, plano), plano, 0, 20)


def test_time_in_range_interpolates_and_skips_long_gaps():
    from analitix.charts import time_in_range

    def p(fecha, v):
        return {"fecha": fecha, "value_num": v, "ref_low": 0.0, "ref_high": 10.0}

    # sube de 5 a 15 y vuelve a 5 en dos tramos de ~6 meses: dentro la mitad de cada uno
    pct, huecos = time_in_range([p("2024-01-01", 5), p("2024-07-01", 15), p("2025-01-01", 5)])
    assert abs(pct - 50) < 0.01 and huecos == 0
    # un hueco de más de un año no se interpola: aquí no queda tramo suficiente
    assert time_in_range([p("2020-01-01", 5), p("2022-01-01", 5)]) is None


def test_kdigo_note_only_for_demonstrable_rapid_egfr_decline():
    from analitix.charts import evolution_figure

    fg = [dict(_row(f"20{20 + i}-01-01", 90 - 8 * i, "A", 60.0, 200.0), kdigo_fg=True) for i in range(6)]
    texto = " ".join(t.get_text() for t in evolution_figure(fg, "FG").axes[0].texts)
    assert "progresión rápida" in texto
    estable = [dict(_row(f"20{20 + i}-01-01", 90 + (i % 2), "A", 60.0, 200.0), kdigo_fg=True) for i in range(6)]
    assert "progresión rápida" not in " ".join(t.get_text() for t in evolution_figure(estable, "FG").axes[0].texts)
